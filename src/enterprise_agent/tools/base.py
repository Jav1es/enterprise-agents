"""工具层基础抽象 — Pydantic Schema 严格定义输入/输出。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from pydantic import BaseModel, Field


class ToolInput(BaseModel):
    """工具输入 Schema 基类。"""


class ToolOutput(BaseModel):
    """工具输出 Schema 基类。"""

    success: bool = True
    data: Dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class BaseTool(ABC):
    """企业工具统一接口。

    所有企业系统工具（ERP/CRM/钉钉/企微）继承本类，
    通过 Pydantic args_schema 使 LLM 准确理解工具用途。
    """

    name: str = ""
    description: str = ""
    args_schema: type[BaseModel] = ToolInput

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolOutput:
        """执行工具逻辑。"""
        raise NotImplementedError

    def to_langchain_tool(self) -> Any:
        """转换为 LangChain Tool。"""
        from langchain_core.tools import StructuredTool

        return StructuredTool.from_function(
            name=self.name,
            description=self.description,
            func=self.run,
            args_schema=self.args_schema,
        )
