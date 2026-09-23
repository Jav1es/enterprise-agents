"""企微接入通道 — wecom-aibot-python-sdk WebSocket 长连接。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .base import BaseChannel
from .unified_message import UnifiedMessage

logger = logging.getLogger(__name__)


class WeComChannel(BaseChannel):
    """企微 Channel（WebSocket 长连接）。

    使用 wecom-aibot-python-sdk 建立长连接。
    TODO: 集成 sdk 回调事件 -> UnifiedMessage。
    """

    platform = "wecom"

    def __init__(
        self,
        handler: Callable[[UnifiedMessage], Awaitable[Any]],
        corp_id: str = "",
        agent_id: str = "",
        secret: str = "",
    ) -> None:
        super().__init__(handler)
        self.corp_id = corp_id
        self.agent_id = agent_id
        self.secret = secret

    async def start(self) -> None:
        # TODO: wecom-aibot-python-sdk 初始化并建立 WebSocket 连接
        logger.info("企微通道启动（WebSocket 长连接）")

    async def stop(self) -> None:
        logger.info("企微通道停止")
