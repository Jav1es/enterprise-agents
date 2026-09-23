"""工具注册中心 — 统一管理企业工具。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册与发现。"""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool
        logger.info("工具已注册: %s", tool.name)

    def unregister(self, name: str) -> None:
        """注销工具。"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[BaseTool]:
        """按名称获取工具。"""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """列出全部工具。"""
        return list(self._tools.values())

    def to_langchain_tools(self) -> List[Any]:
        """批量转换为 LangChain Tool。"""
        return [t.to_langchain_tool() for t in self._tools.values()]
