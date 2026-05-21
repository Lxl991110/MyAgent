"""FastAPI entrypoint exposing the LawResearchAgent via HTTP."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Iterator, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatTongyi
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration, SearchAPI
from agent import LawResearchAgent
from services.case_parser import get_knowledge_base, parse_case
from services.compliance_reviewer import ComplianceReviewService
from services.law_indexer import get_law_indexer
from services.law_retriever import get_law_retriever
from services.law_repository import get_law_repository
from services.law_router import get_law_router
from services.qdrant_memory import get_qdrant_memory
from services.trace_logger import get_trace_logger
from services.vector_store import init_vector_store

logger.remove()  # 移除 loguru 默认 handler，避免日志重复输出
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


class ResearchRequest(BaseModel):
    """Payload for triggering a research run."""

    topic: str = Field(..., description="Research topic supplied by the user")
    case_text: str = Field(default="", description="Optional case text for parsing")
    search_api: SearchAPI | None = Field(
        default=None,
        description="Override the default search backend configured via env",
    )


class CaseParseRequest(BaseModel):
    """Payload for standalone case parsing."""

    text: str = Field(..., description="Raw legal case text to parse")
    use_bert: bool = Field(default=False, description="Enable BERT NER (requires transformers)")


class CaseParseResponse(BaseModel):
    """Structured case parse result."""

    success: bool
    case_id: str = ""
    case_type: str = ""
    subjects: list[str] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)
    amount: str = ""
    region: str = ""
    time_period: str = ""
    related_laws: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    description: str = ""
    entities: list[dict[str, Any]] = Field(default_factory=list)
    preprocess_info: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class ResearchResponse(BaseModel):
    """HTTP response containing the generated report and structured tasks."""

    report_markdown: str = Field(
        ..., description="Markdown-formatted research report including sections"
    )
    todo_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured TODO items with summaries and sources",
    )
    verification: Optional[dict[str, Any]] = Field(
        default=None,
        description="Verification results: law validity, fact consistency, violations",
    )
    retrieved_laws: list[dict[str, Any]] = Field(
        default_factory=list,
        description="RAG-retrieved law articles with scores",
    )


class ComplianceReviewRequest(BaseModel):
    """合规审查请求。"""

    text: str = Field(..., description="待审查的合同条款或商业行为描述")
    context: str = Field(default="", description="额外上下文，如行业、地域等")
    use_rag: bool = Field(default=True, description="是否启用 RAG 知识库增强")
    override_laws: list[dict[str, Any]] | None = Field(
        default=None,
        description="人工修正后的法条列表，提供后跳过 RAG 检索直接使用",
    )


class ComplianceReviewResponse(BaseModel):
    """合规审查结果。"""

    risk_level: str = Field(default="低", description="风险等级：低 / 中 / 高")
    violations: list[dict[str, Any]] = Field(default_factory=list)
    relevant_laws: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    review_summary: str = Field(default="")
    case_id: str = Field(default="", description="审查案例 ID，用于存入记忆")


class MemoryStoreRequest(BaseModel):
    """存入长期记忆的请求。"""

    case_text: str = Field(..., description="原始审查文本")
    risk_level: str = Field(..., description="风险等级: 低/中/高")
    review_summary: str = Field(..., description="审查总结")
    violations: list[dict[str, Any]] = Field(default_factory=list)
    relevant_laws: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class GenerateCaseRequest(BaseModel):
    """案例生成请求 — 用户可指定违法行为、法条、案件类型等条件。"""

    violation_behavior: str = Field(default="", description="违法行为，如'地域限制'")
    violated_law: str = Field(default="", description="违反的法条，如'《反垄断法》第四十二条'")
    case_type: str = Field(default="", description="案件类型，如'政府采购'")
    risk_level: str = Field(default="", description="风险等级: 高/中/低，空=自动判断")
    style: str = Field(default="真实案例风格", description="生成风格: 真实案例风格 | 行政处罚风格 | 法院判决风格")
    user_message: str = Field(default="", description="用户自然语言补充描述")
    extra_context: str = Field(default="")


class SaveGeneratedCaseRequest(BaseModel):
    """保存生成案例到知识库。"""

    case: dict[str, Any] = Field(..., description="生成的案例 JSON")


def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """Mask sensitive tokens while keeping leading and trailing characters."""

    if not value:
        return "unset"

    if len(value) <= visible * 2:
        return "*" * len(value)

    return f"{value[:visible]}...{value[-visible:]}"


def _build_config(payload: ResearchRequest) -> Configuration:
    overrides: Dict[str, Any] = {}

    if payload.search_api is not None:
        overrides["search_api"] = payload.search_api

    return Configuration.from_env(overrides=overrides)


def _init_llm_for_endpoint(config: Configuration | None = None) -> BaseChatModel:
    """为独立端点初始化 LLM（复用 agent.py 的初始化逻辑）。"""
    cfg = config or Configuration.from_env()

    llm_kwargs: dict[str, Any] = {"temperature": 0.0}
    model_id = cfg.llm_model_id or cfg.local_llm
    if model_id:
        llm_kwargs["model"] = model_id

    provider = (cfg.llm_provider or "").strip()
    if provider == "ollama":
        llm_kwargs["base_url"] = cfg.sanitized_ollama_url()
        llm_kwargs["api_key"] = cfg.llm_api_key or "ollama"
        return ChatOpenAI(**llm_kwargs)
    elif provider == "lmstudio":
        llm_kwargs["base_url"] = cfg.lmstudio_base_url
        llm_kwargs["api_key"] = cfg.llm_api_key or "lm-studio"
        return ChatOpenAI(**llm_kwargs)
    else:
        api_key = cfg.llm_api_key
        if api_key:
            llm_kwargs["dashscope_api_key"] = api_key
        return ChatTongyi(**llm_kwargs)


def create_app() -> FastAPI:
    app = FastAPI(title="Law Research Agent (LangGraph)")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def log_startup_configuration() -> None:
        config = Configuration.from_env()

        if config.llm_provider == "ollama":
            base_url = config.sanitized_ollama_url()
        elif config.llm_provider == "lmstudio":
            base_url = config.lmstudio_base_url
        else:
            base_url = "dashscope (ChatTongyi)"

        logger.info(
            "配置: provider={} model={} base_url={} search_api={} max_loops={} fetch_full_page={} api_key={}",
            config.llm_provider,
            config.resolved_model() or "unset",
            base_url,
            (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
            config.max_web_research_loops,
            config.fetch_full_page,
            _mask_secret(config.llm_api_key),
        )

        # 初始化向量存储：索引内置法条 + 已入库案例
        try:
            kb = get_knowledge_base()
            laws = kb.list_laws()
            cases = kb.list_cases()
            store = init_vector_store(laws, cases)
            logger.info("向量存储初始化完成: {} 法条, {} 案例", store.law_count, store.case_count)
        except Exception:
            logger.exception("向量存储初始化失败，RAG 检索将不可用")

        # 初始化 Qdrant 长期记忆
        try:
            memory = get_qdrant_memory()
            if memory.available:
                logger.info("Qdrant 长期记忆就绪: {} 条历史案例", memory.case_count)
        except Exception:
            logger.exception("Qdrant 记忆初始化失败")

        # 初始化法规知识库索引（Qdrant laws collection）
        try:
            indexer = get_law_indexer()
            if indexer.available:
                existing = indexer.law_count
                repo = get_law_repository()
                txt_total = sum(law["article_count"] for law in repo.list_available_laws()) if repo.available else 0

                if existing == 0:
                    count = indexer.index_all()
                    logger.info("法规知识库索引完成: {} 条法条写入 Qdrant", count)
                elif txt_total > existing:
                    logger.info("TXT 原文库有 {} 条法条，Qdrant 仅 {} 条，自动补充索引...", txt_total, existing)
                    count = indexer.index_all()
                    logger.info("法规知识库补充索引完成: 更新后共 {} 条", count)
                else:
                    logger.info("法规知识库就绪: {} 条法条", existing)
        except Exception:
            logger.exception("法规知识库索引失败")

        # 初始化 TXT 法规原文库（双层架构的原文层）
        try:
            repo = get_law_repository()
            if repo.available:
                logger.info("TXT 法规原文库就绪: {} 部法律", len(repo.law_names))
        except Exception:
            logger.exception("TXT 法规原文库初始化失败")

    @app.get("/healthz")
    def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        try:
            config = _build_config(payload)
            agent = LawResearchAgent(config=config)
            result = agent.run(payload.topic, case_text=payload.case_text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Research failed") from exc

        todo_payload = [
            {
                "id": item.id,
                "title": item.title,
                "intent": item.intent,
                "query": item.query,
                "status": item.status,
                "summary": item.summary,
                "sources_summary": item.sources_summary,
            }
            for item in result.todo_items
        ]

        verif = result.verification_result
        verification_payload = None
        if verif:
            verification_payload = {
                "passed": verif.passed,
                "score": verif.overall_score,
                "law_validity": verif.law_validity,
                "fact_consistency": verif.fact_consistency,
                "violation_detection": verif.violation_detection,
                "warnings": verif.warnings,
                "corrections": verif.corrections,
            }

        laws_payload = [
            {
                "law_id": rl.law_id,
                "law_name": rl.law_name,
                "article_number": rl.article_number,
                "content": rl.content[:200],
                "score": rl.score,
                "method": rl.retrieval_method,
            }
            for rl in (result.retrieved_laws or [])
        ]

        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
            verification=verification_payload,
            retrieved_laws=laws_payload,
        )

    @app.post("/research/stream")
    def stream_research(payload: ResearchRequest) -> StreamingResponse:
        try:
            config = _build_config(payload)
            agent = LawResearchAgent(config=config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        def event_iterator() -> Iterator[str]:
            try:
                for event in agent.run_stream(payload.topic, case_text=payload.case_text):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.exception("Streaming research failed")
                error_payload = {"type": "error", "detail": str(exc)}
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    @app.post("/case/parse", response_model=CaseParseResponse)
    def parse_case_endpoint(payload: CaseParseRequest) -> CaseParseResponse:
        """独立案例解析接口：原始文本 → 结构化 JSON。"""

        try:
            result = parse_case(payload.text, use_bert=payload.use_bert)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"案例解析失败: {exc}") from exc

        sc = result.structured_case
        return CaseParseResponse(
            success=result.success,
            case_id=sc.case_id if sc else "",
            case_type=sc.case_type if sc else "",
            subjects=sc.subjects if sc else [],
            behaviors=sc.behaviors if sc else [],
            amount=sc.amount if sc else "",
            region=sc.region if sc else "",
            time_period=sc.time_period if sc else "",
            related_laws=sc.related_laws if sc else [],
            risk_tags=sc.risk_tags if sc else [],
            description=sc.description if sc else "",
            entities=[
                {"type": e.type, "value": e.value, "confidence": e.confidence}
                for e in result.entities
            ],
            preprocess_info=result.preprocess_info,
            errors=result.errors,
        )

    @app.get("/case/knowledge-base/laws")
    def list_laws(search: str = "") -> list[dict[str, Any]]:
        """查询内置法律条文库，支持关键词检索。"""

        kb = get_knowledge_base()
        if search.strip():
            results = kb.search_similar_laws(search, top_k=10)
            return [
                {
                    "law_id": law.law_id,
                    "law_name": law.law_name,
                    "article_number": law.article_number,
                    "content": law.content[:200],
                    "chapter": law.chapter,
                    "enforcement_level": law.enforcement_level,
                    "score": score,
                }
                for law, score in results
            ]
        return [
            {
                "law_id": law.law_id,
                "law_name": law.law_name,
                "article_number": law.article_number,
                "content": law.content[:200],
                "chapter": law.chapter,
                "enforcement_level": law.enforcement_level,
            }
            for law in kb.list_laws()
        ]

    @app.get("/case/knowledge-base/cases")
    def list_cases() -> list[dict[str, Any]]:
        """列出已入库的结构化案例。"""

        kb = get_knowledge_base()
        return [
            {
                "case_id": c.case_id,
                "case_type": c.case_type,
                "subjects": c.subjects,
                "behaviors": c.behaviors,
                "related_laws": c.related_laws,
                "risk_tags": c.risk_tags,
                "description": c.description[:200],
            }
            for c in kb.list_cases()
        ]

    # ── 法规检索（Qdrant 语义 + 分类 + 精确查找）───────────────────────

    @app.get("/laws/search")
    def search_laws(
        q: str = "",
        category: str = "",
        law_name: str = "",
        top_k: int = 10,
        auto_route: bool = True,
    ) -> dict[str, Any]:
        """语义检索法条（支持分类过滤 + 自动路由）。

        - q: 查询文本
        - category: 分类过滤（可选，如 公平竞争、招投标）
        - law_name: 法律名称过滤（可选，如 《反垄断法》）
        - auto_route: 是否启用自动路由过滤（默认开启；搜索下拉场景建议关闭）
        """
        if not q.strip():
            return {"hits": [], "route": None}

        retriever = get_law_retriever()
        if not retriever.available:
            raise HTTPException(status_code=503, detail="法规检索服务不可用，请确认 Qdrant laws collection 已索引")

        router = get_law_router()
        route = router.route(q)

        hits = retriever.search(
            q, top_k=top_k,
            category=category,
            law_name=law_name,
            auto_route=auto_route and not (category or law_name),
        )

        # 确保按分数降序排列
        hits.sort(key=lambda h: h.get("score", 0), reverse=True)

        return {
            "hits": hits,
            "total": len(hits),
            "route": route,
        }

    @app.get("/laws/categories")
    def list_categories() -> dict[str, Any]:
        """返回法规分类列表及各类别法条数量。"""
        retriever = get_law_retriever()
        categories = retriever.list_categories()
        counts = retriever.get_category_counts() if retriever.available else {}
        return {
            "categories": categories,
            "counts": counts,
            "total_indexed": sum(counts.values()) if retriever.available else 0,
        }

    @app.get("/laws/article")
    def get_article(law_name: str, article_number: str) -> dict[str, Any]:
        """精确查找指定法律的指定条文（优先从 TXT 原文库获取完整内容）。"""
        retriever = get_law_retriever()
        result = retriever.get_article(law_name, article_number) if retriever.available else None

        if result is None:
            # 直接从 TXT 原文库查找
            repo = get_law_repository()
            if repo.available:
                txt = repo.get_article(law_name, article_number)
                if txt:
                    return {
                        "law_id": "", "law_name": law_name, "article_number": article_number,
                        "content": txt["content"], "chapter": "",
                        "category": txt.get("category", ""), "keywords": txt.get("keywords", []),
                        "enforcement_level": "", "issuing_authority": "", "source": "txt",
                    }
            raise HTTPException(status_code=404, detail=f"未找到: {law_name} {article_number}")
        return result

    @app.get("/laws/txt")
    def list_txt_laws() -> dict[str, Any]:
        """列出 TXT 原文库中可用的法律法规（双层架构的原文层）。"""
        repo = get_law_repository()
        return {
            "available": repo.available,
            "laws": repo.list_available_laws(),
            "total": len(repo.law_names),
        }

    @app.get("/laws/txt/articles")
    def get_txt_law_articles(law_name: str = "") -> dict[str, Any]:
        """获取某部法律在 TXT 原文库中的所有条文（结构化列表）。

        用法: GET /laws/txt/articles?law_name=中华人民共和国反垄断法
        """
        if not law_name:
            raise HTTPException(status_code=400, detail="缺少 law_name 参数")
        repo = get_law_repository()
        law = repo._laws.get(law_name)
        if law is None:
            # 尝试简称匹配
            for name, l in repo._laws.items():
                short = repo._to_short_name(name)
                if law_name == short or law_name in name:
                    law = l
                    law_name = name
                    break
        if law is None:
            raise HTTPException(status_code=404, detail=f"未找到法律: {law_name}")
        return {
            "law_name": law["law_name"],
            "article_count": len(law["articles"]),
            "articles": law["articles"],
        }

    @app.get("/laws/txt/{law_name:path}")
    def get_txt_law_full_text(law_name: str) -> dict[str, Any]:
        """获取某部法律的完整 TXT 原文。"""
        repo = get_law_repository()
        text = repo.get_law_full_text(law_name)
        if text is None:
            raise HTTPException(status_code=404, detail=f"未找到法律: {law_name}")
        return {"law_name": law_name, "full_text": text}

    @app.get("/laws/list")
    def list_laws_by_name(law_name: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """列出某部法律的已索引条文（law_name 为空则按分类返回最新索引）。"""
        retriever = get_law_retriever()
        if not retriever.available:
            return []
        if law_name.strip():
            return retriever.list_by_law(law_name.strip(), limit=limit)
        # 返回所有分类汇总
        result: list[dict[str, Any]] = []
        for cat in retriever.list_categories():
            articles = retriever.search_by_category(cat, limit=limit)
            result.extend(articles)
        return result[:limit]

    @app.get("/laws/route")
    def analyze_query(q: str = "") -> dict[str, Any]:
        """分析查询文本，返回分类路由结果（调试用）。"""
        if not q.strip():
            return {"categories": [], "preferred_laws": [], "detected_law_name": None}
        router = get_law_router()
        return router.route(q)

    # ── 合规审查 ──────────────────────────────────────────────────────────

    @app.post("/compliance/review", response_model=ComplianceReviewResponse)
    def compliance_review(payload: ComplianceReviewRequest) -> ComplianceReviewResponse:
        """对企业行为/合同条款进行合规审查（规则初筛 + LLM 深度分析）。"""

        from services.verifier import VerificationAgent
        from tools.fact_check import FactCheckTool

        verifier = VerificationAgent()
        fact_checker = FactCheckTool()

        # ── Trace: 创建审查追踪 ──────────────────────────────────────
        trace_logger = get_trace_logger()
        trace = trace_logger.start_trace(payload.text, context=payload.context)

        # 生成案例 ID
        import uuid
        from datetime import datetime, timezone
        case_id = f"cr-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

        # ── 阶段 1：法规检索（Qdrant 语义 + 分类路由 + 人工修正）────
        if payload.override_laws is not None:
            relevant_laws = payload.override_laws
            logger.info("使用人工修正法条 {} 条，跳过检索", len(relevant_laws))
        else:
            retriever = get_law_retriever()
            if payload.use_rag and retriever.available:
                retrieved = retriever.search(payload.text, top_k=5, auto_route=True)
                relevant_laws = [
                    {
                        "law_name": r.get("law_name", ""),
                        "article": r.get("article_number", ""),
                        "content": r.get("content", "")[:200],
                        "score": r.get("score", 0),
                    }
                    for r in retrieved
                ]
                logger.info("法规检索(Qdrant): {} 条法条", len(relevant_laws))
            else:
                relevant_laws = []

        trace.log_step(
            "law_retrieval",
            override_mode=payload.override_laws is not None,
            laws_count=len(relevant_laws),
            laws_summary=[
                {"law_name": r.get("law_name", ""), "article": r.get("article", "")}
                for r in relevant_laws
            ],
            hybrid_search=payload.use_rag,
        )

        violations = verifier.detect_violations(payload.text)
        violation_details = violations.get("details", [])
        fact_result = fact_checker.call(text=payload.text)

        trace.log_step(
            "rule_engine_scan",
            violations_detected=violations.get("violations_detected", 0),
            violation_types=[v.get("type", "") for v in violation_details],
            fact_checks_verified=fact_result.data.get("verified", 0) if fact_result.success else 0,
            fact_checks_total=fact_result.data.get("total_refs", 0) if fact_result.success else 0,
            max_severity=violations.get("max_severity", "★☆☆"),
        )

        # ── 1.5 记忆检索：查找相似历史案例 ────────────────────────────
        past_cases: list[dict[str, Any]] = []
        try:
            memory_service = get_qdrant_memory()
            if memory_service.available:
                past_cases = memory_service.search(payload.text, top_k=3)
                if past_cases:
                    logger.info("记忆检索: 命中 {} 条相似历史案例", len(past_cases))
        except Exception:
            logger.exception("记忆检索失败，将继续审查")

        trace.log_step(
            "memory_retrieval",
            memory_hits=len(past_cases),
            past_case_ids=[pc.get("case_id", "") for pc in past_cases],
            past_risk_levels=[pc.get("risk_level", "") for pc in past_cases],
        )

        # ── RAG Context 汇总 ──────────────────────────────────────────
        rag_context = {
            "relevant_laws_count": len(relevant_laws),
            "past_cases_count": len(past_cases),
            "violation_types": [v.get("type", "") for v in violation_details],
        }
        trace.log_step("rag_context", **rag_context)

        # ── 阶段 2：LLM 深度分析 ──────────────────────────────────────
        llm_result: Optional[Dict[str, Any]] = None
        llm_failed = False
        try:
            reviewer = ComplianceReviewService(_init_llm_for_endpoint())
            llm_result = reviewer.review(
                text=payload.text,
                context=payload.context,
                violations=violations,
                fact_checks=fact_result.data if fact_result.success else None,
                relevant_laws=relevant_laws,
                past_cases=past_cases,
                trace=trace,
            )
            if llm_result:
                trace.log_step("verification", llm_passed=True)
                response = ComplianceReviewResponse(
                    risk_level=llm_result.get("risk_level", "低"),
                    violations=llm_result.get("violations", []),
                    relevant_laws=llm_result.get("relevant_laws", relevant_laws),
                    suggestions=llm_result.get("suggestions", []),
                    review_summary=llm_result.get("review_summary", ""),
                    case_id=case_id,
                )
                trace.set_final_report({
                    "risk_level": response.risk_level,
                    "violations_count": len(response.violations),
                    "relevant_laws_count": len(response.relevant_laws),
                    "suggestions_count": len(response.suggestions),
                    "source": "llm",
                })
                trace_logger.save_trace(trace)
                return response
        except Exception:
            logger.exception("LLM 合规审查失败，回退到规则引擎")
            llm_failed = True

        # ── 回退：规则引擎结果 ────────────────────────────────────────
        if llm_failed or llm_result is None:
            trace.log_step("verification", llm_passed=False, fallback_to_rules=True)

        risk_level = violations.get("max_severity", "★☆☆")
        if risk_level == "★★★":
            risk_label = "高"
        elif risk_level == "★★☆":
            risk_label = "中"
        else:
            risk_label = "低"

        suggestions: list[str] = []
        for v in violation_details:
            for law_ref in v.get("relevant_laws", [])[:1]:
                suggestions.append(f"针对「{v.get('type', '')}」行为，建议参照 {law_ref} 进行合规整改")
        if not suggestions:
            suggestions.append("未检测到明显违法风险，建议定期合规自查")

        response = ComplianceReviewResponse(
            risk_level=risk_label,
            violations=violation_details,
            relevant_laws=relevant_laws,
            suggestions=suggestions,
            review_summary=(
                f"检测到 {violations.get('violations_detected', 0)} 类潜在违法风险，"
                f"涉及 {len(relevant_laws)} 条相关法律法规，总体风险等级：{risk_label}"
            ),
            case_id=case_id,
        )
        trace.set_final_report({
            "risk_level": response.risk_level,
            "violations_count": len(response.violations),
            "relevant_laws_count": len(response.relevant_laws),
            "suggestions_count": len(response.suggestions),
            "source": "rule_engine_fallback",
        })
        trace_logger.save_trace(trace)
        return response

    # ── 工具列表 ──────────────────────────────────────────────────────────

    @app.get("/tools/list")
    def list_tools() -> list[dict[str, Any]]:
        """列出所有可用的 MCP 工具及其输入 Schema。"""

        from tools import get_tool_registry

        registry = get_tool_registry()
        return registry.list_tools()

    @app.post("/tools/call")
    def call_tool(name: str, body: dict[str, Any] = {}) -> dict[str, Any]:
        """调用指定 MCP 工具。"""

        from tools import get_tool_registry

        registry = get_tool_registry()
        result = registry.call_tool(name, **body)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "metadata": result.metadata,
        }

    # ── 案例生成 ─────────────────────────────────────────────────────

    @app.post("/case/generate/stream")
    def stream_case_generation(payload: GenerateCaseRequest) -> StreamingResponse:
        """流式生成法律案例（SSE）。

        支持自定义违法行为、违反法条、案件类型、风险等级、生成风格。
        每个阶段实时推送进度事件。
        """
        from models import CaseGenerationConfig
        from services.case_generator import CaseGenerator

        config = CaseGenerationConfig(
            violation_behavior=payload.violation_behavior,
            violated_law=payload.violated_law,
            case_type=payload.case_type,
            risk_level=payload.risk_level,
            style=payload.style,
            extra_context=payload.extra_context or payload.user_message,
        )

        generator = CaseGenerator(_init_llm_for_endpoint())

        def event_iterator() -> Iterator[str]:
            try:
                for event in generator.generate_stream(config, user_message=payload.user_message):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.exception("案例生成流式失败")
                yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @app.post("/case/save")
    def save_generated_case(payload: SaveGeneratedCaseRequest) -> dict[str, Any]:
        """将生成的案例存入 Qdrant 长期记忆。"""
        memory = get_qdrant_memory()
        if not memory.available:
            raise HTTPException(status_code=503, detail="记忆服务不可用")

        c = payload.case
        case_text = f"{c.get('title', '')} | {c.get('case_type', '')} | {c.get('violation_behavior', '')} | {c.get('violated_law', '')}"
        case_id = memory.store(
            case_text=case_text,
            risk_level=c.get("risk_level", "低"),
            review_summary=c.get("review_conclusion", "")[:200],
            violations=[{
                "type": c.get("violation_behavior", ""),
                "relevant_laws": [c.get("violated_law", "")],
                "severity": "★★★" if c.get("risk_level") == "高" else ("★★☆" if c.get("risk_level") == "中" else "★☆☆"),
            }],
            relevant_laws=[{
                "law_name": c.get("violated_law", "").split("第")[0] if "第" in c.get("violated_law", "") else c.get("violated_law", ""),
                "article": c.get("violated_law", ""),
                "content": c.get("legal_analysis", "")[:200],
            }],
            suggestions=[c.get("penalty_reference", "")],
        )

        if not case_id:
            raise HTTPException(status_code=500, detail="案例保存失败")

        logger.info("生成案例已存入记忆: {} ({} 风险)", case_id, c.get("risk_level", ""))
        return {"success": True, "case_id": case_id, "message": "案例已存入长期记忆"}

    # ── 长期记忆 ─────────────────────────────────────────────────────

    @app.post("/memory/store")
    def store_memory(payload: MemoryStoreRequest) -> dict[str, Any]:
        """将合规审查结果存入 Qdrant 长期记忆。"""
        memory = get_qdrant_memory()
        if not memory.available:
            raise HTTPException(status_code=503, detail="记忆服务不可用")

        case_id = memory.store(
            case_text=payload.case_text,
            risk_level=payload.risk_level,
            review_summary=payload.review_summary,
            violations=payload.violations,
            relevant_laws=payload.relevant_laws,
            suggestions=payload.suggestions,
        )

        if not case_id:
            raise HTTPException(status_code=500, detail="记忆存储失败")

        logger.info("记忆已存储: {} (风险: {})", case_id, payload.risk_level)
        return {"success": True, "case_id": case_id, "message": "已存入长期记忆"}

    @app.get("/memory/search")
    def search_memory(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """语义检索历史案例记忆。"""
        memory = get_qdrant_memory()
        if not memory.available:
            return []
        return memory.search(query, top_k=top_k)

    @app.get("/memory/cases")
    def list_memory_cases(limit: int = 50) -> list[dict[str, Any]]:
        """列出已存储的历史案例。"""
        memory = get_qdrant_memory()
        if not memory.available:
            return []
        return memory.list_all(limit=limit)

    # ── Agent Trace 日志 ─────────────────────────────────────────────────

    @app.get("/logs/traces")
    def list_traces(limit: int = 50) -> list[dict[str, Any]]:
        """列出最近的审查 trace 摘要。"""
        tl = get_trace_logger()
        return tl.list_traces(limit=limit)

    @app.get("/logs/trace/{trace_id}")
    def get_trace(trace_id: str) -> dict[str, Any]:
        """获取单条审查 trace 完整详情（含所有步骤、Prompt、输出）。"""
        tl = get_trace_logger()
        data = tl.get_trace(trace_id)
        if data is None:
            raise HTTPException(status_code=404, detail=f"Trace 不存在: {trace_id}")
        return data

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
