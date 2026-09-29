"""混合检索器 — Dense + BM25 → RRF 融合。

向量库: ChromaDB(开发) / Milvus(生产)
"""

from __future__ import annotations

import logging
from typing import Any

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

RRF_K = 60  # RRF 融合常数


def tokenize_zh(text: str) -> list[str]:
    """中文友好分词：按空白/标点切分后补充中文 bigram，提升 BM25 中文召回。"""
    tokens: list[str] = []
    for tok in text.replace("，", " ").replace("。", " ").replace("、", " ").replace("；", " ").split():
        if not tok:
            continue
        tokens.append(tok)
        # 含中文的连续串补充 bigram，缓解无分词器导致的漏匹配
        if len(tok) > 1 and any("\u4e00" <= ch <= "\u9fff" for ch in tok):
            for i in range(len(tok) - 1):
                tokens.append(tok[i : i + 2])
    return tokens


class HybridRetriever:
    """Dense + BM25 混合检索器。"""

    def __init__(
        self,
        collection: Any,
        bm25_index: BM25Okapi | None = None,
        doc_ids: list[str] | None = None,
        top_k: int = 10,
    ) -> None:
        self.collection = collection
        self.bm25 = bm25_index
        self.doc_ids = doc_ids or []
        self.top_k = top_k

    def _tokenize(self, text: str) -> list[str]:
        """简单分词（中文 bigram 增强）。"""
        return tokenize_zh(text)

    def hybrid_search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """混合检索：向量 + BM25 → RRF 融合排序。

        返回每条命中附 text / source / chunk_id 元数据，供上层直接构建引用。
        """
        top_k = top_k or self.top_k

        # 1. 向量检索
        vector_ids: list[str] = []
        try:
            vector_results = self.collection.query(
                query_texts=[query], n_results=max(top_k * 3, 20)
            )
            vector_ids = list(vector_results["ids"][0])
        except Exception as exc:  # noqa: BLE001 - embedding 不可用时降级 BM25
            logger.warning("向量检索失败，降级为仅 BM25: %s", exc)

        # 2. BM25 检索
        bm25_scores: dict[str, float] = {}
        if self.bm25 is not None:
            scores = self.bm25.get_scores(self._tokenize(query))
            for doc_id, score in zip(self.doc_ids, scores, strict=False):
                if score > 0:
                    bm25_scores[doc_id] = float(score)

        # 3. RRF (Reciprocal Rank Fusion) 融合
        rrf_scores: dict[str, float] = {}
        for rank, doc_id in enumerate(vector_ids):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, doc_id in enumerate(
            sorted(bm25_scores, key=bm25_scores.get, reverse=True)
        ):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)

        # 4. 排序并回填元数据
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        hit_ids = [doc_id for doc_id, _ in ranked]
        texts: dict[str, str] = {}
        metas: dict[str, dict[str, Any]] = {}
        if hit_ids:
            try:
                got = self.collection.get(ids=hit_ids, include=["documents", "metadatas"])
                docs = got["documents"] or [""] * len(got["ids"])
                md_list = got["metadatas"] or [None] * len(got["ids"])
                for cid, doc, md in zip(got["ids"], docs, md_list, strict=False):
                    texts[cid] = doc or ""
                    metas[cid] = md or {}
            except Exception as exc:  # noqa: BLE001
                logger.warning("回填 chunk 元数据失败: %s", exc)

        results: list[dict[str, Any]] = []
        for doc_id, score in ranked:
            md = metas.get(doc_id, {})
            results.append(
                {
                    "doc_id": doc_id,
                    "text": texts.get(doc_id, ""),
                    "source": md.get("source", ""),
                    "chunk_id": md.get("chunk_id", doc_id),
                    "rrf_score": round(score, 4),
                }
            )
        return results
