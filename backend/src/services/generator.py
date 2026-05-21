"""生成代理 —— 基于 RAG 上下文生成结构化法律分析报告。

按案由类型加载不同的分析模版，确保报告格式规范、法律引用准确。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.language_models.chat_models import BaseChatModel

from services.rag_service import build_rag_prompt
from models import RetrievedLaw, RetrievedCase

logger = logging.getLogger(__name__)

# ── 案由 → 分析场景模版 ─────────────────────────────────────────────────────

_SCENARIO_TEMPLATES: Dict[str, str] = {
    "滥用市场支配地位": (
        "重点分析：市场支配地位的认定标准、滥用行为的类型化分析、"
        "相关市场界定、正当理由抗辩的可能性、处罚幅度参考。"
    ),
    "垄断协议": (
        "重点分析：协议是否构成横向/纵向垄断协议、是否适用豁免条款、"
        "协议对市场竞争的实际影响、参与者责任划分。"
    ),
    "经营者集中": (
        "重点分析：集中是否达到申报标准、相关市场界定、"
        "竞争影响评估、附加限制性条件可能性、未依法申报的法律后果。"
    ),
    "行政垄断": (
        "重点分析：行政行为是否构成滥用行政权力排除限制竞争、"
        "法律依据与政策边界、救济途径分析。"
    ),
    "不正当竞争": (
        "重点分析：行为是否构成混淆/虚假宣传/商业诋毁等、"
        "损害赔偿计算方式、停止侵害与消除影响的具体措施。"
    ),
    "其他": (
        "重点分析：案件法律关系的定性、适用法律的选择、"
        "争议焦点提炼、裁判规则总结。"
    ),
}


class GenerationAgent:
    """法律研究报告生成代理。"""

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    def generate(
        self,
        topic: str,
        rag_context: str,
        *,
        web_context: str = "",
        case_parse_info: dict | None = None,
        retrieved_laws: list[RetrievedLaw] | None = None,
        retrieved_cases: list[RetrievedCase] | None = None,
    ) -> str:
        """生成完整法律研究报告。"""
        prompt = build_rag_prompt(
            topic,
            rag_context,
            web_context=web_context,
            case_parse_info=case_parse_info,
        )

        # 注入案由特定的分析指引
        case_type = (case_parse_info or {}).get("case_type", "其他")
        scenario = _SCENARIO_TEMPLATES.get(case_type, _SCENARIO_TEMPLATES["其他"])
        prompt += f"\n\n**案由分析指引（{case_type}）**：{scenario}"

        try:
            response = self.llm.invoke(prompt)
            return str(response.content) if hasattr(response, "content") else str(response)
        except Exception:
            logger.exception("LLM 报告生成失败")
            return f"报告生成失败，请稍后重试。\n\n研究主题：{topic}\n案由：{case_type}"

    def generate_section(
        self,
        section_name: str,
        topic: str,
        rag_context: str,
        *,
        web_context: str = "",
        case_parse_info: dict | None = None,
    ) -> str:
        """按章节生成报告片段（用于流式输出）。"""
        prompt = f"""你是一位资深法律研究专家，请为以下法律研究报告撰写「{section_name}」章节。

## 研究主题
{topic}

## 参考知识库信息
{rag_context}

## 网络检索信息
{web_context or '无'}

## 案例解析信息
{case_parse_info or '无'}

请撰写「{section_name}」章节内容，确保：
- 所有法律引用标注具体条文编号
- 事实与分析一一对应
- 风险等级使用 ★☆☆ / ★★☆ / ★★★ 三级标注

仅输出该章节的 Markdown 内容，不要包含其他章节。"""

        try:
            response = self.llm.invoke(prompt)
            return str(response.content) if hasattr(response, "content") else str(response)
        except Exception:
            logger.exception("章节生成失败: %s", section_name)
            return f"（{section_name}章节生成失败）"

    def validate_output(self, report: str) -> Dict[str, Any]:
        """对生成报告进行基本结构校验。"""
        required_sections = ["案件概述", "法律分析", "类案参考", "风险评估", "合规建议"]
        checks: Dict[str, bool] = {}

        for section in required_sections:
            checks[section] = section in report

        has_references = "参考文献" in report or "参考" in report
        has_law_citation = "第" in report and "条" in report
        has_risk_levels = "★" in report

        return {
            "sections_complete": all(checks.values()),
            "section_checks": checks,
            "has_references": has_references,
            "has_law_citation": has_law_citation,
            "has_risk_levels": has_risk_levels,
            "valid": all(checks.values()) and has_law_citation,
        }
