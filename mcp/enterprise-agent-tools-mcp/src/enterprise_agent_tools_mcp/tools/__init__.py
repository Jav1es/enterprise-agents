"""tools 包：企业工具实现层。

- base.py：精简复用的 BaseTool / ToolInput / ToolOutput 抽象（MIT，派生自 enterprise-agents）
- erp.py：ERP 域工具（库存 / 订单 / 补货建议），mock 数据 + 接口占位
- http.py：通用 HTTP 工具（http_get / http_post）
"""

from enterprise_agent_tools_mcp.tools.base import BaseTool, ToolInput, ToolOutput

__all__ = ["BaseTool", "ToolInput", "ToolOutput"]
