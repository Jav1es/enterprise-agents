"""MCP Server 测试：工具注册与基本调用。

覆盖：
1. server 模块可导入，FastMCP 实例存在；
2. 六个工具均已注册（通过装饰器暴露名称校验）；
3. ERP 工具基本调用：query_inventory / get_order_status / generate_replenishment；
4. 知识检索工具 search_knowledge；
5. 资源与提示模板存在（在 mcp 对象上可见）。
"""

from __future__ import annotations

import pytest

import enterprise_agent_tools_mcp.server as server


# ---------------------------------------------------------------------------
# 工具注册校验
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_registered() -> None:
    """六个工具均应已注册（通过 server 模块可见）。"""
    for name in [
        "query_inventory",
        "get_order_status",
        "generate_replenishment",
        "search_knowledge",
        "http_get",
        "http_post",
    ]:
        assert hasattr(server, name), f"工具 {name} 未注册"
        assert callable(getattr(server, name)), f"工具 {name} 不可调用"


@pytest.mark.asyncio
async def test_fastmcp_instance_exists() -> None:
    """FastMCP 实例应存在且名称正确。"""
    assert server.mcp is not None
    # FastMCP 实例名称通过底层服务可见
    assert server.mcp.name == "enterprise-agent-tools"


# ---------------------------------------------------------------------------
# ERP 工具基本调用（mock 数据）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_inventory_ok() -> None:
    """库存查询：命中示例数据。"""
    result = await server.query_inventory("SKU-DEMO-001")
    assert result["success"] is True
    assert result["data"]["product_code"] == "SKU-DEMO-001"
    assert result["data"]["note"] == "示例数据"


@pytest.mark.asyncio
async def test_query_inventory_missing() -> None:
    """库存查询：未命中时返回失败而非异常。"""
    result = await server.query_inventory("SKU-NOT-EXIST")
    assert result["success"] is False
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_get_order_status_ok() -> None:
    """订单状态查询：命中示例数据。"""
    result = await server.get_order_status("ORD-DEMO-1001")
    assert result["success"] is True
    assert result["data"]["order_id"] == "ORD-DEMO-1001"
    assert "已发货" in result["data"]["status"]


@pytest.mark.asyncio
async def test_generate_replenishment() -> None:
    """补货建议：SKU-DEMO-002 库存 18 < 安全库存 40，应建议补货。"""
    result = await server.generate_replenishment(["SKU-DEMO-001", "SKU-DEMO-002"])
    assert result["success"] is True
    by_sku = {item["sku"]: item for item in result["data"]["suggestions"]}
    # SKU-DEMO-001：120 >= 50，无需补货
    assert by_sku["SKU-DEMO-001"]["suggest_qty"] == 0
    # SKU-DEMO-002：18 < 40，需补货 22
    assert by_sku["SKU-DEMO-002"]["suggest_qty"] == 22


@pytest.mark.asyncio
async def test_generate_replenishment_empty() -> None:
    """补货建议：空列表返回失败。"""
    result = await server.generate_replenishment([])
    assert result["success"] is False


# ---------------------------------------------------------------------------
# 知识检索工具
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_knowledge() -> None:
    """知识检索：命中示例文档。"""
    result = await server.search_knowledge("补货 审批")
    assert result["success"] is True
    assert result["data"]["hits"], "应至少命中一篇示例文档"
    assert result["data"]["note"] == "示例知识库，仅用于演示"


# ---------------------------------------------------------------------------
# 资源与提示模板（通过 mcp 对象能力探测）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resources_registered() -> None:
    """资源模板应注册：通过 FastMCP 内部注册表可见。"""
    resource_templates = server.mcp._resource_manager.list_templates()  # noqa: SLF001 - 测试内部注册表
    uris = {t.uri_template for t in resource_templates}
    assert "enterprise://inventory/{product_code}" in uris
    assert "enterprise://orders/{order_id}" in uris


@pytest.mark.asyncio
async def test_prompts_registered() -> None:
    """提示模板应注册：通过 FastMCP 内部注册表可见。"""
    prompt_manager = server.mcp._prompt_manager  # noqa: SLF001 - 测试内部注册表
    names = {p.name for p in prompt_manager.list_prompts()}
    assert "replenishment_prompt" in names
