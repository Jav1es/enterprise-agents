"""LangGraph 工作流节点实现。

节点: router / planner / retrieve / tool_call / reviewer / respond
TODO: 补充各节点内的 LLM 调用与结构化输出（Pydantic）实现。

可观测性: 所有节点经 traced_node 打点，span 名称为 agent.node.<node>，
trace_id 由外层根 span（agent.workflow.invoke）贯穿整条链路。
"""

from __future__ import annotations

import logging
from typing import Any

from enterprise_agent.observability.telemetry import traced_node

from .state import AgentState

logger = logging.getLogger(__name__)


@traced_node("agent.node.router")
async def router_node(state: AgentState) -> dict[str, Any]:
    """路由节点：判断任务类型（knowledge / data / mixed）。

    TODO: 基于 LLM + Pydantic 结构化输出识别用户意图，返回 route 字段。
    """
    return {"route": "mixed", "step_number": state.get("step_number", 0) + 1}


@traced_node("agent.node.planner")
async def planner_node(state: AgentState) -> dict[str, Any]:
    """规划节点：将任务拆解为可执行的步骤计划。

    TODO: 调用 LLM 生成 Plan 并写入 intermediate_steps。
    """
    return {"step_number": state.get("step_number", 0) + 1}


@traced_node("agent.node.retrieve")
async def retrieve_node(state: AgentState) -> dict[str, Any]:
    """知识检索节点：从 RAG 知识库检索证据。

    TODO: 调用 knowledge 层 HybridRetriever，结果写入 knowledge_evidence。
    """
    return {"step_number": state.get("step_number", 0) + 1}


@traced_node("agent.node.tool_call")
async def tool_call_node(state: AgentState) -> dict[str, Any]:
    """工具调用节点：执行规划中选择的工具。

    TODO: 经 ToolExecutor 执行工具，结果写入 tool_results。
    """
    return {"step_number": state.get("step_number", 0) + 1}


@traced_node("agent.node.reviewer")
async def reviewer_node(state: AgentState) -> dict[str, Any]:
    """评审节点：校验工具结果 / 补货量等关键输出。

    TODO: 结构化校验，必要时触发重试或修正。
    """
    return {"step_number": state.get("step_number", 0) + 1}


@traced_node("agent.node.respond")
async def respond_node(state: AgentState, llm: Any | None = None) -> dict[str, Any]:
    """回复节点：汇总证据与工具结果，调用 LLM 生成最终回答。"""
    user_input = (state.get("user_input") or "").strip()
    if llm is not None and user_input:
        try:
            resp = await llm.ainvoke([{"role": "user", "content": user_input}])
            content = getattr(resp, "content", None) or str(resp)
            return {"final_output": str(content), "step_number": state.get("step_number", 0) + 1}
        except Exception as exc:  # noqa: BLE001 - LLM 调用失败时返回错误提示，不阻断响应
            logger.error("respond 节点 LLM 调用失败: %s", exc)
            return {
                "final_output": f"（LLM 调用失败：{exc}）",
                "step_number": state.get("step_number", 0) + 1,
            }
    return {"final_output": "", "step_number": state.get("step_number", 0) + 1}
