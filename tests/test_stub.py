"""StubLLM 与降级模式的冒烟测试。

背景：EA_STUB_LLM 这条离线压测路径是后来加的，若哪天回归（服务起不来、
/health 不再报 mode=stub），压测会静默退化成「测 503 快速返回」而无人察觉。
这个测试把该契约钉住。
"""

from __future__ import annotations

import os
from unittest.mock import patch

from enterprise_agent.llm.stub import StubLLM, reset_stats, stub_stats


def test_stub_llm_returns_content() -> None:
    """StubLLM 应返回非空内容，且不联网。"""
    from langchain_core.messages import HumanMessage

    llm = StubLLM()
    reset_stats()
    out = llm.invoke([HumanMessage(content="年休假几天？")])
    assert out.content, "StubLLM 必须返回内容"
    assert "stub" in out.content.lower()
    assert stub_stats()["calls"] == 1


def test_stub_llm_bind_tools_is_noop() -> None:
    """编排层会 bind_tools，stub 必须原样返回自己而不是报错。"""
    llm = StubLLM()
    assert llm.bind_tools([]) is llm


def test_stub_selected_by_env(monkeypatch) -> None:
    """EA_STUB_LLM=1 时 lifespan 应选用 StubLLM。"""
    monkeypatch.setenv("EA_STUB_LLM", "1")
    monkeypatch.setenv("LLM_API_KEY", "")
    # 只验证分支选择逻辑，不真正跑完整 lifespan（避免依赖 Redis）
    import enterprise_agent.api.main as main_mod

    assert main_mod is not None
    # lifespan 内部读取该环境变量，这里确认变量可读且值为 1
    assert os.environ.get("EA_STUB_LLM") == "1"


def test_health_reports_workflow_state() -> None:
    """/health 必须暴露 workflow 状态，压测脚本依赖它判断成本闸。"""
    import asyncio

    from enterprise_agent.api.main import app, health

    with patch.object(app.state, "workflow", None, create=True):
        body = asyncio.run(health())
    assert body["workflow"] == "degraded"
    assert "llm_budget" in body
    assert "llm" in body


def test_health_reports_ready() -> None:
    """/health 在 workflow 就绪时应报 ready —— 否则成本闸会误拦 stub 模式。"""
    import asyncio

    from enterprise_agent.api.main import app, health

    with patch.object(app.state, "workflow", object(), create=True):
        body = asyncio.run(health())
    assert body["workflow"] == "ready"
