"""Service responsible for converting a research topic into actionable tasks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from models import TodoItem
from config import Configuration
from prompts import get_current_date, todo_planner_system_prompt, todo_planner_instructions
from utils import strip_thinking_tokens

logger = logging.getLogger(__name__)


class PlanningService:
    """Uses LLM to break the research topic into structured TODO items."""

    def __init__(self, llm: BaseChatModel, config: Configuration) -> None:
        self._llm = llm
        self._config = config

    def plan_todo_list(self, topic: str) -> List[TodoItem]:
        """Ask the LLM to decompose the topic into 3-5 complementary tasks."""

        prompt_text = todo_planner_instructions.format(
            current_date=get_current_date(),
            research_topic=topic,
        )

        messages = [
            SystemMessage(content=todo_planner_system_prompt.strip()),
            HumanMessage(content=prompt_text),
        ]

        response = self._llm.invoke(messages)
        raw_output = response.content if hasattr(response, "content") else str(response)

        logger.info("Planner raw output (truncated): %s", raw_output[:500])

        tasks_payload = self._extract_tasks(raw_output)
        todo_items: List[TodoItem] = []

        for idx, item in enumerate(tasks_payload, start=1):
            title = str(item.get("title") or f"任务{idx}").strip()
            intent = str(item.get("intent") or "聚焦主题的关键问题").strip()
            query = str(item.get("query") or topic).strip()

            if not query:
                query = topic

            task = TodoItem(
                id=idx,
                title=title,
                intent=intent,
                query=query,
            )
            todo_items.append(task)

        titles = [task.title for task in todo_items]
        logger.info("Planner produced %d tasks: %s", len(todo_items), titles)
        return todo_items

    @staticmethod
    def create_fallback_task(topic: str) -> TodoItem:
        """Create a minimal fallback task when planning fails."""

        return TodoItem(
            id=1,
            title="基础背景梳理",
            intent="收集主题的核心背景与最新动态",
            query=f"{topic} 最新进展" if topic else "基础背景梳理",
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _extract_tasks(self, raw_response: str) -> List[dict[str, Any]]:
        """Parse planner output into a list of task dictionaries."""

        text = raw_response.strip()
        if self._config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)

        json_payload = self._extract_json_payload(text)
        tasks: List[dict[str, Any]] = []

        if isinstance(json_payload, dict):
            candidate = json_payload.get("tasks")
            if isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        tasks.append(item)
        elif isinstance(json_payload, list):
            for item in json_payload:
                if isinstance(item, dict):
                    tasks.append(item)

        return tasks

    def _extract_json_payload(self, text: str) -> Optional[dict[str, Any] | list]:
        """Try to locate and parse a JSON object or array from the text."""

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None

        return None
