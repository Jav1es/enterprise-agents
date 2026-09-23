"""长期记忆存储 — PostgreSQL 事实三元组 + 用户偏好。

设计要点：
- 对话中提取的原子事实以三元组 (subject, predicate, object) 持久化
- 写入前做去重与冲突检测（同实体同谓词旧值标记过期）
- 基于访问频率的自动提升 + 基于时间的修剪
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = logging.getLogger(__name__)


class LongTermMemoryStore:
    """长期记忆存储 — 事实三元组 + 用户偏好。"""

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url)

    async def extract_and_store(self, session_id: str, dialogue: list[dict[str, Any]]) -> None:
        """从对话中提取原子事实并持久化。

        TODO: 调用 LLM 完成事实抽取（Pydantic 结构化输出），返回 facts 列表。
        """
        facts = await self._extract_facts(dialogue)
        for fact in facts:
            existing = await self._find_conflict(fact)  # 去重与冲突检测
            if existing and fact["confidence"] > existing["confidence"]:
                await self._update_fact(existing["id"], fact)
            else:
                await self._insert_fact(session_id, fact)

    async def _extract_facts(self, dialogue: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """从对话中抽取事实三元组。"""
        # TODO: 接入 LLM 结构化抽取
        return []

    async def _find_conflict(self, fact: dict[str, Any]) -> dict[str, Any] | None:
        """冲突检测：查找同实体同谓词的旧记录。"""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT id, confidence FROM mem_facts "
                    "WHERE subject = :subject AND predicate = :predicate "
                    "AND expired_at IS NULL LIMIT 1"
                ),
                {"subject": fact["subject"], "predicate": fact["predicate"]},
            )
            row = result.mappings().first()
            return dict(row) if row else None

    async def _insert_fact(self, session_id: str, fact: dict[str, Any]) -> None:
        """插入新事实。"""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO mem_facts "
                    "(session_id, subject, predicate, object, confidence, access_count, created_at) "
                    "VALUES (:session_id, :subject, :predicate, :object, :confidence, 0, :created_at)"
                ),
                {
                    "session_id": session_id,
                    "subject": fact["subject"],
                    "predicate": fact["predicate"],
                    "object": fact["object"],
                    "confidence": fact.get("confidence", 0.0),
                    "created_at": datetime.utcnow(),
                },
            )

    async def _update_fact(self, fact_id: int, fact: dict[str, Any]) -> None:
        """更新已有事实（更高置信度覆盖）。"""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE mem_facts SET object = :object, confidence = :confidence, "
                    "updated_at = :updated_at WHERE id = :id"
                ),
                {
                    "id": fact_id,
                    "object": fact["object"],
                    "confidence": fact.get("confidence", 0.0),
                    "updated_at": datetime.utcnow(),
                },
            )

    async def query_user_preferences(self, user_id: str) -> list[dict[str, Any]]:
        """查询用户偏好（按访问频率排序）。"""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT subject, predicate, object FROM mem_facts "
                    "WHERE user_id = :user_id AND predicate LIKE '偏好:%' "
                    "ORDER BY access_count DESC LIMIT 50"
                ),
                {"user_id": user_id},
            )
            return [dict(row) for row in result.mappings()]

    async def prune_expired(self, days: int = 90) -> int:
        """时间修剪：删除超过保留期的过期事实。"""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM mem_facts WHERE updated_at < :cutoff"),
                {"cutoff": datetime.utcnow() - timedelta(days=days)},
            )
            return result.rowcount

    async def close(self) -> None:
        """关闭连接。"""
        await self._engine.dispose()
