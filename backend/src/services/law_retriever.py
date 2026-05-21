"""法规检索服务 — 语义检索 + 分类过滤 + 精确法条查找。

双层架构:
  Qdrant 负责语义检索"找到"相关法条
  TXT 原文库负责提供完整法条内容

三种检索模式:
  1. 语义检索 — 向量相似度匹配，可选 category / law_name 过滤
  2. 分类检索 — 按 category 精确匹配（跳过向量）
  3. 精确检索 — 按 law_name + article_number 定位
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config import Configuration
from services.embedding import get_embedding_service
from services.law_repository import get_law_repository
from services.law_router import get_law_router

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "laws"


class LawRetriever:
    """法规检索器 — 封装 Qdrant 法律条文检索。"""

    def __init__(self, config: Configuration | None = None) -> None:
        self.config = config or Configuration.from_env()
        self.embedding = get_embedding_service()
        self.router = get_law_router()
        self._client: Optional[object] = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        if not self.config.qdrant_url:
            logger.warning("Qdrant URL 未配置，法规检索不可用")
            return
        try:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(
                url=self.config.qdrant_url,
                api_key=self.config.qdrant_api_key,
                timeout=self.config.qdrant_timeout,
            )
            if not self._client.collection_exists(_COLLECTION_NAME):
                logger.warning("Qdrant collection '%s' 不存在，请先执行法规索引", _COLLECTION_NAME)
                return
            self._available = True
        except Exception:
            logger.exception("法规检索器初始化失败")

    @property
    def available(self) -> bool:
        return self._available

    # ── 内部工具 ──────────────────────────────────────────────────────────

    def _build_hit(self, payload: dict, score: float = 0.0) -> Dict[str, Any]:
        """从 Qdrant payload + score 构建结果 dict，并用 TXT 原文丰富 content。"""
        hit = {
            "law_id": payload.get("law_id", ""),
            "law_name": payload.get("law_name", ""),
            "article_number": payload.get("article_number", ""),
            "content": payload.get("content", ""),
            "chapter": payload.get("chapter", ""),
            "category": payload.get("category", ""),
            "keywords": payload.get("keywords", []),
            "enforcement_level": payload.get("enforcement_level", ""),
            "issuing_authority": payload.get("issuing_authority", ""),
            "score": round(score, 4) if score else 0.0,
        }
        # 用 TXT 原文库补充完整法条内容（双层架构：Qdrant 找 → TXT 展示）
        try:
            repo = get_law_repository()
            if repo.available:
                return repo.resolve_article_full_text(hit)
        except Exception:
            pass
        return hit

    # ── 语义检索 ──────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        category: str = "",
        law_name: str = "",
        auto_route: bool = True,
    ) -> List[Dict[str, Any]]:
        """语义检索法条。

        Args:
            query: 用户查询文本
            top_k: 返回数量
            category: 分类过滤（空表示不过滤）
            law_name: 法律名称过滤（空表示不过滤）
            auto_route: 是否自动路由分类增强检索
        """
        if not self._available or self._client is None:
            return []

        if not self.embedding.available:
            return []

        try:
            vector = self.embedding.encode(query).tolist()

            # 构建过滤条件
            must_filters: List[dict] = []
            if category:
                must_filters.append({"key": "category", "match": {"value": category}})
            if law_name:
                must_filters.append({"key": "law_name", "match": {"value": law_name}})

            query_filter: Optional[dict] = None
            use_filter = bool(must_filters)

            # 自动路由：如果用户未指定分类且开启 auto_route，则优先检索推荐法律
            if auto_route and not must_filters:
                route = self.router.route(query)
                detected = route.get("detected_law_name")
                if detected:
                    must_filters.append({"key": "law_name", "match": {"value": detected}})
                    use_filter = True

            if use_filter:
                query_filter = {"must": must_filters}

            results = self._client.search(
                collection_name=_COLLECTION_NAME,
                query_vector=vector,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )

            hits = [self._build_hit(r.payload, r.score) for r in results if r.payload]

            # 如果 auto_route 过滤后结果太少，回退到不过滤的全局搜索
            if auto_route and len(hits) < 3 and use_filter:
                results_fallback = self._client.search(
                    collection_name=_COLLECTION_NAME,
                    query_vector=vector,
                    limit=top_k,
                    with_payload=True,
                )
                hits = [self._build_hit(r.payload, r.score) for r in results_fallback if r.payload]

            return hits
        except Exception:
            logger.exception("法规检索失败")
            return []

    # ── 分类检索 ──────────────────────────────────────────────────────────

    def search_by_category(self, category: str, limit: int = 20) -> List[Dict[str, Any]]:
        """按分类精确检索法条（不依赖向量相似度）。"""
        if not self._available or self._client is None:
            return []

        try:
            results, _ = self._client.scroll(
                collection_name=_COLLECTION_NAME,
                scroll_filter={
                    "must": [{"key": "category", "match": {"value": category}}]
                },
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            return [self._build_hit(r.payload) for r in results if r.payload]
        except Exception:
            logger.exception("分类检索失败: %s", category)
            return []

    # ── 精确法条查找 ──────────────────────────────────────────────────────

    def get_article(self, law_name: str, article_number: str) -> Optional[Dict[str, Any]]:
        """精确查找指定法律的指定条文 — 优先从 TXT 原文库获取完整内容。"""
        # 先尝试从 TXT 原文库获取（双层架构：TXT 是权威来源）
        try:
            repo = get_law_repository()
            if repo.available:
                txt = repo.get_article(law_name, article_number)
                if txt:
                    return {
                        "law_id": "",
                        "law_name": law_name,
                        "article_number": article_number,
                        "content": txt["content"],
                        "chapter": "",
                        "category": txt.get("category", ""),
                        "keywords": txt.get("keywords", []),
                        "enforcement_level": "",
                        "issuing_authority": "",
                        "source": "txt",
                    }
        except Exception:
            pass

        # 回退到 Qdrant
        if not self._available or self._client is None:
            return None

        try:
            results, _ = self._client.scroll(
                collection_name=_COLLECTION_NAME,
                scroll_filter={
                    "must": [
                        {"key": "law_name", "match": {"value": law_name}},
                        {"key": "article_number", "match": {"value": article_number}},
                    ]
                },
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if results and results[0].payload:
                return self._build_hit(results[0].payload)
            return None
        except Exception:
            logger.exception("精确法条查找失败: %s %s", law_name, article_number)
            return None

    def list_by_law(self, law_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """列出某部法律的全部已索引条文。"""
        if not self._available or self._client is None:
            return []

        try:
            results, _ = self._client.scroll(
                collection_name=_COLLECTION_NAME,
                scroll_filter={
                    "must": [{"key": "law_name", "match": {"value": law_name}}]
                },
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            return [self._build_hit(r.payload) for r in results if r.payload]
        except Exception:
            logger.exception("列表检索失败: %s", law_name)
            return []

    def list_categories(self) -> List[str]:
        """返回可用分类列表。"""
        from data.laws import LAW_CATEGORIES
        return LAW_CATEGORIES

    def get_category_counts(self) -> Dict[str, int]:
        """返回各分类下的法条数量统计。"""
        from data.laws import LAW_CATEGORIES
        counts: Dict[str, int] = {}
        for cat in LAW_CATEGORIES:
            results = self.search_by_category(cat, limit=100)
            counts[cat] = len(results)
        return counts


# 全局单例
_law_retriever: Optional[LawRetriever] = None


def get_law_retriever() -> LawRetriever:
    global _law_retriever
    if _law_retriever is None:
        _law_retriever = LawRetriever()
    return _law_retriever
