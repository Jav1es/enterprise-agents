"""重试中间件 — 瞬态错误指数退避重试。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ModelRetryMiddleware:
    """对瞬态错误（网络/限流）执行指数退避重试。"""

    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0) -> None:
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """带重试的调用。"""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:  # TODO: 仅捕获瞬态错误类型
                last_exc = exc
                wait = self.backoff_factor ** attempt
                logger.warning("调用失败(第%d次): %s, %.1fs 后重试", attempt + 1, exc, wait)
                if attempt < self.max_retries:
                    await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]
