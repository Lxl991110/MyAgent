"""State models for the LangGraph-based legal research workflow."""

from __future__ import annotations

import operator
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any, List, Literal, Optional, Sequence, TypedDict


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
    category: str = ""  # 公平竞争 | 政府采购 | 招投标 | 市场监管 | 行政处罚 | 企业经营 | 价格垄断 | 不正当竞争
    keywords: list[str] = field(default_factory=list)
    enforcement_level: str = ""  # 法律 | 行政法规 | 部门规章 | 司法解释
    issuing_authority: str = ""
    source: str = "official"
    updated_at: str = ""


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
# RAG 检索 & 验证结果 (新增)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class RetrievedLaw:
    """RAG 检索到的法条及其相似度。"""

    law_id: str
    law_name: str
    article_number: str
    content: str
    chapter: str = ""
    enforcement_level: str = ""
    score: float = 0.0
    retrieval_method: str = "vector"  # vector | keyword | hybrid


@dataclass(kw_only=True)
class RetrievedCase:
    """RAG 检索到的案例及其相似度。"""

    case_id: str
    case_type: str
    subjects: list[str] = field(default_factory=list)
    behaviors: list[str] = field(default_factory=list)
    related_laws: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    description: str = ""
    score: float = 0.0
    retrieval_method: str = "vector"


@dataclass(kw_only=True)
class VerificationResult:
    """验证代理输出：事实核查 + 一致性检查 + 违规检测。"""

    # 法条有效性
    law_validity: dict[str, Any] = field(default_factory=dict)
    # 事实一致性
    fact_consistency: dict[str, Any] = field(default_factory=dict)
    # 违法行为检测
    violation_detection: dict[str, Any] = field(default_factory=dict)
    # 综合评分 (0-100)
    overall_score: float = 0.0
    # 修正建议
    corrections: list[str] = field(default_factory=list)
    # 警告
    warnings: list[str] = field(default_factory=list)
    # 是否通过验证
    passed: bool = True


# ---------------------------------------------------------------------------
# 工作流状态
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

    工作流: case_parse → plan → search → summarize → retrieve → generate → verify → report
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
    # ── RAG + MCP 扩展字段 ──
    retrieved_laws: Annotated[list, operator.add]
    retrieved_cases: Annotated[list, operator.add]
    rag_context: str
    generation_result: Optional[dict[str, Any]]
    verification_result: Optional[dict[str, Any]]


@dataclass(kw_only=True)
class SummaryStateOutput:
    """对外输出的研究结果。"""

    running_summary: str = field(default="")
    report_markdown: Optional[str] = field(default=None)
    todo_items: List[TodoItem] = field(default_factory=list)
    case_parse_result: Optional[CaseParseResult] = field(default=None)
    verification_result: Optional[VerificationResult] = field(default=None)
    retrieved_laws: list[RetrievedLaw] = field(default_factory=list)
    retrieved_cases: list[RetrievedCase] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 案例生成
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class CaseGenerationConfig:
    """案例生成配置 — 用户可控的生成条件。"""

    violation_behavior: str = ""  # 违法行为，如"地域限制"
    violated_law: str = ""  # 违反法条，如"《反垄断法》第四十二条"
    case_type: str = ""  # 案件类型，如"政府采购"
    risk_level: str = ""  # 风险等级：高/中/低 (空=自动判断)
    style: str = "真实案例风格"  # 真实案例风格 | 行政处罚风格 | 法院判决风格
    extra_context: str = ""  # 额外补充描述


@dataclass(kw_only=True)
class GeneratedCase:
    """LLM 生成的案例结构化输出。"""

    case_id: str = ""
    title: str = ""  # 案例标题
    case_type: str = ""  # 案件类型
    violation_behavior: str = ""  # 违法行为
    violated_law: str = ""  # 违反法条
    risk_level: str = ""  # 风险等级
    background: str = ""  # 案件背景
    behavior_description: str = ""  # 违法行为描述
    subjects: list[str] = field(default_factory=list)  # 涉及主体
    legal_analysis: str = ""  # 法律分析
    review_conclusion: str = ""  # 审查结论
    penalty_reference: str = ""  # 处罚参考
    keywords: list[str] = field(default_factory=list)
    source: str = "generated"  # generated | verified | imported
    verified: bool = False
    created_at: str = ""


class CaseGenerationState(TypedDict, total=False):
    """案例生成 LangGraph 状态。"""

    config: CaseGenerationConfig
    user_message: str  # 用户自然语言输入
    retrieved_laws: list[dict[str, Any]]
    retrieved_cases: list[dict[str, Any]]
    rag_context: str
    prompt: str
    generated_case: Optional[dict[str, Any]]
    verification_result: Optional[dict[str, Any]]
    stream_events: Annotated[list, operator.add]
