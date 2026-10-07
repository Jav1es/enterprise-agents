"""调用预算闸：给 LLM 调用次数设硬上限，超了就熔断。

背景（真实事故）：多轮压测里服务继承了真实 LLM Key，每分钟都在打计费调用；
期间还因 429 重试白烧一轮。事后才意识到「起服务」与「花钱」之间没有闸门。

本模块提供一个**运行时**兜底：即使环境变量里不慎带了真 Key，
只要设置了 BENCH_MAX_CALLS，超过该次数后所有业务接口立即返回 503，
不再触发任何 LLM 调用。

用法：
    export BENCH_MAX_CALLS=100        # 最多 100 次，之后自动熔断
    # 或不设（默认关闭）

生产环境同样可用（未设该变量时本模块不产生任何开销）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CallBudget:
    """进程内调用预算。线程/事件循环安全：asyncio 单线程下自增不会交错。"""

    limit: int = 0
    used: int = 0
    tripped: bool = False

    def charge(self, n: int = 1) -> bool:
        """记一次调用。返回 False 表示已熔断（调用方应拒绝服务）。"""
        if not self.limit:
            return True  # 未启用预算
        if self.tripped:
            return False
        self.used += n
        if self.used >= self.limit:
            self.tripped = True
            logger.error(
                "LLM 调用预算已耗尽（used=%d limit=%d），已熔断，"
                "后续业务请求将返回 503，不再产生任何计费调用",
                self.used, self.limit,
            )
            return False
        return True

    def remaining(self) -> int | None:
        return None if not self.limit else max(0, self.limit - self.used)


_budget = CallBudget(limit=int(os.environ.get("BENCH_MAX_CALLS", "0") or 0))

if _budget.limit:
    logger.warning("已启用 LLM 调用预算上限：%d 次", _budget.limit)


def get_budget() -> CallBudget:
    return _budget


def budget_status() -> dict:
    b = _budget
    return {"enabled": bool(b.limit), "limit": b.limit, "used": b.used,
            "remaining": b.remaining(), "tripped": b.tripped}
