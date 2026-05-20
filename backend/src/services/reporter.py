"""Service that consolidates task results into the final report."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from models import TodoItem
from config import Configuration
from prompts import report_writer_instructions
from utils import strip_thinking_tokens


class ReportingService:
    """Generates the final structured report from completed task summaries."""

    def __init__(self, llm: BaseChatModel, config: Configuration) -> None:
        self._llm = llm
        self._config = config

    def generate_report(self, topic: str, todo_items: list[TodoItem]) -> str:
        """Generate a structured report based on completed tasks."""

        tasks_block: list[str] = []
        for task in todo_items:
            summary_block = task.summary or "暂无可用信息"
            sources_block = task.sources_summary or "暂无来源"
            tasks_block.append(
                f"### 任务 {task.id}: {task.title}\n"
                f"- 任务目标：{task.intent}\n"
                f"- 检索查询：{task.query}\n"
                f"- 执行状态：{task.status}\n"
                f"- 任务总结：\n{summary_block}\n"
                f"- 来源概览：\n{sources_block}\n"
            )

        prompt_text = (
            f"研究主题：{topic}\n"
            f"任务概览：\n{''.join(tasks_block)}\n"
            "请整合以上所有任务结果，按模板撰写最终研究报告。"
        )

        messages = [
            SystemMessage(content=report_writer_instructions.strip()),
            HumanMessage(content=prompt_text),
        ]

        response = self._llm.invoke(messages)
        report_text = response.content if hasattr(response, "content") else str(response)
        report_text = report_text.strip()

        if self._config.strip_thinking_tokens:
            report_text = strip_thinking_tokens(report_text)

        return report_text or "报告生成失败，请检查输入。"
