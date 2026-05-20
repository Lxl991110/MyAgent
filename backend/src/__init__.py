"""Law Research Agent - A legal research assistant powered by LangGraph."""

__version__ = "0.1.0"

from .agent import LawResearchAgent, run_deep_research
from .config import Configuration, SearchAPI
from .models import ResearchState, SummaryStateOutput, TodoItem

__all__ = [
    "LawResearchAgent",
    "run_deep_research",
    "Configuration",
    "SearchAPI",
    "ResearchState",
    "SummaryStateOutput",
    "TodoItem",
]

