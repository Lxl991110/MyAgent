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
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration, SearchAPI
from agent import LawResearchAgent
from services.case_parser import get_knowledge_base, parse_case

logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)

logger.add(
    sink=sys.stderr,
    level="ERROR",
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
            "Law Research Agent (LangGraph) configuration: provider=%s model=%s base_url=%s "
            "search_api=%s max_loops=%s fetch_full_page=%s api_key=%s",
            config.llm_provider,
            config.resolved_model() or "unset",
            base_url,
            (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
            config.max_web_research_loops,
            config.fetch_full_page,
            _mask_secret(config.llm_api_key),
        )

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

        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
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
