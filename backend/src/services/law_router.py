"""法规路由器 — 分析用户查询，识别法律领域分类，引导优先检索路径。

分类体系: 公平竞争 | 政府采购 | 招投标 | 市场监管 | 行政处罚 | 企业经营 | 价格垄断 | 不正当竞争
"""

from __future__ import annotations

import re
from typing import List, Optional

from data.laws import CATEGORY_LAW_MAP, LAW_CATEGORIES

# 分类 → 关键词映射（用于查询文本匹配）
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "公平竞争": [
        "公平竞争", "市场支配", "垄断", "独家", "排他", "限定交易", "拒绝交易",
        "差别待遇", "搭售", "二选一", "经营者集中", "行政垄断", "地方保护",
    ],
    "不正当竞争": [
        "不正当竞争", "虚假宣传", "混淆", "商业诋毁", "商业秘密", "刷单",
        "商业贿赂", "搭便车", "有奖销售", "误导", "网络不正当竞争",
    ],
    "招投标": [
        "招标", "投标", "中标", "串通投标", "围标", "评标", "招标文件",
        "资格审查", "投标人", "招标人", "低于成本报价",
    ],
    "政府采购": [
        "政府采购", "采购人", "供应商", "采购文件", "采购代理", "集中采购",
    ],
    "价格垄断": [
        "价格", "定价", "转售价格", "固定价格", "低价倾销", "掠夺性定价",
        "价格歧视", "哄抬价格", "不公平高价", "不公平低价", "暴利",
    ],
    "市场监管": [
        "市场份额", "市场准入", "监管", "申报", "审查", "备案",
    ],
    "企业经营": [
        "合并", "收购", "股权", "控制权", "集中", "合营", "电子商务平台",
        "平台经营者", "服务协议", "交易规则",
    ],
    "行政处罚": [
        "处罚", "罚款", "没收", "责令", "吊销", "赔偿", "法律责任",
        "停止违法行为",
    ],
}

# 法律法规名称 ← 查询中直接提及的法名
_LAW_NAME_ALIASES: dict[str, str] = {
    "反垄断": "《反垄断法》",
    "反不正当竞争": "《反不正当竞争法》",
    "招标投标": "《招标投标法》",
    "政府采购": "《政府采购法》",
    "价格法": "《价格法》",
    "电子商务": "《电子商务法》",
    "行政处罚法": "《行政处罚法》",
}


class LawRouter:
    """法规路由器 — 根据查询内容选择最优检索路径。"""

    @staticmethod
    def categorize(query: str) -> List[str]:
        """分析查询文本，返回匹配的分类列表（按相关度排序）。"""
        scores: dict[str, float] = {}
        for category, keywords in _CATEGORY_KEYWORDS.items():
            score = 0.0
            for kw in keywords:
                if kw in query:
                    score += 1.0
            if score > 0:
                scores[category] = score

        return sorted(scores, key=scores.get, reverse=True)

    @staticmethod
    def detect_law_name(query: str) -> Optional[str]:
        """检测查询中是否明确提到了某部法律。"""
        for alias, law_name in _LAW_NAME_ALIASES.items():
            if alias in query:
                return law_name
        return None

    @staticmethod
    def route(query: str) -> dict:
        """路由分析结果 — 返回推荐的检索参数。

        Returns:
            {
                "categories": [...],        # 优先分类
                "preferred_laws": [...],     # 优先检索的法律
                "detected_law_name": "...",  # 明确提及的法律（如有）
                "suggested_filter": {...},   # 建议的 Qdrant 过滤条件
            }
        """
        categories = LawRouter.categorize(query)
        detected_law = LawRouter.detect_law_name(query)

        # 确定优先检索的法律
        preferred_laws: List[str] = []
        if detected_law:
            preferred_laws = [detected_law]
        else:
            seen: set[str] = set()
            for cat in categories[:3]:
                for law in CATEGORY_LAW_MAP.get(cat, []):
                    if law not in seen:
                        preferred_laws.append(law)
                        seen.add(law)

        # 构建 Qdrant 过滤条件
        suggested_filter: dict = {}
        if detected_law:
            suggested_filter = {
                "must": [{"key": "law_name", "match": {"value": detected_law}}]
            }
        elif categories:
            # 按分类过滤
            if len(categories) >= 2:
                suggested_filter = {
                    "should": [
                        {"key": "category", "match": {"value": c}} for c in categories[:3]
                    ]
                }

        return {
            "categories": categories,
            "preferred_laws": preferred_laws,
            "detected_law_name": detected_law,
            "suggested_filter": suggested_filter,
        }


# 全局单例
_law_router: Optional[LawRouter] = None


def get_law_router() -> LawRouter:
    global _law_router
    if _law_router is None:
        _law_router = LawRouter()
    return _law_router
