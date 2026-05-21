"""LangGraph-based legal research workflow orchestrator.

工作流 (7 节点):
    case_parse → plan → search → summarize → retrieve → generate → verify → report

其中 case_parse 为条件节点：仅当提供 case_text 时执行。
"""

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
from models import (
    CaseParseResult,
    ResearchState,
    RetrievedLaw,
    RetrievedCase,
    SummaryStateOutput,
    TodoItem,
    VerificationResult,
)
from services.case_parser import parse_case, get_knowledge_base
from services.embedding import get_embedding_service
from services.generator import GenerationAgent
from services.planner import PlanningService
from services.rag_service import build_rag_context
from services.reporter import ReportingService
from services.search import dispatch_search, prepare_research_context
from services.summarizer import SummarizationService
from services.vector_store import get_vector_store
from services.verifier import VerificationAgent
from tools import register_all_tools, get_tool_registry

logger = logging.getLogger(__name__)


class LawResearchAgent:
    """LangGraph-based multi-agent legal research workflow.

    工作流节点：
        plan → search_tasks → summarize_tasks → generate_report
    """

    def __init__(self, config: Configuration | None = None) -> None:
        self.config = config or Configuration.from_env()
        self.llm = self._init_llm()

        # 基础服务
        self.planner = PlanningService(self.llm, self.config)
        self.summarizer = SummarizationService(self.llm, self.config)
        self.reporting = ReportingService(self.llm, self.config)

        # RAG + MCP 服务
        self.embedding = get_embedding_service()
        self.vector_store = get_vector_store()
        self.generator = GenerationAgent(self.llm)
        self.verifier = VerificationAgent()
        self.tool_registry = register_all_tools()

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

        路径 A（有案例文本）: case_parse → plan → search → summarize → retrieve → generate → verify → report
        路径 B（仅研究主题）:            plan → search → summarize → retrieve → generate → verify → report
        """

        builder = StateGraph(ResearchState)

        builder.add_node("case_parse", self._case_parse_node)
        builder.add_node("plan", self._plan_node)
        builder.add_node("search_tasks", self._search_node)
        builder.add_node("summarize_tasks", self._summarize_node)
        builder.add_node("retrieve", self._retrieve_node)
        builder.add_node("generate", self._generate_node)
        builder.add_node("verify", self._verify_node)
        builder.add_node("generate_report", self._report_node)

        builder.add_conditional_edges(
            START,
            self._route_on_case_text,
            {"case_parse": "case_parse", "plan": "plan"},
        )
        builder.add_edge("case_parse", "plan")
        builder.add_edge("plan", "search_tasks")
        builder.add_edge("search_tasks", "summarize_tasks")
        builder.add_edge("summarize_tasks", "retrieve")
        builder.add_edge("retrieve", "generate")
        builder.add_edge("generate", "verify")
        builder.add_edge("verify", "generate_report")
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
    # Node 5: RAG 检索（向量检索法条 + 案例）
    # ------------------------------------------------------------------
    def _retrieve_node(self, state: ResearchState) -> dict[str, Any]:
        """从向量知识库中检索相关法条和案例。"""

        topic = state["research_topic"]
        parse_result = state.get("parse_result") or {}
        web_results = state.get("web_research_results", [])
        sources = state.get("sources_gathered", [])

        # 构建检索查询文本
        query_parts = [topic]
        if parse_result:
            query_parts.append(parse_result.get("case_type", ""))
            query_parts.extend(parse_result.get("behaviors", []))
            query_parts.extend(parse_result.get("related_laws", []))
        if sources:
            query_parts.append(" ".join(str(s)[:500] for s in sources[:3]))
        query = " ".join(q for q in query_parts if q)

        self._emit_event({"type": "status", "message": "正在从法律知识库检索相关法条和案例..."})

        # 向量检索
        retrieved_laws = self.vector_store.search_laws(query, top_k=5, hybrid=True)
        retrieved_cases = self.vector_store.search_cases(query, top_k=3, hybrid=True)

        # 如果向量存储为空，尝试知识库关键词检索
        if not retrieved_laws:
            kb = get_knowledge_base()
            kb_results = kb.search_similar_laws(topic, top_k=5)
            retrieved_laws = [
                RetrievedLaw(
                    law_id=law.law_id,
                    law_name=law.law_name,
                    article_number=law.article_number,
                    content=law.content,
                    chapter=law.chapter,
                    enforcement_level=law.enforcement_level,
                    score=score,
                    retrieval_method="keyword",
                )
                for law, score in kb_results
            ]

        # 拼接 RAG 上下文
        rag_context = build_rag_context(retrieved_laws, retrieved_cases)

        self._emit_event({
            "type": "rag_retrieval",
            "law_count": len(retrieved_laws),
            "case_count": len(retrieved_cases),
            "top_laws": [
                {"name": rl.law_name, "article": rl.article_number, "score": rl.score}
                for rl in retrieved_laws[:3]
            ],
            "top_cases": [
                {"id": rc.case_id, "type": rc.case_type, "score": rc.score}
                for rc in retrieved_cases[:3]
            ],
        })

        self._emit_event({
            "type": "status",
            "message": f"知识库检索完成：找到 {len(retrieved_laws)} 条法条、{len(retrieved_cases)} 个案例",
        })

        return {
            "retrieved_laws": [
                {
                    "law_id": rl.law_id,
                    "law_name": rl.law_name,
                    "article_number": rl.article_number,
                    "content": rl.content,
                    "score": rl.score,
                }
                for rl in retrieved_laws
            ],
            "retrieved_cases": [
                {
                    "case_id": rc.case_id,
                    "case_type": rc.case_type,
                    "subjects": rc.subjects,
                    "behaviors": rc.behaviors,
                    "related_laws": rc.related_laws,
                    "score": rc.score,
                }
                for rc in retrieved_cases
            ],
            "rag_context": rag_context,
        }

    # ------------------------------------------------------------------
    # Node 6: 生成代理（基于 RAG 上下文生成报告）
    # ------------------------------------------------------------------
    def _generate_node(self, state: ResearchState) -> dict[str, Any]:
        """使用 RAG 上下文 + 网络检索结果生成法律研究报告。"""

        topic = state["research_topic"]
        rag_context = state.get("rag_context", "")
        parse_result = state.get("parse_result")
        web_results = state.get("web_research_results", [])

        web_context = "\n".join(str(r)[:1000] for r in web_results[:3]) if web_results else ""

        self._emit_event({"type": "status", "message": "正在基于知识库和网络信息生成研究报告..."})

        # 按案由选择场景模版
        case_type = (parse_result or {}).get("case_type", "其他") if parse_result else "其他"

        # 分段生成（用于流式反馈）
        sections = ["案件概述", "法律分析", "类案参考", "风险评估", "合规建议"]

        generated_parts: list[str] = []
        for i, section in enumerate(sections):
            self._emit_event({
                "type": "generation_progress",
                "section": section,
                "progress": f"{i + 1}/{len(sections)}",
            })

            part = self.generator.generate_section(
                section, topic, rag_context,
                web_context=web_context,
                case_parse_info=parse_result,
            )

            if part:
                generated_parts.append(f"## {section}\n\n{part}")

            self._emit_event({
                "type": "section_generated",
                "section": section,
                "content_preview": part[:200] if part else "",
            })

        # 添加参考文献章节
        refs_section = self._build_references_section(state)
        generated_parts.append(refs_section)

        full_report = "\n\n".join(generated_parts)

        # 结构校验
        validation = self.generator.validate_output(full_report)
        self._emit_event({
            "type": "generation_validation",
            "valid": validation["valid"],
            "checks": validation,
        })

        return {
            "generation_result": {
                "report": full_report,
                "case_type": case_type,
                "sections_count": len(sections),
                "validation": validation,
            },
        }

    # ------------------------------------------------------------------
    # Node 7: 验证代理（事实核查 + 违法检测）
    # ------------------------------------------------------------------
    def _verify_node(self, state: ResearchState) -> dict[str, Any]:
        """对生成的报告进行事实核查、法条验证和违法检测。"""

        gen_result = state.get("generation_result") or {}
        report = gen_result.get("report", "")
        parse_result = state.get("parse_result")
        original_case_text = state.get("case_text", "")
        retrieved_laws = state.get("retrieved_laws", [])

        self._emit_event({"type": "status", "message": "正在验证报告质量..."})

        result: VerificationResult = self.verifier.verify(
            report,
            case_parse_info=parse_result,
            retrieved_laws=retrieved_laws,
            original_case_text=original_case_text,
        )

        self._emit_event({
            "type": "verification_result",
            "passed": result.passed,
            "score": result.overall_score,
            "violations": result.violation_detection.get("violations_detected", 0),
            "warnings": result.warnings,
            "corrections": result.corrections,
        })

        if not result.passed:
            self._emit_event({
                "type": "status",
                "message": f"验证未通过 (评分: {result.overall_score})，请查看警告信息",
            })
        else:
            self._emit_event({
                "type": "status",
                "message": f"报告验证通过 (评分: {result.overall_score})",
            })

        return {
            "verification_result": {
                "law_validity": result.law_validity,
                "fact_consistency": result.fact_consistency,
                "violation_detection": result.violation_detection,
                "overall_score": result.overall_score,
                "corrections": result.corrections,
                "warnings": result.warnings,
                "passed": result.passed,
            },
        }

    # ── 辅助：构建参考文献章节 ───────────────────────────────────────────

    def _build_references_section(self, state: ResearchState) -> str:
        """从检索结果中提取法条和案例引用，构建参考文献章节。"""
        lines: list[str] = ["## 参考文献\n"]

        retrieved_laws = state.get("retrieved_laws", [])
        if retrieved_laws:
            lines.append("### 法律法规\n")
            seen: set[str] = set()
            for rl in retrieved_laws[:10]:
                ref = f"- 《{rl.get('law_name', '')}》第{rl.get('article_number', '')}条"
                if ref not in seen:
                    lines.append(ref)
                    seen.add(ref)

        retrieved_cases = state.get("retrieved_cases", [])
        if retrieved_cases:
            lines.append("\n### 参考案例\n")
            for rc in retrieved_cases[:5]:
                lines.append(f"- [{rc.get('case_type', '')}] {rc.get('case_id', '')}")

        parse_result = state.get("parse_result") or {}
        related_laws = parse_result.get("related_laws", [])
        if related_laws:
            lines.append("\n### 案例关联法条\n")
            for law_ref in related_laws[:5]:
                lines.append(f"- {law_ref}")

        if len(lines) == 1:
            lines.append("（无特定参考文献）")

        return "\n".join(lines)

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
            # RAG + MCP 初始字段
            "retrieved_laws": [],
            "retrieved_cases": [],
            "rag_context": "",
            "generation_result": None,
            "verification_result": None,
        }

        result = self._graph.invoke(initial_state)

        todo_dicts = result.get("todo_items", [])
        todo_items = [self._deserialize_task(d) for d in todo_dicts]

        # 使用生成代理的报告（优先）或旧版结构化报告
        gen_result = result.get("generation_result") or {}
        report = gen_result.get("report") or result.get("structured_report", "")

        verif_data = result.get("verification_result") or {}
        verification = VerificationResult(
            law_validity=verif_data.get("law_validity", {}),
            fact_consistency=verif_data.get("fact_consistency", {}),
            violation_detection=verif_data.get("violation_detection", {}),
            overall_score=verif_data.get("overall_score", 0.0),
            corrections=verif_data.get("corrections", []),
            warnings=verif_data.get("warnings", []),
            passed=verif_data.get("passed", True),
        )

        retrieved_laws_raw = result.get("retrieved_laws", [])
        retrieved_laws = [
            RetrievedLaw(
                law_id=rl.get("law_id", ""),
                law_name=rl.get("law_name", ""),
                article_number=rl.get("article_number", ""),
                content=rl.get("content", ""),
                score=rl.get("score", 0.0),
                retrieval_method=rl.get("retrieval_method", "vector"),
            )
            for rl in retrieved_laws_raw
        ]

        return SummaryStateOutput(
            running_summary=report,
            report_markdown=report,
            todo_items=todo_items,
            case_parse_result=result.get("parse_result"),
            verification_result=verification,
            retrieved_laws=retrieved_laws,
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
