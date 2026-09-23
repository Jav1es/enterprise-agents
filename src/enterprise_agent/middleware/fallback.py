"""模型降级中间件 — Provider 宕机时自动切换到备用模型。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ModelFallbackMiddleware:
    """Provider 宕机自动降级到备用模型。"""

    def __init__(self, fallback_models: list[str]) -> None:
        self.fallback_models = fallback_models

    async def call(self, func: Callable[..., Any], model: str, *args: Any, **kwargs: Any) -> Any:
        """按模型列表依次尝试调用。"""
        models = [model] + self.fallback_models
        last_exc: Exception | None = None
        for candidate in models:
            try:
                return await func(*args, model=candidate, **kwargs)
            except Exception as exc:
                last_exc = exc
                logger.warning("模型 %s 不可用: %s, 降级到 %s", candidate, exc, models)
        raise last_exc  # type: ignore[misc]
