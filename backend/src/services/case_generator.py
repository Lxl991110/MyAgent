"""可控法律案例生成服务。

工作流:
  用户条件 → 法规检索 → 历史案例检索 → RAG 上下文构建
  → Prompt 构建 → LLM 生成 → 校验 → 结构化输出

支持 SSE 流式输出，每个阶段实时推送进度事件。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

from langchain_core.language_models.chat_models import BaseChatModel

from models import CaseGenerationConfig, GeneratedCase

logger = logging.getLogger(__name__)


class CaseGenerator:
    """受约束的案例生成代理。

    结合 RAG 检索（法规 + 历史案例）+ 生成规则 + LLM，
    输出结构化的法律案例。
    """

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    # ── 流式生成 ──────────────────────────────────────────────────────────

    def generate_stream(
        self,
        config: CaseGenerationConfig,
        user_message: str = "",
    ) -> Iterator[Dict[str, Any]]:
        """流式生成案例，每个步骤 yield 一个 SSE 事件。"""
        case_id = f"gen-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

        # ── Step 0: 条件解析 ──────────────────────────────────────────
        resolved = self._resolve_config(config, user_message)
        yield {"type": "config_resolved", "config": {
            "violation_behavior": resolved.violation_behavior,
            "violated_law": resolved.violated_law,
            "case_type": resolved.case_type,
            "risk_level": resolved.risk_level,
            "style": resolved.style,
            "case_id": case_id,
        }}

        # ── Step 1: 法规检索 ──────────────────────────────────────────
        retrieved_laws = self._retrieve_laws(resolved)
        yield {"type": "laws_retrieved", "count": len(retrieved_laws), "laws": [
            {"law_name": l.get("law_name", ""), "article_number": l.get("article_number", ""), "score": l.get("score", 0)}
            for l in retrieved_laws[:5]
        ]}

        # ── Step 2: 历史案例检索 ─────────────────────────────────────
        retrieved_cases = self._retrieve_similar_cases(resolved)
        yield {"type": "cases_retrieved", "count": len(retrieved_cases), "cases": [
            {"case_id": c.get("case_id", ""), "query": (c.get("query", "") or "")[:100], "risk_level": c.get("risk_level", "")}
            for c in retrieved_cases[:5]
        ]}

        # ── Step 3: RAG 上下文构建 ───────────────────────────────────
        rag_context = self._build_rag_context(resolved, retrieved_laws, retrieved_cases)
        yield {"type": "rag_built", "context_length": len(rag_context)}

        # ── Step 4: Prompt 构建 ──────────────────────────────────────
        prompt = self._build_prompt(resolved, rag_context)
        yield {"type": "prompt_built", "prompt_length": len(prompt)}

        # ── Step 5: LLM 生成 ────────────────────────────────────────
        generated = None
        try:
            response = self.llm.invoke(prompt)
            content = str(response.content) if hasattr(response, "content") else str(response)
            generated = self._parse_case(content)
            if generated:
                generated["case_id"] = case_id
                generated["source"] = "generated"
                yield {"type": "case_generated", "case": generated}
            else:
                yield {"type": "generation_error", "detail": "解析 LLM 输出失败", "raw": content[:500]}
        except Exception:
            logger.exception("案例生成 LLM 调用失败")
            yield {"type": "generation_error", "detail": "LLM 调用失败"}

        # ── Step 6: 校验 ────────────────────────────────────────────
        if generated:
            verification = self._verify(generated, resolved, retrieved_laws)
            generated["verified"] = verification.get("passed", False)
            yield {"type": "verification_result", **verification}

        # ── Step 7: 完成 ────────────────────────────────────────────
        yield {"type": "done", "case_id": case_id, "case": generated}

    # ── 配置解析 ──────────────────────────────────────────────────────────

    def _resolve_config(self, config: CaseGenerationConfig, user_message: str) -> CaseGenerationConfig:
        """从用户自然语言中增强/补全配置。"""
        if not user_message.strip():
            return config

        # 如果配置已完整，直接返回
        if config.violation_behavior and config.violated_law and config.case_type:
            config.extra_context = user_message
            return config

        # 尝试从用户消息中提取
        resolved = CaseGenerationConfig(
            violation_behavior=config.violation_behavior,
            violated_law=config.violated_law,
            case_type=config.case_type,
            risk_level=config.risk_level,
            style=config.style,
            extra_context=config.extra_context or user_message,
        )
        return resolved

    # ── 法规检索 ──────────────────────────────────────────────────────────

    def _retrieve_laws(self, config: CaseGenerationConfig) -> list[Dict[str, Any]]:
        """从 Qdrant laws collection 检索相关法条。"""
        try:
            from services.law_retriever import get_law_retriever

            retriever = get_law_retriever()
            if not retriever.available:
                return []

            # 构建检索查询
            parts = [config.violation_behavior, config.case_type, config.extra_context]
            query = " ".join(p for p in parts if p)

            # 如果指定了具体法条，精确查找
            if config.violated_law:
                laws = retriever.search(query, top_k=3, auto_route=True)
                # 追加该法律的更多条文
                if "《" in config.violated_law:
                    law_name = config.violated_law.split("》")[0] + "》"
                    more = retriever.search_by_category("", limit=5)
                    # 过滤同名法律
                    related = [l for l in more if l.get("law_name") == law_name]
                    seen = {l.get("law_id") for l in laws}
                    for r in related:
                        if r.get("law_id") not in seen:
                            laws.append(r)
                return laws[:5]

            return retriever.search(query, top_k=5, auto_route=True)
        except Exception:
            logger.exception("案例生成-法规检索失败")
            return []

    # ── 历史案例检索 ──────────────────────────────────────────────────────

    def _retrieve_similar_cases(self, config: CaseGenerationConfig) -> list[Dict[str, Any]]:
        """从 Qdrant 记忆库检索相似历史案例。"""
        try:
            from services.qdrant_memory import get_qdrant_memory

            memory = get_qdrant_memory()
            if not memory.available:
                return []

            parts = [config.violation_behavior, config.case_type, config.violated_law]
            query = " ".join(p for p in parts if p)
            return memory.search(query, top_k=3)
        except Exception:
            logger.exception("案例生成-历史案例检索失败")
            return []

    # ── RAG 上下文构建 ────────────────────────────────────────────────────

    def _build_rag_context(
        self,
        config: CaseGenerationConfig,
        laws: list[Dict[str, Any]],
        cases: list[Dict[str, Any]],
    ) -> str:
        parts: list[str] = []

        if laws:
            parts.append("## 相关法律法规")
            for l in laws:
                parts.append(f"- **{l.get('law_name', '')}** {l.get('article_number', '')}")
                parts.append(f"  {l.get('content', '')[:300]}")
                parts.append("")

        if cases:
            parts.append("## 相似历史案例参考")
            for i, c in enumerate(cases, 1):
                parts.append(f"### 参考案例 {i}")
                parts.append(f"- 案件类型: {c.get('risk_level', '')} 风险")
                parts.append(f"- 原文摘要: {(c.get('query', '') or '')[:200]}")
                if c.get("violations"):
                    v_types = [v.get("type", "") for v in c["violations"] if v.get("type")]
                    if v_types:
                        parts.append(f"- 违规判定: {', '.join(v_types)}")
                parts.append("")

        if not parts:
            parts.append("（无额外参考资料，请基于法律知识生成）")

        return "\n".join(parts)

    # ── Prompt 构建 ───────────────────────────────────────────────────────

    def _build_prompt(self, config: CaseGenerationConfig, rag_context: str) -> str:
        style_guide = {
            "真实案例风格": "模拟真实行政执法案例的写作风格，语言客观、描述具体、包含实际机构名称和量化数据",
            "行政处罚风格": "参照行政处罚决定书格式，包含当事人信息、违法事实、证据列举、处罚依据和决定",
            "法院判决风格": "参照法院裁判文书风格，包含原告诉称、被告诉称、法院查明、法院认为、判决结果",
        }

        parts = [
            "你是一位资深法律案例编写专家，精通中国反垄断法、反不正当竞争法、招标投标法等经济法领域。",
            "",
            "请根据以下条件生成一个真实、合理、有参考价值的法律案例。",
            "严格按 JSON 格式输出，不要输出任何 Markdown 代码块标记以外的文字。",
            "",
            "## 生成条件",
            f"- 违法行为: {config.violation_behavior or '（不限定）'}",
            f"- 违反法条: {config.violated_law or '（自动匹配）'}",
            f"- 案件类型: {config.case_type or '（不限定）'}",
            f"- 风险等级: {config.risk_level or '（自动判断）'}",
            f"- 写作风格: {style_guide.get(config.style, style_guide['真实案例风格'])}",
        ]

        if config.extra_context:
            parts.append(f"- 补充说明: {config.extra_context}")

        parts.append("")
        parts.append(rag_context)

        parts.extend([
            "",
            "## 生成要求",
            "1. 案件逻辑合理、情节完整、主体明确",
            "2. 违法行为描述与引用的法条严格对应",
            "3. 法律分析需引用具体条文并论证构成要件",
            "4. 风险等级判断需有依据",
            "5. 处罚参考需引用法条规定的处罚幅度",
            "",
            "## 输出 JSON Schema",
            "```json",
            "{",
            '  "title": "案例标题（15字以内）",',
            '  "case_type": "案件类型（如政府采购、招标投标、市场竞争等）",',
            '  "violation_behavior": "违法行为（如地域限制、限定交易、串通投标等）",',
            '  "violated_law": "主要违反的法条（如《反垄断法》第四十二条）",',
            '  "risk_level": "高 | 中 | 低",',
            '  "background": "案件背景（150-300字，描述案件发生的时间、地点、涉及主体、行业背景等）",',
            '  "behavior_description": "违法行为描述（150-300字，具体描述违法行为的实施方式、过程、涉及金额等）",',
            '  "subjects": ["涉及主体1", "涉及主体2"],',
            '  "legal_analysis": "法律分析（200-400字，引用法条、分析构成要件、论证违法性）",',
            '  "review_conclusion": "审查结论（100-200字，综合判断违法性、风险等级、建议措施）",',
            '  "penalty_reference": "处罚参考（引用法条规定的具体处罚幅度和方式）",',
            '  "keywords": ["关键词1", "关键词2", "关键词3"]',
            "}",
            "```",
        ])

        return "\n".join(parts)

    # ── 响应解析 ──────────────────────────────────────────────────────────

    def _parse_case(self, content: str) -> Optional[Dict[str, Any]]:
        """从 LLM 输出中提取 JSON 案例。"""
        import re

        strategies = [
            # 1) 直接解析
            lambda s: json.loads(s.strip()),
            # 2) Markdown 代码块
            lambda s: json.loads(re.search(r'```(?:json)?\s*\n?(.*?)\n?```', s, re.DOTALL).group(1).strip()),
            # 3) 首个 { 到末个 }
            lambda s: json.loads(s[s.find("{"):s.rfind("}") + 1]),
        ]

        for strategy in strategies:
            try:
                return strategy(content)
            except (json.JSONDecodeError, AttributeError, ValueError):
                continue

        logger.warning("无法解析 LLM 案例输出: %.200s...", content)
        return None

    # ── 校验 ──────────────────────────────────────────────────────────────

    def _verify(
        self,
        case: Dict[str, Any],
        config: CaseGenerationConfig,
        laws: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """校验生成案例的法条真实性、行为一致性和逻辑合理性。"""
        checks = []
        warnings = []

        # 1) 法条引用真实性
        law_name = case.get("violated_law", "")
        law_found = any(
            law_name in l.get("law_name", "") or any(
                kw in l.get("content", "") for kw in law_name.split("第")[:1] if kw
            )
            for l in laws
        )
        if law_name and law_found:
            checks.append({"check": "法条真实性", "passed": True})
        elif law_name:
            checks.append({"check": "法条真实性", "passed": False, "detail": f"引用的 {law_name} 在检索结果中未找到"})
            warnings.append(f"法条 {law_name} 需人工核实")
        else:
            checks.append({"check": "法条真实性", "passed": True, "detail": "未指定具体法条"})

        # 2) 行为-法条一致性
        if config.violation_behavior and case.get("violation_behavior"):
            behavior_match = config.violation_behavior in case.get("violation_behavior", "")
            checks.append({"check": "行为一致性", "passed": behavior_match})
            if not behavior_match:
                warnings.append(f"生成的行为 '{case.get('violation_behavior')}' 与用户指定 '{config.violation_behavior}' 不一致")

        # 3) 内容完整性
        required_fields = ["title", "case_type", "background", "behavior_description", "legal_analysis", "review_conclusion"]
        for f in required_fields:
            if not case.get(f):
                checks.append({"check": f"字段完整性-{f}", "passed": False})
                warnings.append(f"缺少必要字段: {f}")
            else:
                checks.append({"check": f"字段完整性-{f}", "passed": True})

        # 4) 内容长度检查
        if len(case.get("background", "")) < 50:
            warnings.append("案件背景内容过短")
        if len(case.get("legal_analysis", "")) < 50:
            warnings.append("法律分析内容过短")

        passed = all(c.get("passed", False) for c in checks)
        return {
            "passed": passed,
            "checks": checks,
            "warnings": warnings,
            "overall_score": sum(1 for c in checks if c.get("passed")) / max(len(checks), 1) * 100 if checks else 100,
        }


def build_generated_case_from_dict(data: Dict[str, Any]) -> GeneratedCase:
    """从 dict 构建 GeneratedCase 对象。"""
    return GeneratedCase(
        case_id=data.get("case_id", ""),
        title=data.get("title", ""),
        case_type=data.get("case_type", ""),
        violation_behavior=data.get("violation_behavior", ""),
        violated_law=data.get("violated_law", ""),
        risk_level=data.get("risk_level", ""),
        background=data.get("background", ""),
        behavior_description=data.get("behavior_description", ""),
        subjects=data.get("subjects", []),
        legal_analysis=data.get("legal_analysis", ""),
        review_conclusion=data.get("review_conclusion", ""),
        penalty_reference=data.get("penalty_reference", ""),
        keywords=data.get("keywords", []),
        source=data.get("source", "generated"),
        verified=data.get("verified", False),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
