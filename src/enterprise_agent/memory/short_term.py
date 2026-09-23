"""短期记忆存储 — Redis 会话状态管理。

特性：TTL 30 分钟、滚动摘要、上下文预算控制。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """基于 Redis 的短期会话记忆。"""

    def __init__(self, redis_url: str, ttl_seconds: int = 1800) -> None:
        self._redis: aioredis.Redis = aioredis.from_url(redis_url, decode_responses=True)
        self.ttl_seconds = ttl_seconds
        self._key_prefix = "agent:session:"

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}{session_id}"

    async def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """读取会话历史（OpenAI 消息格式）。"""
        raw = await self._redis.get(self._key(session_id))
        if not raw:
            return []
        return json.loads(raw)

    async def append_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """追加一条消息并刷新 TTL。"""
        key = self._key(session_id)
        history = await self.get_history(session_id)
        history.append(message)
        # TODO: 上下文预算控制 — 超过 max_context_messages 时触发滚动摘要
        await self._redis.set(key, json.dumps(history), ex=self.ttl_seconds)

    async def get_summary(self, session_id: str) -> Optional[str]:
        """读取滚动摘要。"""
        return await self._redis.get(f"{self._key(session_id)}:summary")

    async def clear(self, session_id: str) -> None:
        """清空会话状态。"""
        await self._redis.delete(self._key(session_id))

    async def close(self) -> None:
        """关闭连接。"""
        await self._redis.aclose()
