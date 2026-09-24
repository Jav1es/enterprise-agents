#!/usr/bin/env python3
"""OpenTelemetry 全链路可观测性演示 — 上报本地 Jaeger 并展示阶段耗时。

流程:
    1. 初始化 OTel（OTLP HTTP -> http://localhost:4318/v1/traces）
    2. 模拟一次完整 Agent 会话（编排链路与 graph.py 一致）:
        根 span: agent.workflow.invoke（trace_id 贯穿整条链路）
        子 span: agent.node.router -> agent.node.retrieve -> agent.node.planner
              -> agent.node.tool_call -> agent.node.planner(循环)
              -> agent.node.reviewer -> agent.node.respond
    3. 打印 trace_id 与各阶段耗时（Jaeger 内可查 span 的 agent.node.duration_ms）

用法:
    PYTHONPATH=src python examples/observability/run_trace_demo.py
    # 前置: 本地 Jaeger 已启动（docker compose up -d jaeger 或 jaeger-all-in-one.exe）
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from enterprise_agent.observability.telemetry import get_tracer, init_telemetry  # noqa: E402
from enterprise_agent.orchestration.nodes import (  # noqa: E402
    planner_node,
    respond_node,
    retrieve_node,
    reviewer_node,
    router_node,
    tool_call_node,
)
from enterprise_agent.orchestration.state import AgentState  # noqa: E402

# 编排阶段（与 graph.py mixed 分支一致：router -> retrieve -> planner -> tool 循环 -> reviewer -> respond）
STAGES = [
    ("Router   (agent.node.router)", router_node),
    ("Planner  (agent.node.planner)", planner_node),
    ("Retrieve (agent.node.retrieve)", retrieve_node),
    ("Tool     (agent.node.tool_call)", tool_call_node),
    ("Planner  (agent.node.planner, tool 循环)", planner_node),
    ("Reviewer (agent.node.reviewer)", reviewer_node),
    ("Respond  (agent.node.respond)", respond_node),
]


async def main() -> None:
    init_telemetry()  # OTLP -> http://localhost:4318/v1/traces

    session_id = f"obs-demo-{uuid.uuid4().hex[:8]}"
    state: AgentState = {
        "user_input": "请帮我查一下本月各区域销售业绩并生成分析报告",
        "session_id": session_id,
        "route": "mixed",
        "chat_history": [],
        "step_number": 0,
    }

    tracer = get_tracer()
    print("=" * 72)
    print("Enterprise Agent — OpenTelemetry 全链路可观测性演示")
    print(f"session_id : {session_id}")
    print(f"OTLP       : {os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318/v1/traces')}")
    print("=" * 72)

    with tracer.start_as_current_span("agent.workflow.invoke") as root:
        root.set_attribute("agent.session_id", session_id)
        root.set_attribute("agent.user_input", state["user_input"])
        trace_id = root.get_span_context().trace_id

        for label, node_fn in STAGES:
            start = time.perf_counter()
            result = await node_fn(state)  # 节点内部已由 traced_node 打点
            elapsed_ms = (time.perf_counter() - start) * 1000
            state.update(result)
            print(f"  [{label:<46}] {elapsed_ms:8.3f} ms")

    print("-" * 72)
    print(f"trace_id   : {trace_id:032x}")
    print("下一步     : 打开 Jaeger UI http://localhost:16686 ，服务选择 enterprise-agent")
    print("           : 点击最新 trace 即可看到各阶段 span 与耗时")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
