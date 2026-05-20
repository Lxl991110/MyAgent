"""Search dispatch helpers using direct API calls (no helloagents dependency)."""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from config import Configuration, SearchAPI
from utils import deduplicate_and_format_sources, format_sources

logger = logging.getLogger(__name__)

MAX_TOKENS_PER_SOURCE = 2000


def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search via DuckDuckGo using the ddgs package."""
    try:
        from ddgs import DDGS
    except ImportError:
        logger.warning("ddgs package not installed; DuckDuckGo search unavailable")
        return []

    results: list[dict[str, Any]] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", ""),
                })
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)

    return results


def _search_tavily(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search via Tavily API."""
    try:
        from tavily import TavilyClient
    except ImportError:
        logger.warning("tavily-python not installed; Tavily search unavailable")
        return []

    import os

    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        logger.warning("TAVILY_API_KEY not set")
        return []

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=max_results)
        results: list[dict[str, Any]] = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            })
        return results
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return []


def dispatch_search(
    query: str,
    config: Configuration,
    loop_count: int,
) -> Tuple[dict[str, Any] | None, list[str], Optional[str], str]:
    """Execute the configured search backend and return normalized results."""

    search_api = config.search_api
    if isinstance(search_api, SearchAPI):
        backend = search_api.value
    else:
        backend = str(search_api)

    notices: list[str] = []
    results: list[dict[str, Any]] = []

    if backend == SearchAPI.TAVILY.value:
        results = _search_tavily(query)
        backend_label = "tavily"
    elif backend == SearchAPI.DUCKDUCKGO.value:
        results = _search_duckduckgo(query)
        backend_label = "duckduckgo"
    elif backend in (SearchAPI.PERPLEXITY.value, SearchAPI.SEARXNG.value, SearchAPI.ADVANCED.value):
        # Fall back to DuckDuckGo for unsupported backends
        notices.append(f"搜索后端 '{backend}' 暂未适配，使用 DuckDuckGo 替代")
        results = _search_duckduckgo(query)
        backend_label = "duckduckgo (fallback)"
    else:
        results = _search_duckduckgo(query)
        backend_label = "duckduckgo"

    if not results:
        notices.append("未检索到相关结果")

    logger.info(
        "Search backend=%s results=%d",
        backend_label,
        len(results),
    )

    payload: dict[str, Any] = {
        "results": results,
        "backend": backend_label,
        "answer": None,
        "notices": notices,
    }

    return payload, notices, None, backend_label


def prepare_research_context(
    search_result: dict[str, Any] | None,
    answer_text: Optional[str],
    config: Configuration,
) -> tuple[str, str]:
    """Build structured context and source summary for downstream agents."""

    sources_summary = format_sources(search_result)
    context = deduplicate_and_format_sources(
        search_result or {"results": []},
        max_tokens_per_source=MAX_TOKENS_PER_SOURCE,
        fetch_full_page=config.fetch_full_page,
    )

    if answer_text:
        context = f"AI直接答案：\n{answer_text}\n\n{context}"

    return sources_summary, context
