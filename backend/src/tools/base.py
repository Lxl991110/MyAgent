"""MCP 协议工具基类及工具注册表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(kw_only=True)
class ToolResult:
    """MCP 工具调用返回结果。"""

    success: bool
    data: Any = None
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class MCPTool(ABC):
    """MCP (Model Context Protocol) 工具基类。

    每个工具定义 name / description / input_schema，
    子类实现 call() 方法。
    """

    name: str = ""
    description: str = ""
    input_schema: Dict[str, Any] = {}

    @abstractmethod
    def call(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class ToolRegistry:
    """全局 MCP 工具注册表。"""

    def __init__(self) -> None:
        self._tools: Dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[MCPTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._tools.values()]

    def call_tool(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(success=False, error=f"未知工具: {name}")
        try:
            return tool.call(**kwargs)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


# 全局注册表单例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
