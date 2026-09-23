"""HTTP Connector — 通用 HTTP 工具连接器（对接 OA / CRM 等 REST 服务）。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class HTTPConnector:
    """基于 httpx 的通用 HTTP 工具连接器。"""

    def __init__(
        self,
        base_url: str,
        api_token: str = "",
        timeout_seconds: int = 30,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_token}"} if api_token else {},
        )

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET 请求。"""
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST 请求。"""
        resp = await self._client.post(path, json=payload or {})
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """关闭连接。"""
        await self._client.aclose()
