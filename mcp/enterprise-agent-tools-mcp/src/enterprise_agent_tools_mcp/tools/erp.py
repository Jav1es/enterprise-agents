"""ERP 域工具：库存查询 / 订单状态 / 补货建议。

实现策略：
- 所有数据均为 mock 示例数据（标注"示例"），不包含任何真实企业名 / 真实密钥 / 真实客户数据；
- 若配置了 ERP_API_URL / ERP_API_TOKEN，则尝试调用真实接口（占位逻辑），失败时自动降级到 mock；
- 保证"无真实 API Key 也能运行"。
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from enterprise_agent_tools_mcp.tools.base import BaseTool, ToolInput, ToolOutput

# ---------------------------------------------------------------------------
# mock 示例数据（仅用于演示，标注"示例"）
# ---------------------------------------------------------------------------

# 示例库存表：product_code -> 库存信息（示例数据）
MOCK_INVENTORY: dict[str, dict[str, Any]] = {
    "SKU-DEMO-001": {
        "product_code": "SKU-DEMO-001",
        "product_name": "示例商品A（库存演示）",
        "warehouse": "华东仓（示例）",
        "quantity": 120,
        "safety_stock": 50,
        "unit": "件",
        "note": "示例数据",
    },
    "SKU-DEMO-002": {
        "product_code": "SKU-DEMO-002",
        "product_name": "示例商品B（库存演示）",
        "warehouse": "华南仓（示例）",
        "quantity": 18,
        "safety_stock": 40,
        "unit": "箱",
        "note": "示例数据",
    },
    "SKU-DEMO-003": {
        "product_code": "SKU-DEMO-003",
        "product_name": "示例商品C（库存演示）",
        "warehouse": "华北仓（示例）",
        "quantity": 200,
        "safety_stock": 60,
        "unit": "件",
        "note": "示例数据",
    },
}

# 示例订单表：order_id -> 订单状态（示例数据）
MOCK_ORDERS: dict[str, dict[str, Any]] = {
    "ORD-DEMO-1001": {
        "order_id": "ORD-DEMO-1001",
        "status": "已发货（示例）",
        "customer": "示例客户X",
        "items": ["SKU-DEMO-001 x 20", "SKU-DEMO-003 x 10"],
        "created_at": "2026-09-20 10:30:00（示例）",
        "note": "示例数据",
    },
    "ORD-DEMO-1002": {
        "order_id": "ORD-DEMO-1002",
        "status": "待发货（示例）",
        "customer": "示例客户Y",
        "items": ["SKU-DEMO-002 x 5"],
        "created_at": "2026-09-25 14:00:00（示例）",
        "note": "示例数据",
    },
}


def _erp_api_configured() -> bool:
    """判断是否配置了真实 ERP 接口（未配置则走 mock 降级）。"""
    return bool(os.getenv("ERP_API_URL")) and bool(os.getenv("ERP_API_TOKEN"))


# ---------------------------------------------------------------------------
# 库存查询工具
# ---------------------------------------------------------------------------


class QueryInventoryInput(ToolInput):
    """查询库存入参。"""

    product_code: str = Field(description="产品编码，如 SKU-DEMO-001")


class QueryInventoryTool(BaseTool[QueryInventoryInput, ToolOutput]):
    """查询 ERP 库存：优先走真实接口（占位），未配置或失败时降级到 mock 示例数据。"""

    name = "query_inventory"
    description = "根据产品编码查询 ERP 库存信息（数量、仓库、安全库存）。未配置 ERP_API_URL 时返回示例数据。"

    input_schema = QueryInventoryInput
    output_schema = ToolOutput

    async def run(self, args: QueryInventoryInput) -> ToolOutput:
        product_code = args.product_code.strip()

        # 真实接口占位：若配置了 ERP_API_URL / ERP_API_TOKEN，此处应调用真实接口
        # （示例仅保留占位注释，正式接入时替换为 httpx 请求）
        if _erp_api_configured():
            # TODO: 接入真实 ERP 查询接口，例如 GET {ERP_API_URL}/inventory/{product_code}
            # 真实接口失败或超时时，建议降级到下方 mock 分支，保证服务可用
            pass

        # mock 降级：返回示例数据（标注"示例"）
        item = MOCK_INVENTORY.get(product_code)
        if item is None:
            return ToolOutput.fail(f"未找到产品编码 {product_code} 的库存记录（当前为示例数据，仅有 SKU-DEMO-001/002/003）")
        return ToolOutput.ok(item)


# ---------------------------------------------------------------------------
# 订单状态查询工具
# ---------------------------------------------------------------------------


class GetOrderStatusInput(ToolInput):
    """查询订单状态入参。"""

    order_id: str = Field(description="订单号，如 ORD-DEMO-1001")


class GetOrderStatusTool(BaseTool[GetOrderStatusInput, ToolOutput]):
    """查询订单状态：优先走真实接口（占位），未配置或失败时降级到 mock 示例数据。"""

    name = "get_order_status"
    description = "根据订单号查询订单状态（状态、客户、商品明细）。未配置 ERP_API_URL 时返回示例数据。"

    input_schema = GetOrderStatusInput
    output_schema = ToolOutput

    async def run(self, args: GetOrderStatusInput) -> ToolOutput:
        order_id = args.order_id.strip()

        # 真实接口占位：与 query_inventory 相同的降级策略
        if _erp_api_configured():
            # TODO: 接入真实 ERP 订单接口，例如 GET {ERP_API_URL}/orders/{order_id}
            pass

        # mock 降级：返回示例数据（标注"示例"）
        order = MOCK_ORDERS.get(order_id)
        if order is None:
            return ToolOutput.fail(f"未找到订单号 {order_id} 的订单记录（当前为示例数据，仅有 ORD-DEMO-1001/1002）")
        return ToolOutput.ok(order)


# ---------------------------------------------------------------------------
# 补货建议生成工具
# ---------------------------------------------------------------------------


class GenerateReplenishmentInput(ToolInput):
    """生成补货建议入参。"""

    sku_list: list[str] = Field(default_factory=list, description="需要评估的 SKU 列表，如 ['SKU-DEMO-001', 'SKU-DEMO-002']")


class GenerateReplenishmentTool(BaseTool[GenerateReplenishmentInput, ToolOutput]):
    """根据 SKU 列表 + mock 库存生成补货建议（建议数量 = 安全库存 - 当前库存，最低为 0）。"""

    name = "generate_replenishment"
    description = "输入 SKU 列表，结合当前库存与安全库存生成补货建议清单（基于示例数据）。"

    input_schema = GenerateReplenishmentInput
    output_schema = ToolOutput

    async def run(self, args: GenerateReplenishmentInput) -> ToolOutput:
        skus = [s.strip() for s in args.sku_list if s and s.strip()]
        if not skus:
            return ToolOutput.fail("sku_list 不能为空")

        suggestions = []
        for sku in skus:
            item = MOCK_INVENTORY.get(sku)
            if item is None:
                suggestions.append(
                    {
                        "sku": sku,
                        "exists": False,
                        "suggestion": f"SKU {sku} 未收录于示例库存表，请人工核实（示例数据）",
                    }
                )
                continue
            # 建议补货量 = 安全库存 - 当前库存；已充足则建议 0
            suggest_qty = max(0, int(item["safety_stock"]) - int(item["quantity"]))
            suggestions.append(
                {
                    "sku": sku,
                    "exists": True,
                    "product_name": item["product_name"],
                    "current_qty": item["quantity"],
                    "safety_stock": item["safety_stock"],
                    "suggest_qty": suggest_qty,
                    "level": "需要补货" if suggest_qty > 0 else "库存充足",
                    "note": "示例数据",
                }
            )

        return ToolOutput.ok(
            {
                "generated_at": "2026-09-28（示例）",
                "count": len(suggestions),
                "suggestions": suggestions,
                "note": "以上为基于示例数据的补货建议，正式使用请替换为真实库存",
            }
        )
