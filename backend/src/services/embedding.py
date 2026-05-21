"""Sentence-BERT 文本嵌入服务。

默认模型：paraphrase-multilingual-MiniLM-L12-v2（支持中文，384 维）。
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_EMBEDDING_DIM = 384


class EmbeddingService:
    """文本向量化封装，支持 sentence-transformers 和退化模式。"""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self.dim = _EMBEDDING_DIM
        self._model: Optional[object] = None
        self._available = False
        self._init_model()

    def _init_model(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self._available = True
            logger.info("Sentence-BERT 模型加载完成: %s (dim=%d)", self.model_name, self.dim)
        except ImportError:
            logger.warning(
                "sentence-transformers 未安装，将使用零向量占位。"
                "安装: pip install sentence-transformers"
            )
        except Exception:
            logger.exception("Sentence-BERT 模型加载失败，将使用零向量占位")

    @property
    def available(self) -> bool:
        return self._available

    def encode(self, text: str) -> np.ndarray:
        """将单条文本编码为向量。"""
        if not self._available:
            return np.zeros(self.dim, dtype=np.float32)
        return self._model.encode(text, normalize_embeddings=True)  # type: ignore[union-attr]

    def encode_batch(self, texts: List[str], show_progress: bool = False) -> np.ndarray:
        """批量编码文本。"""
        if not self._available:
            return np.zeros((len(texts), self.dim), dtype=np.float32)
        return self._model.encode(  # type: ignore[union-attr]
            texts,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
        )


# 全局单例，按需惰性初始化
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
