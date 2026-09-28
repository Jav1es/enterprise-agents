"""MCP Server 主体：FastMCP('enterprise-agent-tools')。

暴露内容：
- 工具（Tools）：query_inventory / get_order_status / generate_replenishment /
  search_knowledge / http_get / http_post
- 资源（Resources）：enterprise://inventory/{product_code}、enterprise://orders/{order_id}
- 提示模板（Prompts）：replenishment_prompt（输入 SKU 列表返回补货建议提示词）

运行方式：
- uv run enterprise-agent-tools-mcp
- uv run python -m enterprise_agent_tools_mcp
- uvx mcp dev src/enterprise_agent_tools_mcp/server.py（Inspector 调试）
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from enterprise_agent_tools_mcp.tools.erp import (
    GenerateReplenishmentInput,
    GenerateReplenishmentTool,
    GetOrderStatusInput,
    GetOrderStatusTool,
    MOCK_INVENTORY,
    MOCK_ORDERS,
    QueryInventoryInput,
    QueryInventoryTool,
)
from enterprise_agent_tools_mcp.tools.http import HttpGetInput, HttpGetTool, HttpPostInput, HttpPostTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Server 实例
# ---------------------------------------------------------------------------
mcp = FastMCP("enterprise-agent-tools")


# ---------------------------------------------------------------------------
# mock 知识库（示例数据，仅用于演示 search_knowledge）
# ---------------------------------------------------------------------------
MOCK_KNOWLEDGE_BASE: list[dict[str, str]] = [
    {
        "title": "示例制度：库存盘点流程（示例）",
        "content": "每月末进行一次全量库存盘点，盘点差异需在三个工作日内查明原因并提交调整单。（示例文档，仅用于演示）",
    },
    {
        "title": "示例制度：补货审批规则（示例）",
        "content": "当库存低于安全库存时，系统自动生成补货建议；金额超过阈值需部门负责人审批。（示例文档，仅用于演示）",
    },
    {
        "title": "示例手册：ERP 订单操作指南（示例）",
        "content": "订单发货前需核对商品编码与数量，发货后 24 小时内更新物流单号。（示例文档，仅用于演示）",
    },
]


def _search_knowledge_impl(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """知识库关键词检索实现：对示例文档做简单的包含匹配 + 打分排序。

    仅用于演示：正式接入可替换为 enterprise-agents 的 HybridRetriever(RRF) 等方案。
    """
    query = query.strip().lower()
    if not query:
        return []
    scored: list[tuple[float, dict[str, str]]] = []
    for doc in MOCK_KNOWLEDGE_BASE:
        haystack = (doc["title"] + " " + doc["content"]).lower()
        # 简单打分：命中关键词个数越多分越高（示例逻辑）
        score = sum(1 for word in query.split() if word in haystack)
        if score > 0:
            scored.append((float(score), doc))
    # 按分数降序，取 top_k
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]


# ---------------------------------------------------------------------------
# 工具（Tools）
# ---------------------------------------------------------------------------


@mcp.tool()
async def query_inventory(product_code: str) -> dict[str, Any]:
    """查询 ERP 库存：根据产品编码返回库存信息（数量、仓库、安全库存）。

    Args:
        product_code: 产品编码，如 SKU-DEMO-001
    """
    result = await QueryInventoryTool().run_safe(QueryInventoryInput(product_code=product_code))
    return result.model_dump()


@mcp.tool()
async def get_order_status(order_id: str) -> dict[str, Any]:
    """查询订单状态：根据订单号返回订单状态、客户与商品明细。

    Args:
        order_id: 订单号，如 ORD-DEMO-1001
    """
    result = await GetOrderStatusTool().run_safe(GetOrderStatusInput(order_id=order_id))
    return result.model_dump()


@mcp.tool()
async def generate_replenishment(sku_list: list[str]) -> dict[str, Any]:
    """生成补货建议：结合当前库存与安全库存，为输入的 SKU 列表计算建议补货量。

    Args:
        sku_list: 需要评估的 SKU 列表，如 ["SKU-DEMO-001", "SKU-DEMO-002"]
    """
    result = await GenerateReplenishmentTool().run_safe(GenerateReplenishmentInput(sku_list=sku_list))
    return result.model_dump()


@mcp.tool()
async def search_knowledge(query: str, top_k: int = 5) -> dict[str, Any]:
    """检索企业内部知识库：按关键词在示例文档中检索并返回最相关的片段。

    Args:
        query: 检索关键词，如 "补货审批"
        top_k: 返回结果数量上限，默认 5
    """
    hits = _search_knowledge_impl(query, top_k)
    return {
        "success": True,
        "data": {"query": query, "top_k": top_k, "hits": hits, "note": "示例知识库，仅用于演示"},
        "error": None,
    }


@mcp.tool()
async def http_get(url: str) -> dict[str, Any]:
    """发起 HTTP GET 请求并返回响应内容（JSON 或文本）。

    Args:
        url: 目标 URL
    """
    result = await HttpGetTool().run_safe(HttpGetInput(url=url))
    return result.model_dump()


@mcp.tool()
async def http_post(url: str, json: dict[str, Any]) -> dict[str, Any]:
    """发起 HTTP POST 请求（携带 JSON 请求体）并返回响应内容。

    Args:
        url: 目标 URL
        json: 请求体 JSON 对象
    """
    result = await HttpPostTool().run_safe(HttpPostInput(url=url, json=json))
    return result.model_dump()


# ---------------------------------------------------------------------------
# 资源（Resources）
# ---------------------------------------------------------------------------


@mcp.resource("enterprise://inventory/{product_code}")
async def inventory_resource(product_code: str) -> str:
    """资源：按产品编码读取库存信息（示例数据）。"""
    item = MOCK_INVENTORY.get(product_code)
    if item is None:
        return f"未找到产品编码 {product_code} 的库存记录（示例数据）"
    return str(item)


@mcp.resource("enterprise://orders/{order_id}")
async def order_resource(order_id: str) -> str:
    """资源：按订单号读取订单状态（示例数据）。"""
    order = MOCK_ORDERS.get(order_id)
    if order is None:
        return f"未找到订单号 {order_id} 的订单记录（示例数据）"
    return str(order)


# ---------------------------------------------------------------------------
# 提示模板（Prompts）
# ---------------------------------------------------------------------------


@mcp.prompt()
def replenishment_prompt(sku_list: list[str]) -> str:
    """提示模板：输入 SKU 列表，返回补货建议的系统提示词。

    Args:
        sku_list: 需要生成补货建议的 SKU 列表
    """
    sku_text = "、".join(sku_list) if sku_list else "（空列表）"
    return (
        f"你是一位资深的供应链补货顾问（演示角色）。\n"
        f"请针对以下 SKU 列表：{sku_text}，结合可用库存工具（query_inventory、generate_replenishment）"
        f"逐一评估库存状态并给出补货建议：\n"
        f"1. 先调用 query_inventory 查询每个 SKU 的当前库存与安全库存；\n"
        f"2. 调用 generate_replenishment 获取建议补货量；\n"
        f"3. 对需要补货的 SKU 说明补货数量、优先级与备注；\n"
        f"4. 库存充足的 SKU 说明无需补货。\n"
        f"注意：当前所有数据均为示例数据，仅用于演示。"
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI 入口：以 stdio 模式启动 MCP Server。"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("enterprise-agent-tools MCP Server starting ...")
    mcp.run()


if __name__ == "__main__":
    main()
