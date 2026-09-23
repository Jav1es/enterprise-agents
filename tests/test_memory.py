"""记忆层测试（占位）。"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_short_term_memory_append():
    """TODO: Redis 会话记忆 append/get/TTL 测试（需 redis 服务或 fakeredis）。"""
    assert True


@pytest.mark.asyncio
async def test_long_term_conflict_detection():
    """TODO: 事实三元组冲突检测与置信度覆盖测试（需 PostgreSQL）。"""
    assert True
