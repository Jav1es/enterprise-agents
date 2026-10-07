"""离线 StubLLM：不联网的假模型，用于零成本压测与离线演练。

用途：没有 LLM Key 时 `ChatOpenAI` 构造失败 → workflow=None → 业务接口一律 503，
于是压测只能测到「路由与降级路径」（P50≈1ms），**测不到完整编排的真实开销**。

本模块提供一个满足 LangChain BaseChatModel 契约的本地实现：
- 输出固定内容，不发任何网络请求
- 做少量字符串计算，让 CPU 开销不至于为零（避免低估编排成本）
- 记录调用次数，便于确认编排节点确实执行过

由环境变量 `EA_STUB_LLM=1` 启用（见 api/main.py），不影响生产路径。
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_STATS = {"calls": 0, "chars": 0}


def stub_stats() -> dict[str, int]:
    return dict(_STATS)


def reset_stats() -> None:
    _STATS["calls"] = 0
    _STATS["chars"] = 0


class StubLLM(BaseChatModel):
    """固定输出的离线路径模型。"""

    temperature: float = 0.0
    model_name: str = "stub-llm"

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        _STATS["calls"] += 1
        # 做一点真实计算，避免「零成本模型」把编排开销测得过轻
        # （目标是对齐真实推理的量级，而非精确复现）
        blob = " ".join(str(getattr(m, "content", "")) for m in messages)
        digest = hash(blob) & 0xFFFF
        time.sleep(0.002)  # 约 2ms，模拟单次推理的最小开销
        text = f"[stub] 分析 {len(blob)} 字符，摘要 {digest:04x}。"
        _STATS["chars"] += len(text)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    def bind_tools(self, tools: Any, **kwargs: Any):
        """编排层会绑定工具；stub 不真调工具，原样返回。"""
        return self
