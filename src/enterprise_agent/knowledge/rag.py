"""RAG 检索入口 — 文档切分、索引、混合检索与重排组装。

TODO: 补充完整 RAG 管线（load -> split -> embed -> index -> hybrid search -> rerank）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .retriever import HybridRetriever

logger = logging.getLogger(__name__)


class RAGPipeline:
    """RAG 知识检索管线。"""

    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: Optional[Any] = None,
    ) -> None:
        self.retriever = retriever
        self.reranker = reranker

    async def retrieve_with_evidence(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """检索并返回带证据的结果。"""
        results = self.retriever.hybrid_search(query, top_k=top_k)

        # 重排
        if self.reranker is not None:
            # TODO: Cross-Encoder 重排
            pass

        # TODO: 附加引用来源 (source / chunk_id / score)
        return results
