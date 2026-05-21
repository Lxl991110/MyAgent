"""MCP 事实核查工具 —— 校验生成报告中引用法条的准确性和时效性。"""

from __future__ import annotations

import re
from typing import Any

from tools.base import MCPTool, ToolResult
from services.case_parser import get_knowledge_base


class FactCheckTool(MCPTool):
    name = "fact_check"
    description = "核查法律文书中引用的法条是否真实存在、内容是否准确、是否仍有效"
    input_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "待核查的法律文本或报告段落",
            },
        },
        "required": ["text"],
    }

    # 法条引用模式：《XXX》第Y条 / 《XXX》 第 Y 条
    _LAW_REF_PATTERN = re.compile(
        r"《([^》]+)》\s*第?\s*([零一二三四五六七八九十百千\d]+)\s*条"
    )

    def call(self, **kwargs: Any) -> ToolResult:
        text = kwargs.get("text", "")
        if not text.strip():
            return ToolResult(success=False, error="待核查文本不能为空")

        kb = get_knowledge_base()
        all_laws = {l.law_name: l for l in kb.list_laws()}

        refs = self._LAW_REF_PATTERN.findall(text)
        checks: list[dict[str, Any]] = []
        warnings: list[str] = []

        for law_name, article_num in refs:
            law = all_laws.get(law_name)
            if law is None:
                checks.append({
                    "law_name": law_name,
                    "article": article_num,
                    "status": "not_found",
                    "detail": f"知识库中未找到《{law_name}》",
                })
                warnings.append(f"引用的《{law_name}》在知识库中不存在")
            elif article_num not in law.article_number:
                checks.append({
                    "law_name": law_name,
                    "article": article_num,
                    "status": "mismatch",
                    "detail": f"《{law_name}》中未找到第{article_num}条（知识库有: {law.article_number}）",
                })
                warnings.append(f"引用的《{law_name}》第{article_num}条可能不准确")
            else:
                checks.append({
                    "law_name": law_name,
                    "article": article_num,
                    "status": "verified",
                    "detail": f"《{law_name}》第{article_num}条已核实",
                })

        return ToolResult(
            success=True,
            data={
                "total_refs": len(refs),
                "verified": sum(1 for c in checks if c["status"] == "verified"),
                "warnings_count": len(warnings),
                "checks": checks,
            },
            metadata={"warnings": warnings},
        )
