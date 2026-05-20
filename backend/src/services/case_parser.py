"""
案例结构化解析与知识建模模块。

子模块:
  1. 法律文本预处理   — 清洗、分句、分段
  2. BERT + NER 实体抽取 — 正则 + 关键词 (可选 BERT 增强)
  3. 案例属性结构化     — NER 结果 → 标准化 JSON
  4. 案例‑法条知识库    — 存储 + 向量检索 (可选 FAISS)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from models import CaseLawLink, CaseParseResult, LawArticle, LegalEntity, StructuredCase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. 法律文本预处理
# ---------------------------------------------------------------------------

# 中英文标点 → 统一中文标点
_PUNCT_NORMALIZE = str.maketrans(
    "(),;:!?\"'",
    "（），；：！？""''",
)


def preprocess_case_text(raw: str) -> dict[str, Any]:
    """清洗 + 分句 + 分段，返回可供 NER 使用的文本与元信息。"""

    # 基本清洗
    text = raw.strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)  # 合并多余空行
    text = re.sub(r"[ 　\t]+", "", text)  # 去空格 / 全角空格
    text = text.translate(_PUNCT_NORMALIZE)

    # 分句（中英文句号 / 换行 / 分号断句）
    sentences = re.split(r"(?<=[。！？；\n])(?=[^。！？；\n])", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # 简单分段（按双换行或长度阈值）
    paragraphs: list[str] = []
    buf = ""
    for s in sentences:
        if buf and (buf.endswith("\n") or len(buf) > 200):
            paragraphs.append(buf.strip())
            buf = s
        else:
            buf = (buf + s) if buf else s
    if buf.strip():
        paragraphs.append(buf.strip())

    return {
        "clean_text": text,
        "sentences": sentences,
        "paragraphs": paragraphs,
        "char_count": len(text),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
    }


# ---------------------------------------------------------------------------
# 2. BERT + NER 命名实体识别（正则引擎 + 可选 BERT）
# ---------------------------------------------------------------------------

# ── 正则模式库 ─────────────────────────────────────────────────────────────

_LAW_REF_PATTERN = re.compile(
    r"《(?P<name>[^》]{1,30})》"
    r"(?:第(?P<article>[一二三四五六七八九十百千零\d]+)条)?"
    r"(?:第(?P<para>[一二三四五六七八九十百千零\d]+)款)?",
)

_AMOUNT_PATTERN = re.compile(
    r"(?P<amount>\d[\d,.]*(?:万|亿|千|百)?(?:元|美元|欧元|日元|英镑|人民币))"
    r"|(?:(?:人民币)?\d[\d,.]*(?:万|亿)?(?:余)?(?:元))",
)

_SUBJECT_PATTERNS = [
    re.compile(r"(?P<subj>[一-鿿]{2,8}(?:公司|集团|有限(?:责任)?公司|股份(?:有限)?公司|厂|商店|平台))"),
    re.compile(r"(?P<subj>[一-鿿]{2,10}(?:局|厅|委|部|署|院|办|处|所))"),
    re.compile(r"(?P<subj>[一-鿿]{2,6}(?:经营者|当事人|原告|被告|申请人|被申请人|第三人))"),
]

# 行为关键词 → 行为分类
_BEHAVIOR_KEYWORDS: dict[str, list[str]] = {
    "滥用市场支配地位": [
        "滥用市场支配", "市场支配地位", "限定交易", "拒绝交易", "搭售",
        "附加不合理条件", "差别待遇", "不公平高价", "不公平低价",
        "低于成本销售", "掠夺性定价", "独家交易", "排他性协议",
    ],
    "垄断协议": [
        "垄断协议", "横向垄断", "纵向垄断", "固定价格", "划分市场",
        "联合抵制", "串通投标", "价格同盟", "限制产量",
    ],
    "经营者集中": [
        "经营者集中", "合并", "收购", "集中申报", "控制权取得",
        "未依法申报", "先集中后申报",
    ],
    "行政垄断": [
        "行政垄断", "滥用行政权力", "行政性限制", "地方保护",
        "指定交易", "妨碍商品流通", "限制公平竞争",
    ],
    "不正当竞争": [
        "不正当竞争", "虚假宣传", "商业诋毁", "侵犯商业秘密",
        "商业贿赂", "混淆行为", "有奖销售", "不正当有奖销售",
    ],
    "补贴与补贴协议": [
        "补贴", "财政补贴", "税收优惠", "选择性补贴", "专项补贴",
        "政府补助", "政策性补贴",
    ],
}

# 风险关键词
_RISK_KEYWORDS = [
    "违法", "违规", "不合规", "处罚", "罚款", "责令改正", "吊销",
    "涉嫌", "立案调查", "约谈", "整改", "警告", "严重违法",
    "刑事责任", "民事赔偿", "行政处罚",
]

# 地域
_REGION_PATTERN = re.compile(
    r"(?P<region>[一-鿿]{2,4}(?:省|市|自治区|县|区|新区|开发区))"
)

# 时间
_TIME_PATTERN = re.compile(
    r"(?P<time>\d{4}年\d{1,2}月(?:\d{1,2}日)?)"
    r"|(?P<time_range>\d{4}年(?:\d{1,2}月)?[至到\-~]\d{4}年(?:\d{1,2}月)?)",
)


def _extract_entities_regex(text: str) -> list[LegalEntity]:
    """基于正则 + 关键词的实体抽取。"""

    entities: list[LegalEntity] = []

    # ── 法律条文 ──
    for m in _LAW_REF_PATTERN.finditer(text):
        law_name = f"《{m.group('name')}》"
        article = m.group("article")
        para = m.group("para")
        value = law_name
        if article:
            value += f"第{article}条"
        if para:
            value += f"第{para}款"
        entities.append(LegalEntity(
            type="条文", value=value, confidence=0.95,
            span=(m.start(), m.end()),
        ))

    # ── 金额 ──
    for m in _AMOUNT_PATTERN.finditer(text):
        entities.append(LegalEntity(
            type="金额", value=m.group().strip(), confidence=0.9,
            span=(m.start(), m.end()),
        ))

    # ── 主体 ──
    seen_subjects: set[str] = set()
    for pat in _SUBJECT_PATTERNS:
        for m in pat.finditer(text):
            val = m.group("subj")
            if val not in seen_subjects:
                seen_subjects.add(val)
                entities.append(LegalEntity(
                    type="主体", value=val, confidence=0.85,
                    span=(m.start(), m.end()),
                ))

    # ── 行为 ──
    seen_behaviors: set[str] = set()
    for category, keywords in _BEHAVIOR_KEYWORDS.items():
        for kw in keywords:
            start = 0
            while True:
                idx = text.find(kw, start)
                if idx == -1:
                    break
                if kw not in seen_behaviors:
                    seen_behaviors.add(kw)
                    entities.append(LegalEntity(
                        type="行为", value=kw,
                        confidence=0.8,
                        span=(idx, idx + len(kw)),
                    ))
                start = idx + 1

    # ── 地域 ──
    for m in _REGION_PATTERN.finditer(text):
        entities.append(LegalEntity(
            type="地域", value=m.group("region"), confidence=0.85,
            span=(m.start(), m.end()),
        ))

    # ── 时间 ──
    for m in _TIME_PATTERN.finditer(text):
        entities.append(LegalEntity(
            type="时间", value=m.group().strip(), confidence=0.9,
            span=(m.start(), m.end()),
        ))

    # ── 风险关键词 ──
    for kw in _RISK_KEYWORDS:
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx == -1:
                break
            entities.append(LegalEntity(
                type="风险关键词", value=kw, confidence=0.75,
                span=(idx, idx + len(kw)),
            ))
            start = idx + 1

    return entities


def _deduplicate_entities(entities: list[LegalEntity]) -> list[LegalEntity]:
    """按 (type, value) 去重，保留置信度最高的。"""

    dedup: dict[tuple[str, str], LegalEntity] = {}
    for e in entities:
        key = (e.type, e.value)
        if key not in dedup or e.confidence > dedup[key].confidence:
            dedup[key] = e
    return sorted(dedup.values(), key=lambda e: (e.type, e.value))


# ── 可选 BERT 增强入口 ──────────────────────────────────────────────────────

_BERT_NER_AVAILABLE = None  # 惰性检测


def _check_bert_available() -> bool:
    global _BERT_NER_AVAILABLE

    if _BERT_NER_AVAILABLE is not None:
        return _BERT_NER_AVAILABLE

    try:
        import torch  # noqa: F401

        from transformers import AutoModelForTokenClassification, AutoTokenizer  # noqa: F401

        _BERT_NER_AVAILABLE = True
        logger.info("transformers + torch 可用，BERT NER 已启用")
    except ImportError:
        _BERT_NER_AVAILABLE = False
        logger.info("transformers 或 torch 未安装，使用正则 NER 引擎")

    return _BERT_NER_AVAILABLE


# 轻量级中文法律 NER 模型（可在部署时替换为微调模型）
_LEGAL_NER_MODEL = "raynardj/ner-gnn-chinese-fine-grained"


def _extract_entities_bert(text: str) -> list[LegalEntity]:
    """使用 HuggingFace BERT 模型进行 NER。"""

    if not _check_bert_available():
        return []

    try:
        from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
    except ImportError:
        return []

    try:
        tokenizer = AutoTokenizer.from_pretrained(_LEGAL_NER_MODEL)
        model = AutoModelForTokenClassification.from_pretrained(_LEGAL_NER_MODEL)
        ner_pipeline = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy="simple")
        raw_entities = ner_pipeline(text[:2000])  # 截断长文本

        type_map = {
            "PER": "主体",
            "ORG": "主体",
            "LOC": "地域",
            "TIME": "时间",
            "MISC": "风险关键词",
        }

        entities: list[LegalEntity] = []
        for item in raw_entities:
            ent_type = type_map.get(item.get("entity_group", ""), "风险关键词")
            entities.append(LegalEntity(
                type=ent_type,
                value=item["word"],
                confidence=float(item.get("score", 0.7)),
                span=(item.get("start", 0), item.get("end", 0)),
            ))
        return entities

    except Exception as exc:
        logger.warning("BERT NER 失败，回退到正则引擎: %s", exc)
        return []


def extract_entities(text: str, *, use_bert: bool = True) -> list[LegalEntity]:
    """主入口：抽取法律实体（正则 + 可选 BERT 融合）。"""

    regex_entities = _extract_entities_regex(text)

    bert_entities: list[LegalEntity] = []
    if use_bert:
        bert_entities = _extract_entities_bert(text)

    all_entities = regex_entities + bert_entities
    return _deduplicate_entities(all_entities)


# ---------------------------------------------------------------------------
# 3. 案例属性结构化
# ---------------------------------------------------------------------------

# 行为关键词 → 案例类型映射
_BEHAVIOR_TO_CASE_TYPE: dict[str, str] = {}
for _ct, _kws in _BEHAVIOR_KEYWORDS.items():
    for _kw in _kws:
        _BEHAVIOR_TO_CASE_TYPE[_kw] = _ct


def _classify_case_type(entities: list[LegalEntity], text: str) -> tuple[str, float]:
    """综合实体与文本判断案例类型。"""

    scores: dict[str, int] = {}
    for e in entities:
        if e.type == "行为" and e.value in _BEHAVIOR_TO_CASE_TYPE:
            ct = _BEHAVIOR_TO_CASE_TYPE[e.value]
            scores[ct] = scores.get(ct, 0) + 1

    # 从 full text 中扫描补充
    for ct, keywords in _BEHAVIOR_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[ct] = scores.get(ct, 0) + 1

    if not scores:
        return "其他", 0.3

    best = max(scores, key=lambda k: scores[k])  # type: ignore[arg-type]
    total = sum(scores.values())
    confidence = min(scores[best] / max(total, 1), 1.0)
    return best, round(confidence, 2)


def _extract_subjects(entities: list[LegalEntity]) -> list[str]:
    return sorted({e.value for e in entities if e.type == "主体"})


def _extract_behaviors(entities: list[LegalEntity]) -> list[str]:
    return sorted({e.value for e in entities if e.type == "行为"})


def _extract_laws(entities: list[LegalEntity]) -> list[str]:
    return sorted({e.value for e in entities if e.type == "条文"})


def _extract_single(entities: list[LegalEntity], ent_type: str) -> str:
    values = [e.value for e in entities if e.type == ent_type]
    return values[0] if values else ""


def _extract_risk_tags(entities: list[LegalEntity]) -> list[str]:
    return sorted({e.value for e in entities if e.type == "风险关键词"})


def _build_description(structured: StructuredCase) -> str:
    parts: list[str] = []
    if structured.subjects:
        parts.append(f"涉事主体: {'、'.join(structured.subjects)}")
    if structured.behaviors:
        parts.append(f"核心行为: {'、'.join(structured.behaviors)}")
    if structured.amount:
        parts.append(f"涉案金额: {structured.amount}")
    if structured.region:
        parts.append(f"地域: {structured.region}")
    if structured.related_laws:
        parts.append(f"相关法条: {'、'.join(structured.related_laws)}")
    return "；".join(parts)


def structure_case(
    raw_text: str,
    entities: list[LegalEntity],
) -> StructuredCase:
    """将 NER 结果转换为标准 StructuredCase。"""

    case_type, _ = _classify_case_type(entities, raw_text)
    subjects = _extract_subjects(entities)
    behaviors = _extract_behaviors(entities)
    related_laws = _extract_laws(entities)
    amount = _extract_single(entities, "金额")
    region = _extract_single(entities, "地域")
    time_period = _extract_single(entities, "时间")
    risk_tags = _extract_risk_tags(entities)

    case = StructuredCase(
        case_type=case_type,
        subjects=subjects,
        behaviors=behaviors,
        amount=amount,
        region=region,
        time_period=time_period,
        related_laws=related_laws,
        risk_tags=risk_tags,
        raw_text=raw_text,
    )
    case.description = _build_description(case)
    return case


# ---------------------------------------------------------------------------
# 4. 案例‑法条关联知识库
# ---------------------------------------------------------------------------


# 内置法律条文库（反垄断法）
_BUILTIN_LAWS: list[LawArticle] = [
    LawArticle(law_id="aml_01", law_name="《反垄断法》", article_number="第二十二条",
               content="禁止具有市场支配地位的经营者从事下列滥用市场支配地位的行为：（一）以不公平的高价销售商品或者以不公平的低价购买商品；（二）没有正当理由，以低于成本的价格销售商品；（三）没有正当理由，拒绝与交易相对人进行交易；（四）没有正当理由，限定交易相对人只能与其进行交易或者只能与其指定的经营者进行交易；（五）没有正当理由搭售商品，或者在交易时附加其他不合理的交易条件；（六）没有正当理由，对条件相同的交易相对人在交易价格等交易条件上实行差别待遇；（七）国务院反垄断执法机构认定的其他滥用市场支配地位的行为。",
               chapter="第三章 滥用市场支配地位", enforcement_level="法律", issuing_authority="全国人大常委会"),
    LawArticle(law_id="aml_02", law_name="《反垄断法》", article_number="第十七条",
               content="禁止具有竞争关系的经营者达成下列垄断协议：（一）固定或者变更商品价格；（二）限制商品的生产数量或者销售数量；（三）分割销售市场或者原材料采购市场；（四）限制购买新技术、新设备或者限制开发新技术、新产品；（五）联合抵制交易；（六）国务院反垄断执法机构认定的其他垄断协议。",
               chapter="第二章 垄断协议", enforcement_level="法律", issuing_authority="全国人大常委会"),
    LawArticle(law_id="aml_03", law_name="《反垄断法》", article_number="第二十六条",
               content="经营者集中达到国务院规定的申报标准的，经营者应当事先向国务院反垄断执法机构申报，未申报的不得实施集中。",
               chapter="第四章 经营者集中", enforcement_level="法律", issuing_authority="全国人大常委会"),
    LawArticle(law_id="aml_04", law_name="《反垄断法》", article_number="第四十二条",
               content="经营者违反本法规定，达成并实施垄断协议的，由反垄断执法机构责令停止违法行为，没收违法所得，并处上一年度销售额百分之一以上百分之十以下的罚款；尚未实施所达成的垄断协议的，可以处五十万元以下的罚款。",
               chapter="第七章 法律责任", enforcement_level="法律", issuing_authority="全国人大常委会"),
    LawArticle(law_id="auc_01", law_name="《反不正当竞争法》", article_number="第二条",
               content="经营者在生产经营活动中，应当遵循自愿、平等、公平、诚信的原则，遵守法律和商业道德。本法所称的不正当竞争行为，是指经营者在生产经营活动中，违反本法规定，扰乱市场竞争秩序，损害其他经营者或者消费者的合法权益的行为。",
               enforcement_level="法律", issuing_authority="全国人大常委会"),
    LawArticle(law_id="auc_02", law_name="《反不正当竞争法》", article_number="第八条",
               content="经营者不得对其商品的性能、功能、质量、销售状况、用户评价、曾获荣誉等作虚假或者引人误解的商业宣传，欺骗、误导消费者。经营者不得通过组织虚假交易等方式，帮助其他经营者进行虚假或者引人误解的商业宣传。",
               enforcement_level="法律", issuing_authority="全国人大常委会"),
    LawArticle(law_id="auc_03", law_name="《反不正当竞争法》", article_number="第十二条",
               content="经营者利用网络从事生产经营活动，应当遵守本法的各项规定。经营者不得利用技术手段，通过影响用户选择或者其他方式，实施妨碍、破坏其他经营者合法提供的网络产品或者服务正常运行的行为。",
               enforcement_level="法律", issuing_authority="全国人大常委会"),
]


class CaseLawKnowledgeBase:
    """案例‑法条关联知识库。

    支持关键词匹配检索 + 可选 FAISS 向量检索。
    """

    def __init__(self) -> None:
        self._cases: dict[str, StructuredCase] = {}
        self._laws: dict[str, LawArticle] = {l.law_id: l for l in _BUILTIN_LAWS}
        self._links: dict[str, CaseLawLink] = {}
        self._faiss_index: Any = None
        self._faiss_available: bool = False
        self._init_faiss()

    # ── FAISS 向量检索（可选） ──────────────────────────────────────────

    def _init_faiss(self) -> None:
        try:
            import numpy as np

            import faiss

            self._faiss_available = True
            logger.info("FAISS 向量检索已启用")
        except ImportError:
            self._faiss_available = False
            logger.info("FAISS 未安装，使用关键词匹配检索")

    def _embed_text(self, text: str) -> Any:
        """将文本转为向量。"""

        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            return model.encode([text])[0]
        except ImportError:
            return None

    # ── CRUD ────────────────────────────────────────────────────────────

    def add_case(self, case: StructuredCase) -> str:
        self._cases[case.case_id] = case
        self._link_case_to_laws(case.case_id)
        if self._faiss_available:
            self._index_case_vector(case)
        return case.case_id

    def add_law(self, law: LawArticle) -> str:
        self._laws[law.law_id] = law
        return law.law_id

    def get_case(self, case_id: str) -> StructuredCase | None:
        return self._cases.get(case_id)

    def get_law(self, law_id: str) -> LawArticle | None:
        return self._laws.get(law_id)

    def list_cases(self) -> list[StructuredCase]:
        return list(self._cases.values())

    def list_laws(self) -> list[LawArticle]:
        return list(self._laws.values())

    # ── 关联匹配 ─────────────────────────────────────────────────────────

    def _link_case_to_laws(self, case_id: str) -> CaseLawLink | None:
        case = self._cases.get(case_id)
        if not case:
            return None

        linked_ids: list[str] = []
        scores: dict[str, float] = {}

        for law in self._laws.values():
            score = 0.0
            # 法条名在 related_laws 中
            for ref in case.related_laws:
                if law.law_name in ref:
                    score += 0.5
                    if law.article_number and law.article_number in ref:
                        score += 0.4
            # 关键词匹配
            for bh in case.behaviors:
                if bh in law.content:
                    score += 0.15
            for subj in case.subjects:
                if subj in law.content:
                    score += 0.05

            if score > 0.2:
                linked_ids.append(law.law_id)
                scores[law.law_id] = min(round(score, 2), 1.0)

        link = CaseLawLink(
            case_id=case_id,
            law_ids=linked_ids,
            similarity_scores=scores,
            match_method="keyword",
        )
        self._links[case_id] = link
        return link

    def _index_case_vector(self, case: StructuredCase) -> None:
        text = f"{case.case_type} {case.description}"
        vec = self._embed_text(text)
        if vec is None:
            return
        try:
            import numpy as np

            vec_np = np.array([vec], dtype=np.float32)
            if self._faiss_index is None:
                dim = vec_np.shape[1]
                import faiss

                self._faiss_index = faiss.IndexFlatL2(dim)
            self._faiss_index.add(vec_np)
        except Exception as exc:
            logger.debug("向量索引失败: %s", exc)

    def search_similar_laws(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[tuple[LawArticle, float]]:
        """搜索与查询文本最相关的法条。"""

        if self._faiss_available and self._faiss_index is not None:
            return self._vector_search_laws(query, top_k)
        return self._keyword_search_laws(query, top_k)

    def _keyword_search_laws(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[tuple[LawArticle, float]]:
        results: list[tuple[LawArticle, float]] = []
        for law in self._laws.values():
            score = 0.0
            if law.law_name in query:
                score += 0.3
            for ch in law.content:
                if ch in query:
                    score += 0.02
            if law.article_number and law.article_number in query:
                score += 0.2
            score = min(score, 1.0)
            if score > 0.05:
                results.append((law, round(score, 2)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _vector_search_laws(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[tuple[LawArticle, float]]:
        vec = self._embed_text(query)
        if vec is None or self._faiss_index is None:
            return self._keyword_search_laws(query, top_k)

        try:
            import numpy as np

            vec_np = np.array([vec], dtype=np.float32)
            distances, indices = self._faiss_index.search(vec_np, min(top_k, self._faiss_index.ntotal))
            results: list[tuple[LawArticle, float]] = []
            law_list = list(self._laws.values())
            for dist, idx in zip(distances[0], indices[0]):
                if idx < len(law_list):
                    sim = float(1.0 / (1.0 + dist))
                    results.append((law_list[idx], round(sim, 2)))
            return results
        except Exception as exc:
            logger.debug("向量检索失败，回退关键词: %s", exc)
            return self._keyword_search_laws(query, top_k)

    def get_case_links(self, case_id: str) -> CaseLawLink | None:
        return self._links.get(case_id)


# ── 全局知识库单例 ──────────────────────────────────────────────────────────

_kb: CaseLawKnowledgeBase | None = None


def get_knowledge_base() -> CaseLawKnowledgeBase:
    global _kb
    if _kb is None:
        _kb = CaseLawKnowledgeBase()
    return _kb


# ---------------------------------------------------------------------------
# 5. 一键解析入口
# ---------------------------------------------------------------------------


def parse_case(raw_text: str, *, use_bert: bool = True) -> CaseParseResult:
    """对外主入口：原始文本 → 结构化案例 + 知识库入库。"""

    errors: list[str] = []
    entities: list[LegalEntity] = []
    structured_case: StructuredCase | None = None
    preprocess_info: dict[str, Any] = {}

    # Step 1: 预处理
    try:
        preprocess_info = preprocess_case_text(raw_text)
    except Exception as exc:
        errors.append(f"预处理失败: {exc}")
        return CaseParseResult(success=False, errors=errors, preprocess_info=preprocess_info)

    clean_text = preprocess_info.get("clean_text", raw_text)

    # Step 2: NER 实体抽取
    try:
        entities = extract_entities(clean_text, use_bert=use_bert)
    except Exception as exc:
        errors.append(f"NER 抽取异常: {exc}")
        entities = _extract_entities_regex(clean_text)

    if not entities:
        errors.append("未抽取到任何法律实体")

    # Step 3: 结构化
    try:
        structured_case = structure_case(raw_text, entities)
    except Exception as exc:
        errors.append(f"结构化失败: {exc}")
        return CaseParseResult(
            success=False, entities=entities, errors=errors, preprocess_info=preprocess_info,
        )

    # Step 4: 入库
    try:
        kb = get_knowledge_base()
        kb.add_case(structured_case)
    except Exception as exc:
        errors.append(f"知识库写入失败: {exc}")

    return CaseParseResult(
        success=len(errors) == 0 or structured_case is not None,
        entities=entities,
        structured_case=structured_case,
        preprocess_info=preprocess_info,
        errors=errors,
    )
