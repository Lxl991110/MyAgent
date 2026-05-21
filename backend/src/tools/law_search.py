"""MCP 法条检索工具 —— 向量 + 关键词混合检索法律法规条文。"""

from __future__ import annotations

from typing import Any, Dict

from tools.base import MCPTool, ToolResult
from services.vector_store import get_vector_store
from services.case_parser import get_knowledge_base


class LawSearchTool(MCPTool):
    name = "law_search"
    description = "在法律法规知识库中检索与查询文本最相关的法条，支持向量+关键词混合检索"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索查询文本，如 '滥用市场支配地位 处罚'",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量，默认 5",
                "default": 5,
            },
            "hybrid": {
                "type": "boolean",
                "description": "是否启用混合检索（向量+关键词），默认 true",
                "default": True,
            },
        },
        "required": ["query"],
    }

    def call(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        top_k = int(kwargs.get("top_k", 5))
        hybrid = bool(kwargs.get("hybrid", True))

        if not query.strip():
            return ToolResult(success=False, error="查询文本不能为空")

        store = get_vector_store()

        # 优先使用向量存储，回退到知识库关键词检索
        if store.law_count > 0:
            results = store.search_laws(query, top_k=top_k, hybrid=hybrid)
            return ToolResult(
                success=True,
                data=[
                    {
                        "law_id": r.law_id,
                        "law_name": r.law_name,
                        "article_number": r.article_number,
                        "content": r.content,
                        "score": r.score,
                        "method": r.retrieval_method,
                    }
                    for r in results
                ],
                metadata={"total": len(results), "backend": "vector_store"},
            )

        kb = get_knowledge_base()
        results = kb.search_similar_laws(query, top_k=top_k)
        return ToolResult(
            success=True,
            data=[
                {
                    "law_id": law.law_id,
                    "law_name": law.law_name,
                    "article_number": law.article_number,
                    "content": law.content[:200],
                    "score": score,
                    "method": "keyword",
                }
                for law, score in results
            ],
            metadata={"total": len(results), "backend": "knowledge_base"},
        )
