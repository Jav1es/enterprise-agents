"""API 路由测试（占位）。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from enterprise_agent.api.main import app


@pytest.mark.asyncio
async def test_health():
    """健康检查接口。"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_not_ready():
    """TODO: 工作流未初始化时应返回 503。"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/v1/chat",
            json={
                "session_id": "sess_001",
                "user_id": "u_1001",
                "message": "hello",
                "channel": "api",
                "stream": False,
            },
        )
    assert resp.status_code == 503
