"""接入通道基础抽象 — Channel 统一接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from .unified_message import UnifiedMessage


class BaseChannel(ABC):
    """企业系统接入通道基类。

    所有平台通道（钉钉 / 企微 / OA / ERP）继承本类，
    将平台差异消息收敛为 UnifiedMessage 统一格式。
    """

    platform: str = ""

    def __init__(self, handler: Callable[[UnifiedMessage], Awaitable[Any]]) -> None:
        self._handler = handler

    @abstractmethod
    async def start(self) -> None:
        """启动通道（长连接 / 回调服务）。"""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """停止通道。"""
        raise NotImplementedError

    async def _dispatch(self, message: UnifiedMessage) -> Any:
        """将统一消息派发给业务处理层。"""
        return await self._handler(message)
