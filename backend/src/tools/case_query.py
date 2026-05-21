"""MCP 案例查询工具 —— 检索相似案例并返回结构化信息。"""

from __future__ import annotations

from typing import Any

from tools.base import MCPTool, ToolResult
from services.vector_store import get_vector_store
from services.case_parser import get_knowledge_base


class CaseQueryTool(MCPTool):
    name = "case_query"
    description = "在案例库中检索与查询文本相似的已入库案例，返回结构化案例信息及关联法条"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索查询文本，如 '某平台要求商家二选一'",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量，默认 3",
                "default": 3,
            },
            "include_laws": {
                "type": "boolean",
                "description": "是否同时返回关联法条，默认 true",
                "default": True,
            },
        },
        "required": ["query"],
    }

    def call(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        top_k = int(kwargs.get("top_k", 3))
        include_laws = bool(kwargs.get("include_laws", True))

        if not query.strip():
            return ToolResult(success=False, error="查询文本不能为空")

        store = get_vector_store()
        kb = get_knowledge_base()

        # 向量检索案例
        if store.case_count > 0:
            results = store.search_cases(query, top_k=top_k, hybrid=True)
            data = [
                {
                    "case_id": r.case_id,
                    "case_type": r.case_type,
                    "subjects": r.subjects,
                    "behaviors": r.behaviors,
                    "related_laws": r.related_laws,
                    "risk_tags": r.risk_tags,
                    "description": r.description,
                    "score": r.score,
                    "method": r.retrieval_method,
                }
                for r in results
            ]
        else:
            data = [
                {
                    "case_id": c.case_id,
                    "case_type": c.case_type,
                    "subjects": c.subjects,
                    "behaviors": c.behaviors,
                    "related_laws": c.related_laws,
                    "risk_tags": c.risk_tags,
                    "description": c.description[:200],
                    "score": 0.0,
                    "method": "keyword",
                }
                for c in kb.list_cases()[:top_k]
            ]

        # 附带关联法条
        if include_laws and data:
            for item in data:
                links = kb.get_case_links(item["case_id"])
                item["linked_law_ids"] = links.law_ids if links else []

        return ToolResult(
            success=True,
            data=data,
            metadata={"total": len(data)},
        )
