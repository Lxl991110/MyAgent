"""LLM 深度合规审查服务。

基于规则引擎初筛结果 + RAG 检索法条，调用 LLM 进行深度法律分析。
失败时返回 None，由调用方回退到规则引擎结果。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)


class ComplianceReviewService:
    """LLM 驱动的合规审查代理。

    接收规则引擎的预检结果作为上下文，调用 LLM 生成：
    - 违规行为深度分析
    - 法律适用性论证
    - 风险等级评定
    - 具体整改建议
    - 审查总结
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    def review(
        self,
        text: str,
        *,
        context: str = "",
        violations: Optional[Dict[str, Any]] = None,
        fact_checks: Optional[Dict[str, Any]] = None,
        relevant_laws: Optional[List[Dict[str, Any]]] = None,
        past_cases: Optional[List[Dict[str, Any]]] = None,
        trace: Optional[Any] = None,  # ComplianceTrace
    ) -> Optional[Dict[str, Any]]:
        """执行 LLM 深度审查，返回结构化结果或 None（触发回退）。"""
        prompt = self._build_prompt(
            text,
            context=context,
            violations=violations,
            fact_checks=fact_checks,
            relevant_laws=relevant_laws,
            past_cases=past_cases,
        )

        if trace is not None:
            trace.log_step("prompt_build", prompt=prompt)

        try:
            response = self.llm.invoke(prompt)
            content = str(response.content) if hasattr(response, "content") else str(response)
            parsed = self._parse_response(content)
            if trace is not None:
                trace.log_step("llm_analysis", raw_response=content, parsed=parsed is not None)
            return parsed
        except Exception:
            if trace is not None:
                trace.log_step("llm_analysis", error=str(Exception))
            logger.exception("LLM 合规审查失败，将回退到规则引擎")
            return None

    # ── 提示词构建 ──────────────────────────────────────────────────────

    def _build_prompt(
        self,
        text: str,
        *,
        context: str = "",
        violations: Optional[Dict[str, Any]] = None,
        fact_checks: Optional[Dict[str, Any]] = None,
        relevant_laws: Optional[List[Dict[str, Any]]] = None,
        past_cases: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        parts: list[str] = [
            "你是一位资深法律合规审查专家，精通中国反垄断法、反不正当竞争法、电子商务法等经济法领域。",
            "请对以下文本进行深度合规审查分析，严格按 JSON 格式输出结果。",
            "",
            "## 待审查文本",
            text,
        ]

        if context:
            parts.extend(["", "## 背景信息", context])

        # 规则引擎预检结果
        parts.append("")
        parts.append("## 规则引擎预检结果（仅供参考，请独立判断）")

        if violations:
            details = violations.get("details", [])
            if details:
                parts.append("### 初步违规检测")
                for v in details:
                    kws = "、".join(v.get("matched_keywords", []))
                    parts.append(f"- **{v.get('type', '')}** (严重: {v.get('severity', '')}) — 命中: {kws}")
                    parts.append(f"  相关法条: {'; '.join(v.get('relevant_laws', []))}")
            else:
                parts.append("### 初步违规检测: 未发现明显违规关键词")

        if fact_checks:
            checks = fact_checks.get("checks", [])
            if checks:
                parts.append("### 法条引用核查")
                for c in checks:
                    parts.append(f"- {c.get('law_name', '')} 第{c.get('article', '')}条: {c.get('status', '')}")
            total = fact_checks.get("total_refs", 0)
            verified = fact_checks.get("verified", 0)
            if total:
                parts.append(f"引用准确率: {verified}/{total}")

        # RAG 检索法条
        if relevant_laws:
            parts.append("")
            parts.append("## 相关法律法规（RAG 检索）")
            for rl in relevant_laws[:5]:
                parts.append(f"- **{rl.get('law_name', '')}** 第{rl.get('article', '')}条 (相关性: {rl.get('score', 0):.0%})")
                parts.append(f"  {rl.get('content', '')}")

        # 历史相似案例（记忆检索）
        if past_cases:
            parts.append("")
            parts.append("## 历史相似案例参考（长期记忆检索）")
            parts.append("以下是从知识记忆库中检索到的相似历史审查案例，请参考其分析逻辑和结论：")
            for i, pc in enumerate(past_cases, 1):
                parts.append(f"\n### 历史案例 {i}: {pc.get('case_id', '')}")
                parts.append(f"- 原始文本: {pc.get('query', '')[:300]}")
                parts.append(f"- 风险等级: {pc.get('risk_level', '')}")
                parts.append(f"- 审查总结: {pc.get('review_summary', '')[:200]}")
                v_list = pc.get("violations", [])
                if v_list:
                    v_types = [v.get("type", "") for v in v_list if v.get("type")]
                    if v_types:
                        parts.append(f"- 历史违规判定: {', '.join(v_types)}")
                s_list = pc.get("suggestions", [])
                if s_list:
                    parts.append(f"- 历史整改建议: {s_list[0][:150]}")

        # 任务要求
        parts.extend([
            "",
            "## 任务要求",
            "",
            "请对以上文本进行深度法律合规分析，输出严格符合以下 JSON Schema 的结果：",
            "",
            "```json",
            "{",
            '  "risk_level": "高 | 中 | 低",',
            '  "violations": [',
            "    {",
            '      "type": "违规行为类型（如滥用市场支配地位、虚假宣传等）",',
            '      "matched_keywords": ["命中关键词1", "命中关键词2"],',
            '      "count": 命中次数,',
            '      "relevant_laws": ["《反垄断法》第二十二条", ...],',
            '      "severity": "★★★ | ★★☆ | ★☆☆",',
            '      "detail": "对该违规行为的法律分析，包含构成要件分析、法律适用论证"',
            "    }",
            "  ],",
            '  "relevant_laws": [',
            "    {",
            '      "law_name": "法律名称",',
            '      "article": "条文号（如第二十二条）",',
            '      "content": "条文内容摘要",',
            '      "score": 0.0-1.0,',
            '      "applicability": "该法条对本案的适用性分析"',
            "    }",
            "  ],",
            '  "suggestions": ["具体可操作的整改建议1", "建议2", ...],',
            '  "review_summary": "200字以内的审查总结"',
            "}",
            "```",
            "",
            "要求：",
            "- 必须输出纯 JSON，不要包含任何其他文字或 Markdown 代码块标记",
            "- 所有法律引用必须标注具体条文编号",
            "- 风险等级：★★★=3项以上或严重违法, ★★☆=1-2项风险, ★☆☆=轻微或无",
            "- 每条 suggestion 必须具体可操作，不可泛泛而谈",
            "- 如果未发现违规，violations 为空数组，risk_level 为\"低\"",
            "- detail 字段需包含实质性法律分析，不可仅重复违规类型名称",
        ])

        return "\n".join(parts)

    # ── 响应解析 ─────────────────────────────────────────────────────────

    def _parse_response(self, content: str) -> Optional[Dict[str, Any]]:
        """从 LLM 输出中提取 JSON 结果。"""
        # 尝试直接解析
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass

        # 尝试从 Markdown 代码块中提取
        import re
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 尝试提取第一个 { 到最后一个 } 之间的内容
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning("无法解析 LLM 审查响应为 JSON: %.200s...", content)
        return None
