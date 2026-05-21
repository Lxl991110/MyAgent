"""Qdrant 长期记忆服务。

存储合规审查结果到 Qdrant Cloud，支持语义检索历史案例，
为后续 RAG 提供"历史案例记忆"上下文。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import Configuration
from services.embedding import get_embedding_service, EmbeddingService

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "legal_cases"


class QdrantMemoryService:
    """Qdrant 向量记忆存储与检索。

    管理 legal_cases collection，复用 Sentence-BERT 384 维嵌入。
    """

    def __init__(self, config: Configuration | None = None) -> None:
        self.config = config or Configuration.from_env()
        self.embedding = get_embedding_service()
        self._client: Optional[object] = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        if not self.config.qdrant_url:
            logger.warning("Qdrant URL 未配置，记忆服务不可用")
            return
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(
                url=self.config.qdrant_url,
                api_key=self.config.qdrant_api_key,
                timeout=self.config.qdrant_timeout,
            )

            # 确保 collection 存在（兼容旧版 qdrant-client）
            distance = getattr(Distance, self.config.qdrant_distance.upper(), Distance.COSINE)
            if not self._client.collection_exists(_COLLECTION_NAME):
                self._client.create_collection(
                    collection_name=_COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.config.qdrant_vector_size,
                        distance=distance,
                    ),
                )

            self._available = True
            logger.info(
                "Qdrant 记忆服务已连接: %s (collection=%s, dim=%d)",
                self.config.qdrant_url, _COLLECTION_NAME, self.config.qdrant_vector_size,
            )
        except ImportError:
            logger.warning("qdrant-client 未安装，记忆服务不可用")
        except Exception:
            logger.exception("Qdrant 连接失败，记忆服务不可用")

    @property
    def available(self) -> bool:
        return self._available

    # ── CRUD ────────────────────────────────────────────────────────────

    def store(
        self,
        case_text: str,
        risk_level: str,
        review_summary: str,
        violations: list[dict[str, Any]] | None = None,
        relevant_laws: list[dict[str, Any]] | None = None,
        suggestions: list[str] | None = None,
        *,
        case_id: str | None = None,
    ) -> Optional[str]:
        """将审查结果存入 Qdrant，返回 case_id。失败返回 None。"""
        if not self._available or self._client is None:
            return None

        case_id = case_id or f"mem-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

        # 构建检索文本（用于生成 embedding）
        parts = [case_text]
        if violations:
            parts.append(" ".join(
                v.get("type", "") for v in violations
            ))
        search_text = " ".join(p for p in parts if p)

        try:
            vector = self.embedding.encode(search_text).tolist()

            payload: Dict[str, Any] = {
                "case_id": case_id,
                "query": case_text,
                "risk_level": risk_level,
                "review_summary": review_summary,
                "violations": violations or [],
                "relevant_laws": relevant_laws or [],
                "suggestions": suggestions or [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            from qdrant_client.models import PointStruct

            self._client.upsert(
                collection_name=_COLLECTION_NAME,
                points=[
                    PointStruct(
                        id=uuid.uuid4().hex,
                        vector=vector,
                        payload=payload,
                    )
                ],
            )

            logger.info("记忆已存储: %s (风险: %s)", case_id, risk_level)
            return case_id
        except Exception:
            logger.exception("记忆存储失败: %s", case_id)
            return None

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """语义检索历史案例，返回相似案例列表。"""
        if not self._available or self._client is None:
            return []

        if not self.embedding.available:
            return []

        try:
            vector = self.embedding.encode(query).tolist()

            results = self._client.search(
                collection_name=_COLLECTION_NAME,
                query_vector=vector,
                limit=top_k,
                with_payload=True,
            )

            return [
                {
                    "case_id": r.payload.get("case_id", ""),
                    "query": r.payload.get("query", ""),
                    "risk_level": r.payload.get("risk_level", ""),
                    "review_summary": r.payload.get("review_summary", ""),
                    "violations": r.payload.get("violations", []),
                    "relevant_laws": r.payload.get("relevant_laws", []),
                    "suggestions": r.payload.get("suggestions", []),
                    "timestamp": r.payload.get("timestamp", ""),
                    "score": round(r.score, 3),
                }
                for r in results
                if r.payload
            ]
        except Exception:
            logger.exception("记忆检索失败")
            return []

    def get(self, case_id: str) -> Optional[dict[str, Any]]:
        """按 case_id 获取单条记忆。"""
        if not self._available or self._client is None:
            return None

        try:
            results, _ = self._client.scroll(
                collection_name=_COLLECTION_NAME,
                scroll_filter={
                    "must": [{"key": "case_id", "match": {"value": case_id}}]
                },
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if results and results[0].payload:
                p = results[0].payload
                return {
                    "case_id": p.get("case_id", ""),
                    "query": p.get("query", ""),
                    "risk_level": p.get("risk_level", ""),
                    "review_summary": p.get("review_summary", ""),
                    "violations": p.get("violations", []),
                    "relevant_laws": p.get("relevant_laws", []),
                    "suggestions": p.get("suggestions", []),
                    "timestamp": p.get("timestamp", ""),
                }
            return None
        except Exception:
            logger.exception("获取记忆失败: %s", case_id)
            return None

    def list_all(self, limit: int = 50) -> list[dict[str, Any]]:
        """列出最近存储的案例记忆。"""
        if not self._available or self._client is None:
            return []

        try:
            results, _ = self._client.scroll(
                collection_name=_COLLECTION_NAME,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            return [
                {
                    "case_id": r.payload.get("case_id", ""),
                    "query": r.payload.get("query", ""),
                    "risk_level": r.payload.get("risk_level", ""),
                    "review_summary": r.payload.get("review_summary", ""),
                    "violations": r.payload.get("violations", []),
                    "relevant_laws": r.payload.get("relevant_laws", []),
                    "suggestions": r.payload.get("suggestions", []),
                    "timestamp": r.payload.get("timestamp", ""),
                }
                for r in results
                if r.payload
            ]
        except Exception:
            logger.exception("列出记忆失败")
            return []

    @property
    def case_count(self) -> int:
        """已存储案例数量。"""
        if not self._available or self._client is None:
            return 0
        try:
            info = self._client.count(_COLLECTION_NAME)
            return info.count if hasattr(info, "count") else 0
        except Exception:
            return 0


# 全局单例
_qdrant_memory: Optional[QdrantMemoryService] = None


def get_qdrant_memory() -> QdrantMemoryService:
    global _qdrant_memory
    if _qdrant_memory is None:
        _qdrant_memory = QdrantMemoryService()
    return _qdrant_memory
