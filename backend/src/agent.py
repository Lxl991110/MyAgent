"""LangGraph-based legal research workflow orchestrator."""

from __future__ import annotations

import logging
from queue import Queue
from threading import Thread
from typing import Any, Iterator, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatTongyi
from langgraph.graph import StateGraph, START, END

from config import Configuration
from models import CaseParseResult, ResearchState, SummaryStateOutput, TodoItem
from services.case_parser import parse_case
from services.planner import PlanningService
from services.reporter import ReportingService
from services.search import dispatch_search, prepare_research_context
from services.summarizer import SummarizationService

logger = logging.getLogger(__name__)


class LawResearchAgent:
    """LangGraph-based multi-agent legal research workflow.

    工作流节点：
        plan → search_tasks → summarize_tasks → generate_report
    """

    def __init__(self, config: Configuration | None = None) -> None:
        self.config = config or Configuration.from_env()
        self.llm = self._init_llm()

        self.planner = PlanningService(self.llm, self.config)
        self.summarizer = SummarizationService(self.llm, self.config)
        self.reporting = ReportingService(self.llm, self.config)

        self._graph = self._build_graph()
        self._stream_queue: Optional[Queue[dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # LLM 初始化
    # ------------------------------------------------------------------
    def _init_llm(self) -> BaseChatModel:
        """Instantiate the chat model based on configuration."""

        llm_kwargs: dict[str, Any] = {"temperature": 0.0}

        model_id = self.config.llm_model_id or self.config.local_llm
        if model_id:
            llm_kwargs["model"] = model_id

        provider = (self.config.llm_provider or "").strip()

        if provider == "ollama":
            llm_kwargs["base_url"] = self.config.sanitized_ollama_url()
            llm_kwargs["api_key"] = self.config.llm_api_key or "ollama"
            return ChatOpenAI(**llm_kwargs)
        elif provider == "lmstudio":
            llm_kwargs["base_url"] = self.config.lmstudio_base_url
            llm_kwargs["api_key"] = self.config.llm_api_key or "lm-studio"
            return ChatOpenAI(**llm_kwargs)
        else:
            api_key = self.config.llm_api_key
            if api_key:
                llm_kwargs["dashscope_api_key"] = api_key
            return ChatTongyi(**llm_kwargs)

    # ------------------------------------------------------------------
    # LangGraph 构建
    # ------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph for the research workflow.

        路径 A（有案例文本）: case_parse → plan → search → summarize → report
        路径 B（仅研究主题）:            plan → search → summarize → report
        """

        builder = StateGraph(ResearchState)

        builder.add_node("case_parse", self._case_parse_node)
        builder.add_node("plan", self._plan_node)
        builder.add_node("search_tasks", self._search_node)
        builder.add_node("summarize_tasks", self._summarize_node)
        builder.add_node("generate_report", self._report_node)

        builder.add_conditional_edges(
            START,
            self._route_on_case_text,
            {"case_parse": "case_parse", "plan": "plan"},
        )
        builder.add_edge("case_parse", "plan")
        builder.add_edge("plan", "search_tasks")
        builder.add_edge("search_tasks", "summarize_tasks")
        builder.add_edge("summarize_tasks", "generate_report")
        builder.add_edge("generate_report", END)

        return builder.compile()

    # ------------------------------------------------------------------
    # 节点实现
    # ------------------------------------------------------------------
    def _plan_node(self, state: ResearchState) -> dict[str, Any]:
        """Node 1: 将研究主题拆解为待办任务列表。"""

        topic = state["research_topic"]
        self._emit_event({"type": "status", "message": "正在拆解研究主题..."})

        todo_items = self.planner.plan_todo_list(topic)

        if not todo_items:
            self._emit_event({"type": "status", "message": "规划未产生任务，使用默认任务"})
            todo_items = [self.planner.create_fallback_task(topic)]

        self._emit_event({
            "type": "todo_list",
            "tasks": [self._serialize_task(t) for t in todo_items],
        })

        return {
            "todo_items": [self._serialize_task(t) for t in todo_items],
            "research_loop_count": 0,
            "stream_events": [],
        }

    def _search_node(self, state: ResearchState) -> dict[str, Any]:
        """Node 2: 为每个任务执行搜索，采集信息。"""

        todo_dicts = state.get("todo_items", [])
        todo_items = [self._deserialize_task(d) for d in todo_dicts]

        self._emit_event({"type": "status", "message": f"开始检索 {len(todo_items)} 个任务..."})

        web_results: list = []
        sources: list = []
        updated_tasks: list[dict[str, Any]] = []

        for task in todo_items:
            self._emit_event({
                "type": "task_status",
                "task_id": task.id,
                "status": "in_progress",
                "title": task.title,
                "intent": task.intent,
            })

            search_result, notices, answer_text, backend = dispatch_search(
                task.query,
                self.config,
                state.get("research_loop_count", 0),
            )
            task.notices = notices

            if not search_result or not search_result.get("results"):
                task.status = "skipped"
                self._emit_event({
                    "type": "task_status",
                    "task_id": task.id,
                    "status": "skipped",
                    "title": task.title,
                    "intent": task.intent,
                })
                updated_tasks.append(self._serialize_task(task))
                continue

            sources_summary, context = prepare_research_context(
                search_result, answer_text, self.config,
            )

            task.sources_summary = sources_summary
            web_results.append(context)
            sources.append(sources_summary)

            self._emit_event({
                "type": "sources",
                "task_id": task.id,
                "latest_sources": sources_summary,
                "raw_context": context,
                "backend": backend,
            })

            updated_tasks.append(self._serialize_task(task))

        return {
            "todo_items": updated_tasks,
            "web_research_results": web_results,
            "sources_gathered": sources,
            "research_loop_count": state.get("research_loop_count", 0) + 1,
        }

    def _summarize_node(self, state: ResearchState) -> dict[str, Any]:
        """Node 3: 对每个任务的检索结果进行总结。"""

        topic = state["research_topic"]
        todo_dicts = state.get("todo_items", [])
        todo_items = [self._deserialize_task(d) for d in todo_dicts]

        self._emit_event({"type": "status", "message": "正在总结各任务的检索结果..."})

        web_results = state.get("web_research_results", [])
        updated_tasks: list[dict[str, Any]] = []

        for i, task in enumerate(todo_items):
            if task.status == "skipped":
                task.summary = "检索无结果，无法生成总结"
                updated_tasks.append(self._serialize_task(task))
                continue

            context = web_results[i] if i < len(web_results) else "暂无上下文"

            if self._stream_queue is not None:
                stream, getter = self.summarizer.stream_task_summary(topic, task, context)
                for chunk in stream:
                    if chunk:
                        self._emit_event({
                            "type": "task_summary_chunk",
                            "task_id": task.id,
                            "content": chunk,
                        })
                summary_text = getter()
            else:
                summary_text = self.summarizer.summarize_task(topic, task, context)

            task.summary = summary_text.strip() if summary_text else "暂无可用信息"
            task.status = "completed"

            self._emit_event({
                "type": "task_status",
                "task_id": task.id,
                "status": "completed",
                "summary": task.summary,
                "sources_summary": task.sources_summary,
            })

            updated_tasks.append(self._serialize_task(task))

        return {"todo_items": updated_tasks}

    def _report_node(self, state: ResearchState) -> dict[str, Any]:
        """Node 4: 整合所有任务结果，生成最终报告。"""

        topic = state["research_topic"]
        todo_dicts = state.get("todo_items", [])
        todo_items = [self._deserialize_task(d) for d in todo_dicts]

        self._emit_event({"type": "status", "message": "正在生成最终研究报告..."})

        report = self.reporting.generate_report(topic, todo_items)

        self._emit_event({
            "type": "final_report",
            "report": report,
        })

        return {
            "structured_report": report,
            "running_summary": report,
        }

    # ------------------------------------------------------------------
    # 路由 & 案例解析节点
    # ------------------------------------------------------------------
    @staticmethod
    def _route_on_case_text(state: ResearchState) -> str:
        """如果有案例文本，先走案例解析；否则直接规划。"""

        if state.get("case_text", "").strip():
            return "case_parse"
        return "plan"

    def _case_parse_node(self, state: ResearchState) -> dict[str, Any]:
        """Node: 案例结构化解析（NER + 结构化 + 知识库入库）。"""

        case_text = state.get("case_text", "")
        self._emit_event({"type": "status", "message": "正在解析案例文本..."})

        result: CaseParseResult = parse_case(case_text)

        if result.structured_case:
            sc = result.structured_case
            self._emit_event({
                "type": "case_parse_result",
                "case_id": sc.case_id,
                "case_type": sc.case_type,
                "subjects": sc.subjects,
                "behaviors": sc.behaviors,
                "related_laws": sc.related_laws,
                "risk_tags": sc.risk_tags,
                "entity_count": len(result.entities),
            })
            self._emit_event({
                "type": "status",
                "message": (
                    f"案例解析完成：类型={sc.case_type}, "
                    f"主体={len(sc.subjects)}个, "
                    f"行为={len(sc.behaviors)}个, "
                    f"法条={len(sc.related_laws)}条"
                ),
            })
        else:
            self._emit_event({
                "type": "status",
                "message": f"案例解析部分失败: {'; '.join(result.errors)}",
            })

        return {
            "parse_result": {
                "success": result.success,
                "case_type": result.structured_case.case_type if result.structured_case else "",
                "subjects": result.structured_case.subjects if result.structured_case else [],
                "behaviors": result.structured_case.behaviors if result.structured_case else [],
                "related_laws": result.structured_case.related_laws if result.structured_case else [],
                "risk_tags": result.structured_case.risk_tags if result.structured_case else [],
                "entity_count": len(result.entities),
                "errors": result.errors,
            },
        }

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    def run(
        self,
        topic: str,
        *,
        case_text: str = "",
    ) -> SummaryStateOutput:
        """同步执行研究流程，返回最终报告。"""

        initial_state: ResearchState = {
            "research_topic": topic,
            "case_text": case_text,
            "parse_result": None,
            "todo_items": [],
            "web_research_results": [],
            "sources_gathered": [],
            "research_loop_count": 0,
            "running_summary": "",
            "structured_report": "",
            "stream_events": [],
        }

        result = self._graph.invoke(initial_state)

        todo_dicts = result.get("todo_items", [])
        todo_items = [self._deserialize_task(d) for d in todo_dicts]

        return SummaryStateOutput(
            running_summary=result.get("structured_report", ""),
            report_markdown=result.get("structured_report", ""),
            todo_items=todo_items,
            case_parse_result=result.get("parse_result"),
        )

    def run_stream(
        self,
        topic: str,
        *,
        case_text: str = "",
    ) -> Iterator[dict[str, Any]]:
        """流式执行研究流程，逐步产出 SSE 事件。"""

        event_queue: Queue[dict[str, Any]] = Queue()
        self._stream_queue = event_queue

        def emit(event: dict[str, Any]) -> None:
            event_queue.put(event)

        self._emit_event = emit  # type: ignore[method-assign]

        def worker() -> None:
            try:
                self.run(topic, case_text=case_text)
            except Exception as exc:
                logger.exception("Streaming research failed")
                event_queue.put({"type": "error", "detail": str(exc)})
            finally:
                event_queue.put({"type": "done"})

        thread = Thread(target=worker, daemon=True)
        thread.start()

        try:
            while True:
                event = event_queue.get()
                if event.get("type") == "done":
                    break
                if event.get("type") == "error":
                    yield event
                    break
                yield event
        finally:
            self._stream_queue = None
            self._emit_event = self._noop_emit  # type: ignore[method-assign]
            thread.join()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _noop_emit(self, event: dict[str, Any]) -> None:
        """Default no-op event emitter (overridden during streaming)."""
        pass

    _emit_event = _noop_emit

    @staticmethod
    def _serialize_task(task: TodoItem) -> dict[str, Any]:
        """Convert TodoItem to a serializable dict for state storage."""

        return {
            "id": task.id,
            "title": task.title,
            "intent": task.intent,
            "query": task.query,
            "status": task.status,
            "summary": task.summary,
            "sources_summary": task.sources_summary,
            "notices": task.notices,
        }

    @staticmethod
    def _deserialize_task(data: dict[str, Any]) -> TodoItem:
        """Reconstruct TodoItem from a dict."""

        return TodoItem(
            id=data.get("id", 0),
            title=data.get("title", ""),
            intent=data.get("intent", ""),
            query=data.get("query", ""),
            status=data.get("status", "pending"),
            summary=data.get("summary"),
            sources_summary=data.get("sources_summary"),
            notices=data.get("notices", []),
        )


def run_deep_research(topic: str, config: Configuration | None = None) -> SummaryStateOutput:
    """Convenience function for programmatic use."""

    agent = LawResearchAgent(config=config)
    return agent.run(topic)
