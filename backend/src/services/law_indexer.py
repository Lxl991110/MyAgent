"""法规索引器 — 将结构化法条批量写入 Qdrant 知识库。

Collection: `laws` — 384-dim cosine, 每条法条一个 point，
payload 含 law_name / article / chapter / category / keywords / content / source。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import Configuration
from data.laws import ALL_LAWS
from models import LawArticle
from services.embedding import get_embedding_service

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "laws"


class LawIndexer:
    """法规索引器 — 批量写入结构化法律条文到 Qdrant。"""

    def __init__(self, config: Configuration | None = None) -> None:
        self.config = config or Configuration.from_env()
        self.embedding = get_embedding_service()
        self._client: Optional[object] = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        if not self.config.qdrant_url:
            logger.warning("Qdrant URL 未配置，法规索引不可用")
            return
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(
                url=self.config.qdrant_url,
                api_key=self.config.qdrant_api_key,
                timeout=self.config.qdrant_timeout,
            )

            distance = getattr(Distance, self.config.qdrant_distance.upper(), Distance.COSINE)
            if not self._client.collection_exists(_COLLECTION_NAME):
                self._client.create_collection(
                    collection_name=_COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.config.qdrant_vector_size,
                        distance=distance,
                    ),
                )

            # 为过滤字段创建 payload 索引（category / law_name / article_number）
            from qdrant_client.models import PayloadSchemaType
            for field in ["category", "law_name", "article_number"]:
                try:
                    self._client.create_payload_index(
                        collection_name=_COLLECTION_NAME,
                        field_name=field,
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                except Exception:
                    pass  # 索引已存在则忽略

            self._available = True
            logger.info("法规索引器已连接: collection=%s, dim=%d", _COLLECTION_NAME, self.config.qdrant_vector_size)
        except Exception:
            logger.exception("法规索引器初始化失败")

    @property
    def available(self) -> bool:
        return self._available

    @property
    def law_count(self) -> int:
        if not self._available or self._client is None:
            return 0
        try:
            info = self._client.count(_COLLECTION_NAME)
            return info.count if hasattr(info, "count") else 0
        except Exception:
            return 0

    # ── 索引 ──────────────────────────────────────────────────────────────

    def index_law(self, law: LawArticle) -> Optional[str]:
        """索引单条法条到 Qdrant。返回 point_id 或 None。"""
        if not self._available or self._client is None:
            return None

        search_text = f"{law.law_name} {law.article_number} {law.chapter} {law.content}"
        try:
            vector = self.embedding.encode(search_text).tolist()

            payload: Dict[str, Any] = {
                "law_id": law.law_id,
                "law_name": law.law_name,
                "article_number": law.article_number,
                "content": law.content,
                "chapter": law.chapter,
                "category": law.category,
                "keywords": law.keywords,
                "enforcement_level": law.enforcement_level,
                "issuing_authority": law.issuing_authority,
                "source": law.source,
                "updated_at": law.updated_at,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }

            from qdrant_client.models import PointStruct

            point_id = uuid.uuid4().hex
            self._client.upsert(
                collection_name=_COLLECTION_NAME,
                points=[PointStruct(id=point_id, vector=vector, payload=payload)],
            )
            return point_id
        except Exception:
            logger.exception("法条索引失败: %s %s", law.law_name, law.article_number)
            return None

    def _get_existing_articles(self) -> set[tuple[str, str]]:
        """从 Qdrant 中查询已索引的 (law_name, article_number) 集合，用于去重。"""
        existing: set[tuple[str, str]] = set()
        if not self._available or self._client is None:
            return existing
        try:
            # scroll 全部已有记录获取 law_name + article_number
            offset = None
            while True:
                results, next_offset = self._client.scroll(
                    collection_name=_COLLECTION_NAME,
                    limit=100,
                    offset=offset,
                    with_payload=["law_name", "article_number"],
                    with_vectors=False,
                )
                for r in results:
                    if r.payload:
                        existing.add((r.payload.get("law_name", ""), r.payload.get("article_number", "")))
                if next_offset is None:
                    break
                offset = next_offset
        except Exception:
            logger.exception("查询已索引法条失败")
        return existing

    def index_all(self, laws: List[LawArticle] | None = None) -> int:
        """批量索引法条到 Qdrant（含 laws.py 精选法条 + TXT 原文库全部法条）。

        先索引 laws.py 中的精选法条（带完整元数据），再从 TXT 原文库补充
        laws.py 中未覆盖的条文（如反垄断法第1-70条全部）。
        自动跳过 Qdrant 中已存在的法条。
        """
        if not self._available or self._client is None:
            return 0

        if laws is None:
            laws = list(ALL_LAWS)

        # 从 Qdrant 查询已存在的法条，避免重复索引
        indexed = self._get_existing_articles()
        count = 0
        for law in laws:
            if (law.law_name, law.article_number) in indexed:
                continue
            point_id = self.index_law(law)
            if point_id:
                count += 1
                indexed.add((law.law_name, law.article_number))

        # 从 TXT 原文库补充 laws.py 中未覆盖的法条
        txt_count = self._index_from_txt(indexed)
        count += txt_count

        logger.info("法规索引完成: %d 条写入 Qdrant (laws.py: %d, TXT补充: %d)",
                    count, count - txt_count, txt_count)
        return count

    def _index_from_txt(self, already_indexed: set[tuple[str, str]]) -> int:
        """从 TXT 原文库读取法条并索引到 Qdrant，跳过已索引的条文。

        将 TXT 中的完整法律名称映射为简称（如《反垄断法》），
        保持与 laws.py 中 Qdrant 数据命名一致。
        """
        try:
            from services.law_repository import get_law_repository

            repo = get_law_repository()
            if not repo.available:
                return 0

            # TXT 全称 → laws.py 简称的映射
            name_map = {
                "中华人民共和国反垄断法": "《反垄断法》",
                "中华人民共和国反不正当竞争法": "《反不正当竞争法》",
                "中华人民共和国招标投标法": "《招标投标法》",
                "中华人民共和国政府采购法": "《政府采购法》",
                "中华人民共和国价格法": "《价格法》",
                "中华人民共和国电子商务法": "《电子商务法》",
            }

            count = 0
            for full_name, law_data in repo._laws.items():
                short_name = name_map.get(full_name, full_name)
                for art in law_data.get("articles", []):
                    art_num = art.get("article_number", "")
                    if (short_name, art_num) in already_indexed:
                        continue

                    law_art = LawArticle(
                        law_id=f"txt_{full_name}_{art_num}",
                        law_name=short_name,
                        article_number=art_num,
                        content=art.get("content", ""),
                        chapter="",
                        category=art.get("category", ""),
                        keywords=art.get("keywords", []),
                        enforcement_level="法律",
                        issuing_authority="全国人大常委会",
                        source="txt",
                        updated_at="",
                    )
                    pid = self.index_law(law_art)
                    if pid:
                        count += 1
                        already_indexed.add((short_name, art_num))

            if count:
                logger.info("TXT 原文库补充索引: %d 条法条", count)
            return count
        except Exception:
            logger.exception("TXT 原文库补充索引失败")
            return 0

    def rebuild(self) -> int:
        """清空 collection 并重新索引全部法条（laws.py + TXT 原文库）。"""
        if not self._available or self._client is None:
            return 0
        try:
            self._client.delete_collection(_COLLECTION_NAME)
            self._init_client()
            return self.index_all()
        except Exception:
            logger.exception("法规索引重建失败")
            return 0


# 全局单例
_law_indexer: Optional[LawIndexer] = None


def get_law_indexer() -> LawIndexer:
    global _law_indexer
    if _law_indexer is None:
        _law_indexer = LawIndexer()
    return _law_indexer
