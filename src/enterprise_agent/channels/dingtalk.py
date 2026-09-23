"""钉钉接入通道 — 开放平台回调模式。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .base import BaseChannel
from .unified_message import UnifiedMessage

logger = logging.getLogger(__name__)


class DingTalkChannel(BaseChannel):
    """钉钉 Channel（开放平台回调）。"""

    platform = "dingtalk"

    def __init__(
        self,
        handler: Callable[[UnifiedMessage], Awaitable[Any]],
        app_key: str = "",
        app_secret: str = "",
    ) -> None:
        super().__init__(handler)
        self.app_key = app_key
        self.app_secret = app_secret

    async def handle_callback(self, payload: dict) -> dict:
        """处理钉钉回调请求。

        TODO: 验签（消息体验签、防重放），转换为 UnifiedMessage 后派发。
        """
        message = UnifiedMessage(
            platform=self.platform,
            user_id=str(payload.get("senderStaffId", "")),
            session_id=str(payload.get("conversationId", "")),
            content=payload.get("text", {}).get("content", ""),
            extra=payload,
        )
        await self._dispatch(message)
        return {"msg": "success"}

    async def start(self) -> None:
        logger.info("钉钉通道启动（开放平台回调模式）")

    async def stop(self) -> None:
        logger.info("钉钉通道停止")
