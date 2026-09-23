"""熔断器 — 连续失败自动熔断，半开状态试探恢复。"""

from __future__ import annotations

import enum
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(enum.Enum):
    """熔断器状态。"""

    CLOSED = "closed"        # 正常
    OPEN = "open"            # 熔断
    HALF_OPEN = "half_open"  # 半开试探


class CircuitBreaker:
    """熔断器。

    连续失败达到阈值（如 5 次）后自动熔断（Open），
    经过恢复超时时间后进入半开状态（Half-Open）允许试探请求。
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """带熔断保护的调用。"""
        self._maybe_half_open()
        if self.state == CircuitState.OPEN:
            raise RuntimeError("circuit breaker open, request rejected")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise exc

    def _maybe_half_open(self) -> None:
        if self.state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("熔断器进入半开状态")

    def _on_success(self) -> None:
        self._consecutive_failures = 0
        if self.state != CircuitState.CLOSED:
            self.state = CircuitState.CLOSED
            logger.info("熔断器恢复关闭状态")

    def _on_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("熔断器触发: 连续失败 %d 次", self._consecutive_failures)
