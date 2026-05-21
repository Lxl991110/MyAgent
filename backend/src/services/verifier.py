"""验证代理 —— 对生成报告进行事实核查、一致性校验和违法检测。

输出 VerificationResult，包含通过/未通过标记、警告和修正建议。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from models import VerificationResult

logger = logging.getLogger(__name__)

# ── 违法行为关键词库 ─────────────────────────────────────────────────────────

_VIOLATION_KEYWORDS: Dict[str, Dict[str, Any]] = {
    "滥用市场支配地位": {
        "keywords": [
            "限定交易", "拒绝交易", "搭售", "附加不合理条件",
            "差别待遇", "不公平高价", "掠夺性定价", "独家交易",
            "二选一", "大数据杀熟", "自我优待", "排他性协议",
        ],
        "laws": ["《反垄断法》第二十二条", "《反垄断法》第二十三条"],
        "severity": "★★★",
    },
    "垄断协议": {
        "keywords": [
            "固定价格", "限制产量", "分割市场", "联合抵制",
            "串通投标", "价格联盟", "横向垄断", "纵向垄断",
        ],
        "laws": ["《反垄断法》第十六条", "《反垄断法》第十七条"],
        "severity": "★★★",
    },
    "不正当竞争": {
        "keywords": [
            "混淆行为", "商业贿赂", "虚假宣传", "侵犯商业秘密",
            "商业诋毁", "不正当有奖销售", "刷单", "恶意不兼容",
        ],
        "laws": ["《反不正当竞争法》第六条至第十二条"],
        "severity": "★★☆",
    },
}


class VerificationAgent:
    """法律研究报告验证代理。

    执行三项检查：
    1. 法条有效性 — 引用的法条是否真实存在
    2. 事实一致性 — 报告事实是否与输入案例一致
    3. 违法行为检测 — 输入案例中是否存在违法关键词
    """

    def verify(
        self,
        report: str,
        *,
        case_parse_info: Optional[Dict[str, Any]] = None,
        retrieved_laws: Optional[list[Any]] = None,
        original_case_text: str = "",
    ) -> VerificationResult:
        """执行全量验证，返回 VerificationResult。"""
        result = VerificationResult()

        # 1. 法条有效性
        result.law_validity = self._check_law_validity(report, retrieved_laws or [])

        # 2. 事实一致性（比对案例原文与报告）
        if case_parse_info and original_case_text:
            result.fact_consistency = self._check_fact_consistency(
                report, case_parse_info, original_case_text
            )
        else:
            result.fact_consistency = {"status": "skipped", "reason": "无原始案例信息"}

        # 3. 违法行为检测
        if case_parse_info or original_case_text:
            source_text = original_case_text or str(case_parse_info or "")
            result.violation_detection = self.detect_violations(
                source_text, case_parse_info
            )
        else:
            result.violation_detection = {"status": "skipped", "reason": "无案例文本"}

        # 综合评分
        result.overall_score = self._compute_score(result)
        result.passed = result.overall_score >= 60.0

        return result

    def _check_law_validity(
        self,
        report: str,
        retrieved_laws: list[Any],
    ) -> Dict[str, Any]:
        """检查报告中引用的法条是否在检索结果或知识库中。"""
        import re

        pattern = re.compile(r"《([^》]+)》\s*第?\s*([零一二三四五六七八九十百千\d]+)\s*条")
        refs = pattern.findall(report)

        known_laws: set[str] = set()
        for rl in retrieved_laws:
            if hasattr(rl, "law_name"):
                known_laws.add(rl.law_name)

        verified: list[dict] = []
        unknown: list[dict] = []
        for law_name, art in refs:
            if law_name in known_laws:
                verified.append({"law": f"《{law_name}》第{art}条"})
            else:
                unknown.append({"law": f"《{law_name}》第{art}条"})

        return {
            "total_citations": len(refs),
            "verified": len(verified),
            "unknown": len(unknown),
            "verified_list": verified,
            "unknown_list": unknown,
            "all_verified": len(unknown) == 0,
        }

    def _check_fact_consistency(
        self,
        report: str,
        case_parse_info: Dict[str, Any],
        original_text: str,
    ) -> Dict[str, Any]:
        """检查报告中的关键事实是否与案例解析结果一致。"""
        checks: list[dict] = []

        # 案由一致
        ct = case_parse_info.get("case_type", "")
        if ct and ct in report:
            checks.append({"item": "案由", "match": True, "detail": ct})
        elif ct:
            checks.append({"item": "案由", "match": False, "detail": f"报告中未找到案由 '{ct}'"})

        # 主体一致
        subjects = case_parse_info.get("subjects", [])
        for s in subjects:
            checks.append({
                "item": "主体",
                "value": s,
                "match": s in report,
                "detail": "已找到" if s in report else "报告中缺失",
            })

        # 法条一致
        related = case_parse_info.get("related_laws", [])
        for law_ref in related:
            law_name = law_ref.split("第")[0].replace("《", "").replace("》", "") if "第" in law_ref else law_ref
            checks.append({
                "item": "法条",
                "value": law_ref,
                "match": law_name in report,
                "detail": "已引用" if law_name in report else "报告中未引用",
            })

        match_count = sum(1 for c in checks if c.get("match"))
        return {
            "total_checks": len(checks),
            "match_count": match_count,
            "consistency_score": round(match_count / max(len(checks), 1) * 100, 1),
            "checks": checks,
        }

    def detect_violations(
        self,
        text: str,
        case_parse_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """基于关键词检测潜在的违法行为。"""
        detected: list[dict] = []

        for violation_type, config in _VIOLATION_KEYWORDS.items():
            matched: list[str] = []
            for kw in config["keywords"]:
                if kw in text:
                    matched.append(kw)
            if matched:
                detected.append({
                    "type": violation_type,
                    "matched_keywords": matched,
                    "count": len(matched),
                    "relevant_laws": config["laws"],
                    "severity": config["severity"],
                })

        # 确定最高严重等级
        max_severity = "—"
        if detected:
            severities = [d["severity"] for d in detected]
            if "★★★" in severities:
                max_severity = "★★★"
            elif "★★☆" in severities:
                max_severity = "★★☆"
            else:
                max_severity = "★☆☆"

        return {
            "violations_detected": len(detected),
            "max_severity": max_severity,
            "details": detected,
        }

    def _compute_score(self, result: VerificationResult) -> float:
        """计算综合验证分数 (0-100)。"""
        score = 100.0

        # 法条验证扣分
        lv = result.law_validity
        if lv.get("total_citations", 0) > 0:
            unknown_rate = lv.get("unknown", 0) / max(lv.get("total_citations", 1), 1)
            score -= unknown_rate * 30

        # 事实一致性扣分
        fc = result.fact_consistency
        if fc.get("total_checks", 0) > 0:
            score -= (100 - fc.get("consistency_score", 100)) * 0.3

        # 违法检测（发现问题反而加分——说明检测到位）
        vd = result.violation_detection
        if vd.get("violations_detected", 0) > 0:
            score = min(score + 5, 100.0)

        return max(round(score, 1), 0.0)
