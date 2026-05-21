"""RAG 检索增强生成服务。

负责将向量检索到的法条和案例组装为 LLM 可用的上下文提示词。
"""

from __future__ import annotations

from typing import List

from models import RetrievedLaw, RetrievedCase
from tools.base import ToolResult


def build_rag_context(
    retrieved_laws: list[RetrievedLaw],
    retrieved_cases: list[RetrievedCase],
    *,
    max_laws: int = 5,
    max_cases: int = 3,
) -> str:
    """将检索到的法条和案例拼接为上下文文本块。"""
    parts: list[str] = []

    # ── 法条部分 ──
    if retrieved_laws:
        top_laws = retrieved_laws[:max_laws]
        parts.append("## 相关法律法规\n")
        for i, rl in enumerate(top_laws, 1):
            parts.append(
                f"**{i}. {rl.law_name} 第{rl.article_number}条** "
                f"(相关性: {rl.score:.0%}, 方法: {rl.retrieval_method})\n"
                f"> {rl.content}\n"
            )

    # ── 案例部分 ──
    if retrieved_cases:
        top_cases = retrieved_cases[:max_cases]
        parts.append("## 参考案例\n")
        for i, rc in enumerate(top_cases, 1):
            parts.append(
                f"**{i}. [{rc.case_type}] {rc.case_id}** "
                f"(相关性: {rc.score:.0%})\n"
                f"- 当事人: {'、'.join(rc.subjects) if rc.subjects else '未知'}\n"
                f"- 行为: {'、'.join(rc.behaviors) if rc.behaviors else '未知'}\n"
                f"- 风险: {'、'.join(rc.risk_tags) if rc.risk_tags else '无'}\n"
                f"- 关联法条: {'、'.join(rc.related_laws) if rc.related_laws else '无'}\n"
                f"- 案情: {rc.description[:300]}\n"
            )

    if not parts:
        return "（未检索到相关法条或案例）"

    return "\n".join(parts)


def build_rag_prompt(
    topic: str,
    rag_context: str,
    *,
    web_context: str = "",
    case_parse_info: dict | None = None,
) -> str:
    """构造完整的 RAG 增强提示词，供 LLM 生成报告使用。"""

    sections: list[str] = [
        "你是一位资深法律研究专家，需要基于以下信息生成专业的法律研究报告。\n",
        f"## 研究主题\n{topic}\n",
    ]

    if case_parse_info:
        sc = case_parse_info
        sections.append("## 案例解析信息\n")
        sections.append(f"- 案由: {sc.get('case_type', '未知')}")
        sections.append(f"- 当事人: {'、'.join(sc.get('subjects', [])) or '未知'}")
        sections.append(f"- 行为: {'、'.join(sc.get('behaviors', [])) or '未知'}")
        sections.append(f"- 风险标签: {'、'.join(sc.get('risk_tags', [])) or '无'}")
        sections.append(f"- 关联法条: {'、'.join(sc.get('related_laws', [])) or '无'}\n")

    sections.append(f"## 知识库检索结果\n{rag_context}\n")

    if web_context:
        sections.append(f"## 网络检索结果\n{web_context}\n")

    sections.extend([
        "## 任务要求\n",
        "请按以下结构生成研究报告：\n",
        "1. **案件概述** — 提炼案件基本事实和法律关系",
        "2. **法律分析** — 结合引用法条进行法律适用性分析",
        "3. **类案参考** — 对比类似案例的裁判逻辑",
        "4. **风险评估** — 识别法律风险点并评估严重程度",
        "5. **合规建议** — 给出具体的合规改进建议",
        "6. **参考文献** — 列出所有引用的法律法规和案例\n",
        "要求：",
        "- 所有法律引用必须标注具体条文编号",
        "- 事实陈述与法律分析须有明确对应关系",
        "- 风险等级使用 ★☆☆ / ★★☆ / ★★★ 三级标注",
    ])

    return "\n".join(sections)
