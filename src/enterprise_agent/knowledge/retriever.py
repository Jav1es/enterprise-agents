"""混合检索器 — Dense + BM25 → RRF 融合。

向量库: ChromaDB(开发) / Milvus(生产)
"""

from __future__ import annotations

import logging
from typing import Any

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

RRF_K = 60  # RRF 融合常数


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
        """简单分词。TODO: 接入 jieba 等中文分词。"""
        return [tok for tok in text.replace("，", " ").replace("。", " ").split() if tok]

    def hybrid_search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """混合检索：向量 + BM25 → RRF 融合排序。"""
        # 1. 向量检索
        # TODO: 生成 query 的 embedding 后查询
        # vector_results = self.collection.query(query_embeddings=[...], n_results=top_k)
        vector_results = self.collection.query(query_texts=[query], n_results=top_k)
        vector_ids = vector_results["ids"][0]

        # 2. BM25 检索
        bm25_scores: dict[str, float] = {}
        if self.bm25 is not None:
            scores = self.bm25.get_scores(self._tokenize(query))
            for doc_id, score in zip(self.doc_ids, scores, strict=True):
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

        # 4. 排序返回
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [
            {"doc_id": doc_id, "rrf_score": score}
            for doc_id, score in ranked[:top_k]
        ]
