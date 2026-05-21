"""FAISS 向量存储服务。

基于 Sentence-BERT 嵌入，提供法条和案例的向量化索引与混合检索。
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np

from models import LawArticle, StructuredCase, RetrievedLaw, RetrievedCase
from services.embedding import get_embedding_service, EmbeddingService

logger = logging.getLogger(__name__)


class VectorStore:
    """法律知识向量存储。

    对内置于知识库的法条和案例建立 FAISS 索引，
    支持纯向量检索和混合（向量+关键词）检索。
    """

    def __init__(self, embedding: EmbeddingService | None = None) -> None:
        self.embedding = embedding or get_embedding_service()

        self._law_index: Optional[object] = None       # faiss.IndexFlatIP
        self._case_index: Optional[object] = None      # faiss.IndexFlatIP
        self._law_entries: list[LawArticle] = []
        self._case_entries: list[StructuredCase] = []
        self._faiss_available = False

        self._init_backend()

    def _init_backend(self) -> None:
        try:
            import faiss
            self._faiss_available = True
            logger.info("FAISS 向量存储后端已就绪")
        except ImportError:
            self._faiss_available = False
            logger.warning("FAISS 未安装，向量检索不可用。安装: pip install faiss-cpu")

    # ── 索引构建 ──────────────────────────────────────────────────────────

    def index_laws(self, laws: list[LawArticle]) -> int:
        """批量向量化法条并建立索引。返回索引条目数。"""
        self._law_entries = list(laws)
        if not laws or not self._faiss_available or not self.embedding.available:
            return 0

        texts = [f"{l.law_name} 第{l.article_number}条 {l.content[:500]}" for l in laws]
        vectors = self.embedding.encode_batch(texts)

        import faiss
        dim = vectors.shape[1]
        self._law_index = faiss.IndexFlatIP(dim)
        self._law_index.add(vectors.astype(np.float32))
        logger.info("已索引 %d 条法条 (dim=%d)", len(laws), dim)
        return len(laws)

    def index_cases(self, cases: list[StructuredCase]) -> int:
        """批量向量化案例并建立索引。"""
        self._case_entries = list(cases)
        if not cases or not self._faiss_available or not self.embedding.available:
            return 0

        texts = [
            f"{c.case_type} {' '.join(c.subjects)} {' '.join(c.behaviors)} {c.description[:300]}"
            for c in cases
        ]
        vectors = self.embedding.encode_batch(texts)

        import faiss
        dim = vectors.shape[1]
        self._case_index = faiss.IndexFlatIP(dim)
        self._case_index.add(vectors.astype(np.float32))
        logger.info("已索引 %d 个案例 (dim=%d)", len(cases), dim)
        return len(cases)

    # ── 检索 ──────────────────────────────────────────────────────────────

    def search_laws(
        self,
        query: str,
        top_k: int = 5,
        *,
        hybrid: bool = True,
    ) -> list[RetrievedLaw]:
        """向量 + 关键词混合检索法条。"""
        vec_results = self._vector_search_laws(query, top_k) if self._faiss_available and self._law_index is not None else []
        kw_results = self._keyword_search_laws(query, top_k) if hybrid else []

        return self._merge_law_results(vec_results, kw_results, top_k)

    def search_cases(
        self,
        query: str,
        top_k: int = 3,
        *,
        hybrid: bool = True,
    ) -> list[RetrievedCase]:
        """向量 + 关键词混合检索案例。"""
        vec_results = self._vector_search_cases(query, top_k) if self._faiss_available and self._case_index is not None else []
        kw_results = self._keyword_search_cases(query, top_k) if hybrid else []

        return self._merge_case_results(vec_results, kw_results, top_k)

    # ── 向量检索 ──────────────────────────────────────────────────────────

    def _vector_search_laws(self, query: str, top_k: int) -> list[Tuple[LawArticle, float]]:
        if not self.embedding.available or self._law_index is None:
            return []

        vec = self.embedding.encode(query)
        vec_np = np.array([vec], dtype=np.float32)
        distances, indices = self._law_index.search(vec_np, min(top_k, self._law_index.ntotal))

        results: list[Tuple[LawArticle, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0 and idx < len(self._law_entries):
                results.append((self._law_entries[idx], float(dist)))
        return results

    def _vector_search_cases(self, query: str, top_k: int) -> list[Tuple[StructuredCase, float]]:
        if not self.embedding.available or self._case_index is None:
            return []

        vec = self.embedding.encode(query)
        vec_np = np.array([vec], dtype=np.float32)
        distances, indices = self._case_index.search(vec_np, min(top_k, self._case_index.ntotal))

        results: list[Tuple[StructuredCase, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0 and idx < len(self._case_entries):
                results.append((self._case_entries[idx], float(dist)))
        return results

    # ── 关键词检索（回退）─────────────────────────────────────────────────

    def _keyword_search_laws(self, query: str, top_k: int) -> list[Tuple[LawArticle, float]]:
        results: list[Tuple[LawArticle, float]] = []
        for law in self._law_entries:
            score = 0.0
            if law.law_name in query:
                score += 0.3
            for ch in law.content:
                if ch in query:
                    score += 0.02
            if law.article_number and law.article_number in query:
                score += 0.2
            score = min(score, 0.95)
            if score > 0.05:
                results.append((law, round(score, 2)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _keyword_search_cases(self, query: str, top_k: int) -> list[Tuple[StructuredCase, float]]:
        results: list[Tuple[StructuredCase, float]] = []
        for case in self._case_entries:
            score = 0.0
            if case.case_type in query:
                score += 0.2
            for s in case.subjects:
                if s in query:
                    score += 0.15
            for b in case.behaviors:
                if b in query:
                    score += 0.15
            for t in case.risk_tags:
                if t in query:
                    score += 0.1
            score = min(score, 0.95)
            if score > 0.05:
                results.append((case, round(score, 2)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ── 混合融合 ──────────────────────────────────────────────────────────

    def _merge_law_results(
        self,
        vec: list[Tuple[LawArticle, float]],
        kw: list[Tuple[LawArticle, float]],
        top_k: int,
    ) -> list[RetrievedLaw]:
        """合并向量和关键词结果（加权 + 去重）。"""
        scores: dict[str, Tuple[LawArticle, float, str]] = {}  # law_id → (law, score, method)

        for law, score in vec:
            scores[law.law_id] = (law, score * 0.7, "vector")

        for law, score in kw:
            if law.law_id in scores:
                _, prev_score, _ = scores[law.law_id]
                scores[law.law_id] = (law, max(prev_score, score * 0.3), "hybrid")
            else:
                scores[law.law_id] = (law, score * 0.3, "keyword")

        merged = sorted(scores.values(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            RetrievedLaw(
                law_id=law.law_id,
                law_name=law.law_name,
                article_number=law.article_number,
                content=law.content,
                chapter=law.chapter,
                enforcement_level=law.enforcement_level,
                score=round(score, 3),
                retrieval_method=method,
            )
            for law, score, method in merged
        ]

    def _merge_case_results(
        self,
        vec: list[Tuple[StructuredCase, float]],
        kw: list[Tuple[StructuredCase, float]],
        top_k: int,
    ) -> list[RetrievedCase]:
        """合并案例结果。"""
        scores: dict[str, Tuple[StructuredCase, float, str]] = {}

        for case, score in vec:
            scores[case.case_id] = (case, score * 0.7, "vector")

        for case, score in kw:
            if case.case_id in scores:
                _, prev_score, _ = scores[case.case_id]
                scores[case.case_id] = (case, max(prev_score, score * 0.3), "hybrid")
            else:
                scores[case.case_id] = (case, score * 0.3, "keyword")

        merged = sorted(scores.values(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            RetrievedCase(
                case_id=case.case_id,
                case_type=case.case_type,
                subjects=case.subjects,
                behaviors=case.behaviors,
                related_laws=case.related_laws,
                risk_tags=case.risk_tags,
                description=case.description,
                score=round(score, 3),
                retrieval_method=method,
            )
            for case, score, method in merged
        ]

    @property
    def law_count(self) -> int:
        return len(self._law_entries)

    @property
    def case_count(self) -> int:
        return len(self._case_entries)


# 全局单例
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


def init_vector_store(laws: list[LawArticle], cases: list[StructuredCase] | None = None) -> VectorStore:
    """初始化向量存储并批量索引法条和案例。"""
    store = get_vector_store()
    store.index_laws(laws)
    if cases:
        store.index_cases(cases)
    return store
