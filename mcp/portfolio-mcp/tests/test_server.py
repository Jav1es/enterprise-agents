"""MCP Server 测试：工具注册与基本调用。

覆盖：
1. server 模块可导入，FastMCP 实例存在且名称正确；
2. 三个工具均已注册（list_modules / search_portfolio / get_item_detail）；
3. 工具基本调用：list_modules 返回模块列表、search_portfolio 关键词命中、
   get_item_detail 命中与未命中分支；
4. 资源与提示模板存在（在 mcp 对象上可见）。
"""

from __future__ import annotations

import pytest

import portfolio_mcp.server as server


# ---------------------------------------------------------------------------
# 工具注册校验
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_registered() -> None:
    """三个工具均应已注册（通过 server 模块可见）。"""
    for name in ["list_modules", "search_portfolio", "get_item_detail"]:
        assert hasattr(server, name), f"工具 {name} 未注册"
        assert callable(getattr(server, name)), f"工具 {name} 不可调用"


@pytest.mark.asyncio
async def test_fastmcp_instance_exists() -> None:
    """FastMCP 实例应存在且名称正确。"""
    assert server.mcp is not None
    assert server.mcp.name == "portfolio"


# ---------------------------------------------------------------------------
# 工具基本调用
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_modules_ok() -> None:
    """list_modules：应返回非空模块概览列表。"""
    result = await server.list_modules()
    assert result["success"] is True
    assert result["data"]["count"] >= 1
    assert result["data"]["modules"], "模块列表不应为空"
    # 概览应包含 id / title / status / pitch 字段
    first = result["data"]["modules"][0]
    for field in ["id", "title", "status", "pitch"]:
        assert field in first, f"概览缺少字段 {field}"


@pytest.mark.asyncio
async def test_search_portfolio_hit() -> None:
    """search_portfolio：关键词命中（title/字段包含检索词）。"""
    # 内置示例数据中包含 "MCP"，应至少命中 1 条
    result = await server.search_portfolio("MCP")
    assert result["success"] is True
    assert result["data"]["count"] >= 1
    assert result["data"]["hits"], "应至少命中一条模块"
    assert result["data"]["note"] == "所有数据均为示例数据，仅用于演示"


@pytest.mark.asyncio
async def test_search_portfolio_empty_keyword() -> None:
    """search_portfolio：空关键词应返回失败而非异常。"""
    result = await server.search_portfolio("   ")
    assert result["success"] is False
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_get_item_detail_ok() -> None:
    """get_item_detail：命中示例模块，应返回完整详情。"""
    result = await server.get_item_detail("mcp-enterprise-agent-tools")
    assert result["success"] is True
    assert result["data"]["id"] == "mcp-enterprise-agent-tools"
    # 关键字段应存在
    for field in ["id", "title", "status", "jd", "pitch", "pain", "role", "arch", "tools", "metrics"]:
        assert field in result["data"], f"详情缺少字段 {field}"
    assert result["data"]["note"] == "示例数据"


@pytest.mark.asyncio
async def test_get_item_detail_missing() -> None:
    """get_item_detail：未命中 id 应返回失败而非异常。"""
    result = await server.get_item_detail("NOT-EXIST-ID")
    assert result["success"] is False
    assert result["error"] is not None


# ---------------------------------------------------------------------------
# 资源与提示模板（通过 mcp 对象能力探测）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resources_registered() -> None:
    """资源应注册：静态资源与模板分别通过 FastMCP 内部注册表可见。"""
    resource_manager = server.mcp._resource_manager  # noqa: SLF001 - 测试内部注册表
    # 静态资源（无参数 URI）：portfolio://modules（uri 为 AnyUrl 对象，转字符串比较）
    resource_uris = {str(r.uri) for r in resource_manager.list_resources()}
    assert "portfolio://modules" in resource_uris
    # 动态模板（带 {id} 参数）：portfolio://module/{id}
    template_uris = {t.uri_template for t in resource_manager.list_templates()}
    assert "portfolio://module/{id}" in template_uris


@pytest.mark.asyncio
async def test_prompts_registered() -> None:
    """提示模板应注册：通过 FastMCP 内部注册表可见。"""
    prompt_manager = server.mcp._prompt_manager  # noqa: SLF001 - 测试内部注册表
    names = {p.name for p in prompt_manager.list_prompts()}
    assert "interview_pitch_prompt" in names
