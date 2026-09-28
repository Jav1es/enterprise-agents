"""工具抽象基类：BaseTool / ToolInput / ToolOutput。

本文件精简复用于开源项目 enterprise-agents（https://github.com/Jav1es/enterprise-agents，MIT License），
保留原作者 MIT 归属注释；为适配 MCP 场景移除了 LangChain 集成部分，仅保留核心抽象与 Schema 约束。

MIT License

Copyright (c) 2025 Jav1es

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

# 泛型参数：输入 / 输出 Schema 类型
TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


class ToolInput(BaseModel):
    """工具输入基类：所有工具入参 Schema 的父类。

    派生类只需声明字段与默认值，Pydantic 负责校验与文档化。
    """


class ToolOutput(BaseModel):
    """工具输出基类：统一承载工具结果。

    - success：是否成功
    - data：结构化结果（任意 JSON 可序列化内容）
    - error：失败时的错误信息（成功时为空）
    """

    success: bool = Field(default=True, description="是否执行成功")
    data: Any = Field(default=None, description="结构化结果数据")
    error: str | None = Field(default=None, description="失败时的错误描述")

    @classmethod
    def ok(cls, data: Any) -> "ToolOutput":
        """构造成功输出。"""
        return cls(success=True, data=data, error=None)

    @classmethod
    def fail(cls, message: str) -> "ToolOutput":
        """构造失败输出。"""
        return cls(success=False, data=None, error=message)


class BaseTool(ABC, Generic[TInput, TOutput]):
    """工具抽象基类：统一工具的名称、描述与执行入口。

    派生类必须实现：
    - name / description：工具元信息，供 LLM 理解用途
    - input_schema / output_schema：输入输出 Pydantic 模型
    - run()：实际业务逻辑

    通过 run_safe() 包装，保证任何异常都转化为 ToolOutput.fail，不让异常泄漏到 MCP 层。
    """

    # 工具名称（MCP 暴露名）
    name: str = "base_tool"
    # 工具描述（供 LLM 判断何时调用）
    description: str = ""

    # 输入 / 输出 Schema
    input_schema: type[TInput] = ToolInput
    output_schema: type[TOutput] = ToolOutput

    @abstractmethod
    async def run(self, args: TInput) -> TOutput:
        """执行工具核心逻辑（子类实现）。"""
        raise NotImplementedError

    async def run_safe(self, args: TInput) -> TOutput:
        """安全执行入口：捕获一切异常并转为失败输出。"""
        try:
            return await self.run(args)
        except Exception as exc:  # noqa: BLE001 - 兜底异常捕获
            return self.output_schema.fail(f"[{self.name}] 执行失败: {exc}")  # type: ignore[attr-defined]
