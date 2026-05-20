"""Task summarization using direct LLM calls with optional streaming."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Callable, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from models import TodoItem
from config import Configuration
from prompts import task_summarizer_instructions
from utils import strip_thinking_tokens


class SummarizationService:
    """Handles synchronous and streaming task summarization via LLM."""

    def __init__(self, llm: BaseChatModel, config: Configuration) -> None:
        self._llm = llm
        self._config = config

    def summarize_task(self, topic: str, task: TodoItem, context: str) -> str:
        """Generate a task-specific summary using the LLM."""

        prompt_text = self._build_prompt(topic, task, context)
        messages = [
            SystemMessage(content=task_summarizer_instructions.strip()),
            HumanMessage(content=prompt_text),
        ]

        response = self._llm.invoke(messages)
        summary_text = response.content if hasattr(response, "content") else str(response)
        summary_text = summary_text.strip()

        if self._config.strip_thinking_tokens:
            summary_text = strip_thinking_tokens(summary_text)

        return summary_text or "暂无可用信息"

    def stream_task_summary(
        self, topic: str, task: TodoItem, context: str
    ) -> Tuple[Iterator[str], Callable[[], str]]:
        """Stream the summary text for a task while collecting full output."""

        prompt_text = self._build_prompt(topic, task, context)
        messages = [
            SystemMessage(content=task_summarizer_instructions.strip()),
            HumanMessage(content=prompt_text),
        ]

        remove_thinking = self._config.strip_thinking_tokens
        raw_buffer = ""
        visible_output = ""
        emit_index = 0

        def flush_visible() -> Iterator[str]:
            nonlocal emit_index, raw_buffer
            while True:
                start = raw_buffer.find("<think>", emit_index)
                if start == -1:
                    if emit_index < len(raw_buffer):
                        segment = raw_buffer[emit_index:]
                        emit_index = len(raw_buffer)
                        if segment:
                            yield segment
                    break

                if start > emit_index:
                    segment = raw_buffer[emit_index:start]
                    emit_index = start
                    if segment:
                        yield segment

                end = raw_buffer.find("</think>", start)
                if end == -1:
                    break
                emit_index = end + len("</think>")

        def generator() -> Iterator[str]:
            nonlocal raw_buffer, visible_output, emit_index
            for chunk in self._llm.stream(messages):
                chunk_text = chunk.content if hasattr(chunk, "content") else str(chunk)
                raw_buffer += chunk_text
                if remove_thinking:
                    for segment in flush_visible():
                        visible_output += segment
                        if segment:
                            yield segment
                else:
                    visible_output += chunk_text
                    if chunk_text:
                        yield chunk_text

            if remove_thinking:
                for segment in flush_visible():
                    visible_output += segment
                    if segment:
                        yield segment

        def get_summary() -> str:
            if remove_thinking:
                cleaned = strip_thinking_tokens(visible_output)
            else:
                cleaned = visible_output
            return cleaned.strip()

        return generator(), get_summary

    def _build_prompt(self, topic: str, task: TodoItem, context: str) -> str:
        """Construct the summarization prompt."""

        return (
            f"研究主题：{topic}\n"
            f"任务名称：{task.title}\n"
            f"任务目标：{task.intent}\n"
            f"检索查询：{task.query}\n"
            f"检索上下文：\n{context}\n"
            "请基于上述检索结果，生成一份面向用户的 Markdown 总结（遵循任务总结模板）。"
        )
