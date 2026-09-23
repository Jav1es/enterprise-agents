"""Cross-Encoder 重排器。

使用 BAAI/bge-reranker-base 对混合检索结果进行重排，
确保最终生成时附带引用来源。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """基于 Cross-Encoder 的结果重排器。"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-base", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model: Optional[Any] = None
        self._load_model()

    def _load_model(self) -> None:
        """加载 Cross-Encoder 模型。"""
        # TODO: 模型权重下载可能较大，建议懒加载；离线环境需预下载。
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device=self.device)
        except Exception as exc:  # pragma: no cover
            logger.warning("CrossEncoder 加载失败，将跳过重排: %s", exc)
            self._model = None

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """对候选结果重排。"""
        if self._model is None or not candidates:
            return candidates
        pairs = [(query, c.get("text", "")) for c in candidates]
        scores = self._model.predict(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        top_k = top_k or len(ranked)
        return [
            {**cand, "rerank_score": float(score)}
            for cand, score in ranked[:top_k]
        ]
