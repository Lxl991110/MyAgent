"""MCP 工具模块 —— 注册并暴露所有法律研究工具。"""

from tools.base import MCPTool, ToolResult, ToolRegistry, get_tool_registry
from tools.law_search import LawSearchTool
from tools.case_query import CaseQueryTool
from tools.fact_check import FactCheckTool
from tools.data_validation import DataValidationTool


def register_all_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    """注册所有内置 MCP 工具到全局注册表。"""
    if registry is None:
        registry = get_tool_registry()

    registry.register(LawSearchTool())
    registry.register(CaseQueryTool())
    registry.register(FactCheckTool())
    registry.register(DataValidationTool())

    return registry


__all__ = [
    "MCPTool",
    "ToolResult",
    "ToolRegistry",
    "get_tool_registry",
    "register_all_tools",
    "LawSearchTool",
    "CaseQueryTool",
    "FactCheckTool",
    "DataValidationTool",
]
