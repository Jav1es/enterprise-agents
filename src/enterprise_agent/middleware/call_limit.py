"""调用次数限制中间件 — 防止死循环。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ModelCallLimitMiddleware:
    """限制单次运行中的 LLM 调用次数（防止死循环）。"""

    def __init__(self, max_calls: int = 10) -> None:
        self.max_calls = max_calls

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """带次数限制的调用。

        TODO: 通过上下文计数器统计本次运行的累计调用数，超限抛异常。
        """
        return await func(*args, **kwargs)
