"""法规原文仓库 — 从 TXT 法律文件中读取完整法条内容。

双层架构中的"原文层"：Qdrant 负责语义检索找到法条，TXT 负责提供完整原文。

TXT 格式示例::

    中华人民共和国反垄断法
    第一条
    为了预防和制止垄断行为...
    【分类】立法目的
    【关键词】预防垄断、公平竞争
    第二条
    ...

解析为::

    {
      "law_name": "中华人民共和国反垄断法",
      "articles": [
        {"article_number": "第一条", "content": "...", "category": "立法目的", "keywords": [...]},
        ...
      ]
    }
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "laws"


class LawRepository:
    """法规原文仓库 — 从 TXT 文件读取完整法条。"""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else _DATA_DIR
        self._laws: Dict[str, Dict[str, Any]] = {}
        self._article_index: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._available = False
        self._load_all()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def law_names(self) -> list[str]:
        return sorted(self._laws.keys())

    # ── 加载 ──────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        if not self.data_dir.exists():
            logger.warning("法规原文目录不存在: %s", self.data_dir)
            return

        txt_files = sorted(self.data_dir.glob("*.txt"))
        if not txt_files:
            logger.warning("法规原文目录下无 .txt 文件: %s", self.data_dir)
            return

        for fp in txt_files:
            try:
                parsed = self._parse_txt(fp)
                if parsed and parsed.get("articles"):
                    self._laws[parsed["law_name"]] = parsed
                    # 建索引
                    idx: Dict[str, Dict[str, Any]] = {}
                    for art in parsed["articles"]:
                        idx[art["article_number"]] = art
                    self._article_index[parsed["law_name"]] = idx
                    # 也建简称索引（如 "《反垄断法》" → "中华人民共和国反垄断法"）
                    short = self._to_short_name(parsed["law_name"])
                    if short != parsed["law_name"]:
                        self._article_index[short] = idx
            except Exception:
                logger.exception("解析法规文件失败: %s", fp)

        self._available = len(self._laws) > 0
        if self._available:
            logger.info("法规原文仓库加载完成: %d 部法律, %s",
                        len(self._laws),
                        ", ".join(f"{n}({len(a['articles'])}条)" for n, a in self._laws.items()))

    def reload(self) -> None:
        self._laws.clear()
        self._article_index.clear()
        self._load_all()

    # ── 解析 ──────────────────────────────────────────────────────────────

    def _parse_txt(self, filepath: Path) -> Optional[Dict[str, Any]]:
        text = filepath.read_text(encoding="utf-8").strip()
        if not text:
            return None

        lines = text.split("\n")
        law_name = lines[0].strip()

        articles: list[Dict[str, Any]] = []
        current_article: Optional[Dict[str, Any]] = None
        content_lines: list[str] = []

        def _flush() -> None:
            nonlocal current_article, content_lines
            if current_article is not None:
                current_article["content"] = "\n".join(content_lines).strip()
                articles.append(current_article)
            current_article = None
            content_lines = []

        for line in lines[1:]:
            stripped = line.strip()
            if not stripped:
                continue

            # 检测"第X条"作为新法条起始
            if re.match(r"^第[一二三四五六七八九十百千\d]+条", stripped):
                _flush()
                art_num = re.match(r"^(第[一二三四五六七八九十百千\d]+条)", stripped).group(1)
                current_article = {"article_number": art_num, "content": "", "category": "", "keywords": []}
                # 如果"第X条"后面直接跟内容（同一行）
                rest = stripped[len(art_num):].strip()
                if rest:
                    content_lines.append(rest)
            elif stripped.startswith("【分类】"):
                if current_article is not None:
                    current_article["category"] = stripped[4:].strip()
            elif stripped.startswith("【关键词】"):
                if current_article is not None:
                    kws = stripped[5:].strip()
                    current_article["keywords"] = [k.strip() for k in kws.replace("、", "，").split("，") if k.strip()] if kws else []
            else:
                if current_article is not None:
                    content_lines.append(stripped)

        _flush()  # 最后一条

        return {"law_name": law_name, "file": filepath.name, "articles": articles}

    @staticmethod
    def _to_short_name(law_name: str) -> str:
        """将全称转为简称，如 '中华人民共和国反垄断法' → '《反垄断法》'"""
        name = law_name.replace("中华人民共和国", "")
        if name != law_name:
            return f"《{name}》"
        return law_name

    # ── 查询 ──────────────────────────────────────────────────────────────

    def get_article(self, law_name: str, article_number: str) -> Optional[Dict[str, Any]]:
        """获取指定法律的指定条文完整内容。

        Args:
            law_name: 法律名称（支持全称或简称，如 "中华人民共和国反垄断法" 或 "《反垄断法》"）
            article_number: 条文号，如 "第四十二条"

        Returns:
            {"article_number": "第四十二条", "content": "...", "category": "...", "keywords": [...]}
        """
        idx = self._article_index.get(law_name) or self._article_index.get(self._to_short_name(law_name))
        if idx is None:
            # 模糊匹配
            for name, i in self._article_index.items():
                if law_name in name or name in law_name:
                    idx = i
                    break
        if idx is None:
            return None
        return idx.get(article_number)

    def get_articles_batch(
        self, law_name: str, article_numbers: list[str]
    ) -> list[Dict[str, Any]]:
        """批量获取同一部法律的多个条文。"""
        results: list[Dict[str, Any]] = []
        for an in article_numbers:
            art = self.get_article(law_name, an)
            if art:
                results.append(art)
        return results

    def get_law_full_text(self, law_name: str) -> Optional[str]:
        """获取整部法律的完整文本。"""
        law = self._laws.get(law_name)
        if law is None:
            # 尝试简称
            for name, l in self._laws.items():
                short = self._to_short_name(name)
                if law_name == short or law_name in name:
                    law = l
                    break
        if law is None:
            return None

        parts = [law["law_name"], ""]
        for art in law["articles"]:
            parts.append(f"{art['article_number']}")
            parts.append(art["content"])
            parts.append("")
        return "\n".join(parts)

    def list_available_laws(self) -> list[Dict[str, Any]]:
        """列出所有可用的 TXT 法律及其条文数。"""
        return [
            {"law_name": name, "article_count": len(law["articles"]), "file": law["file"]}
            for name, law in self._laws.items()
        ]

    def search_in_law(self, law_name: str, keyword: str) -> list[Dict[str, Any]]:
        """在指定法律中按关键词搜索条文（简单字符串匹配）。"""
        law = self._laws.get(law_name)
        if law is None:
            return []
        results = []
        for art in law["articles"]:
            if keyword in art["content"] or keyword in art.get("category", "") or any(keyword in kw for kw in art.get("keywords", [])):
                results.append(art)
        return results

    def resolve_article_full_text(self, qdrant_hit: Dict[str, Any]) -> Dict[str, Any]:
        """用 TXT 原文补充 Qdrant 检索结果。

        Qdrant 存储的 content 可能是摘要/截断的，此方法用 TXT 中的完整原文替换。
        """
        law_name = qdrant_hit.get("law_name", "")
        article_number = qdrant_hit.get("article_number", "")

        if not law_name or not article_number:
            return qdrant_hit

        txt_article = self.get_article(law_name, article_number)
        if txt_article:
            result = dict(qdrant_hit)
            result["content"] = txt_article["content"]
            result["category"] = txt_article.get("category") or result.get("category", "")
            if txt_article.get("keywords"):
                result["keywords"] = txt_article["keywords"]
            result["source"] = "txt"
            return result

        return qdrant_hit


# 全局单例
_repo: Optional[LawRepository] = None


def get_law_repository() -> LawRepository:
    global _repo
    if _repo is None:
        _repo = LawRepository()
    return _repo
