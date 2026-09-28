"""HTTP 域工具：通用 http_get / http_post。

说明：
- 基于 httpx 实现，统一超时 30s，失败返回错误信息（不抛异常）；
- 仅用于调用已授权接口，调用方需自行确保 URL 与权限合法；
- 不内置任何真实密钥 / 真实客户数据。
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import Field

from enterprise_agent_tools_mcp.tools.base import BaseTool, ToolInput, ToolOutput

# 统一请求超时（秒）
HTTP_TIMEOUT = 30.0


class HttpGetInput(ToolInput):
    """HTTP GET 入参。"""

    url: str = Field(description="目标 URL，如 https://api.example.com/demo")


class HttpGetTool(BaseTool[HttpGetInput, ToolOutput]):
    """通用 HTTP GET：返回响应 JSON（解析失败则返回原始文本）。"""

    name = "http_get"
    description = "发起 HTTP GET 请求并返回响应内容（JSON 或文本）。适用于调用已授权的只读 REST 接口。"

    input_schema = HttpGetInput
    output_schema = ToolOutput

    async def run(self, args: HttpGetInput) -> ToolOutput:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(args.url)
            resp.raise_for_status()
            return ToolOutput.ok(_parse_response(resp))
        except httpx.HTTPStatusError as exc:
            return ToolOutput.fail(f"HTTP {exc.response.status_code}: {exc.response.text[:500]}")
        except httpx.RequestError as exc:
            return ToolOutput.fail(f"请求失败: {exc}")


class HttpPostInput(ToolInput):
    """HTTP POST 入参。"""

    url: str = Field(description="目标 URL，如 https://api.example.com/demo")
    json: dict[str, Any] = Field(default_factory=dict, description="请求体 JSON 对象")


class HttpPostTool(BaseTool[HttpPostInput, ToolOutput]):
    """通用 HTTP POST：携带 JSON 请求体，返回响应 JSON（解析失败则返回原始文本）。"""

    name = "http_post"
    description = "发起 HTTP POST 请求（携带 JSON 请求体）并返回响应内容。适用于调用已授权的写操作 REST 接口。"

    input_schema = HttpPostInput
    output_schema = ToolOutput

    async def run(self, args: HttpPostInput) -> ToolOutput:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.post(args.url, json=args.json)
            resp.raise_for_status()
            return ToolOutput.ok(_parse_response(resp))
        except httpx.HTTPStatusError as exc:
            return ToolOutput.fail(f"HTTP {exc.response.status_code}: {exc.response.text[:500]}")
        except httpx.RequestError as exc:
            return ToolOutput.fail(f"请求失败: {exc}")


def _parse_response(resp: httpx.Response) -> dict[str, Any] | str:
    """解析响应：优先 JSON，失败回退为截断文本。"""
    try:
        return resp.json()
    except ValueError:
        text = resp.text
        return text[:2000] if len(text) > 2000 else text
