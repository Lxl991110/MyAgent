"""State models for the LangGraph-based legal research workflow."""

from __future__ import annotations

import operator
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any, List, Optional, Sequence, TypedDict


# ---------------------------------------------------------------------------
# 法律实体 & 结构化案例
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class LegalEntity:
    """NER 抽取出的法律实体。"""

    type: str  # 主体 | 行为 | 条文 | 金额 | 时间 | 地域 | 风险关键词
    value: str
    confidence: float = field(default=1.0)
    span: tuple[int, int] | None = field(default=None)


@dataclass(kw_only=True)
class StructuredCase:
    """标准化后的案例结构。"""

    case_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    case_type: str = ""  # 滥用市场支配地位 / 不正当竞争 / 行政垄断 / 其他
    subjects: list[str] = field(default_factory=list)
    behaviors: list[str] = field(default_factory=list)
    amount: str = ""
    region: str = ""
    time_period: str = ""
    related_laws: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    description: str = ""
    raw_text: str = ""


@dataclass(kw_only=True)
class CaseParseResult:
    """案例解析的完整输出。"""

    success: bool = True
    entities: list[LegalEntity] = field(default_factory=list)
    structured_case: StructuredCase | None = None
    preprocess_info: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 法条条目
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class LawArticle:
    """单条法律条文。"""

    law_id: str
    law_name: str  # e.g. 《反垄断法》
    article_number: str  # e.g. 第二十二条
    content: str
    chapter: str = ""
    enforcement_level: str = ""  # 法律 | 行政法规 | 部门规章 | 司法解释
    issuing_authority: str = ""


# ---------------------------------------------------------------------------
# 知识库条目
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class CaseLawLink:
    """案例 ↔ 法条关联记录。"""

    case_id: str
    law_ids: list[str]
    similarity_scores: dict[str, float] = field(default_factory=dict)
    match_method: str = "keyword"  # keyword | vector


# ---------------------------------------------------------------------------
# 工作流状态（已有）
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class TodoItem:
    """单个待办任务项。"""

    id: int
    title: str
    intent: str
    query: str
    status: str = field(default="pending")
    summary: Optional[str] = field(default=None)
    sources_summary: Optional[str] = field(default=None)
    notices: list[str] = field(default_factory=list)


class ResearchState(TypedDict, total=False):
    """LangGraph 工作流共享状态。

    使用 Annotated[list, operator.add] 实现累加式 reducer，
    各节点返回的列表字段会自动追加而非覆盖。
    """

    research_topic: str
    todo_items: List[dict[str, Any]]
    web_research_results: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]
    research_loop_count: int
    running_summary: str
    structured_report: str
    stream_events: Annotated[list, operator.add]
    # 案例解析扩展字段
    case_text: str
    parse_result: Optional[dict[str, Any]]


@dataclass(kw_only=True)
class SummaryStateOutput:
    """对外输出的研究结果。"""

    running_summary: str = field(default="")
    report_markdown: Optional[str] = field(default=None)
    todo_items: List[TodoItem] = field(default_factory=list)
    case_parse_result: Optional[CaseParseResult] = field(default=None)
