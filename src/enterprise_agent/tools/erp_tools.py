"""ERP / CRM 企业系统工具封装。"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from .base import BaseTool, ToolOutput

logger = logging.getLogger(__name__)


class InventoryQueryInput(BaseModel):
    """库存查询入参。"""

    product_code: str = Field(description="产品编码")


class ERPClient:
    """ERP 客户端连接（凭证经环境变量注入，严禁硬编码）。"""

    def __init__(self) -> None:
        import os

        self._api_url = os.getenv("ERP_API_URL", "")
        self._api_token = os.getenv("ERP_API_TOKEN", "")
        # TODO: 初始化 httpx.AsyncClient

    async def get_inventory(self, product_code: str) -> dict[str, Any]:
        """查询库存。"""
        # TODO: 调用 ERP HTTP 接口
        return {"product_code": product_code, "stock": 0}

    async def __aenter__(self) -> ERPClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        pass


class QueryInventoryTool(BaseTool):
    """查询 ERP 系统中的库存信息。"""

    name = "query_inventory"
    description = "查询ERP系统中的库存信息"
    args_schema = InventoryQueryInput

    async def run(self, **kwargs: Any) -> ToolOutput:
        product_code = kwargs.get("product_code", "")
        async with ERPClient() as client:
            data = await client.get_inventory(product_code)
        return ToolOutput(success=True, data=data)
