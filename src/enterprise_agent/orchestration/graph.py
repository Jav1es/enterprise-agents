"""LangGraph 图结构构建 — AgentWorkflow。

链路: Router → Planner → Skill → Tool → Reviewer → END
支持多步工具调用循环（tool_call -> planner）与条件分支。
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from enterprise_agent.observability.telemetry import get_tracer

from .nodes import (
    planner_node,
    respond_node,
    retrieve_node,
    reviewer_node,
    router_node,
    tool_call_node,
)
from .state import AgentState

logger = logging.getLogger(__name__)


class AgentWorkflow:
    """企业级 Agent 工作流（LangGraph StateGraph）。"""

    def __init__(
        self,
        llm: Any,
        tools: list[Any] | None = None,
        memory_manager: Any = None,
        retriever: Any = None,
    ) -> None:
        self.llm = llm
        self.tools = tools or []
        self.tool_executor = ToolNode(self.tools)
        self.memory = memory_manager
        self.retriever = retriever
        self.graph: Any = self._build_graph()

    def _route_decision(self, state: AgentState) -> str:
        """根据 route 字段选择后续节点。"""
        return state.get("route", "mixed")

    def _should_call_tool(self, state: AgentState) -> str:
        """判断下一步是调用工具还是直接回复。"""
        # TODO: 根据 planner 输出判断是否仍需要调用工具
        return "tool" if not state.get("tool_results") else "respond"

    def _build_graph(self) -> Any:
        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("router", router_node)
        graph.add_node("planner", planner_node)
        graph.add_node("retrieve", retrieve_node)
        graph.add_node("tool_call", tool_call_node)
        graph.add_node("reviewer", reviewer_node)
        graph.add_node("respond", respond_node)

        # 入口与路由分支
        graph.set_entry_point("router")
        graph.add_conditional_edges(
            "router",
            self._route_decision,
            {"knowledge": "retrieve", "data": "planner", "mixed": "retrieve"},
        )

        # 边连接
        graph.add_edge("retrieve", "planner")
        graph.add_conditional_edges(
            "planner",
            self._should_call_tool,
            {"tool": "tool_call", "respond": "reviewer"},
        )
        graph.add_edge("tool_call", "planner")  # 多步工具调用循环
        graph.add_edge("reviewer", "respond")
        graph.add_edge("respond", END)

        return graph.compile()

    async def ainvoke(self, state: AgentState) -> AgentState:
        """异步执行工作流。

        根 span（agent.workflow.invoke）贯穿整条链路：节点 span
        （agent.node.router / planner / tool_call / reviewer ...）自动
        继承根 span 的 trace_id，可在 Jaeger 中按 trace 聚合查看阶段耗时。
        """
        tracer = get_tracer()
        with tracer.start_as_current_span("agent.workflow.invoke") as root:
            root.set_attribute("agent.session_id", str(state.get("session_id", "") or ""))
            root.set_attribute("agent.user_input", str((state.get("user_input") or "")[:200]))
            result = await self.graph.ainvoke(state)
        return result

    def invoke(self, state: AgentState) -> AgentState:
        """同步执行工作流。"""
        tracer = get_tracer()
        with tracer.start_as_current_span("agent.workflow.invoke") as root:
            root.set_attribute("agent.session_id", str(state.get("session_id", "") or ""))
            root.set_attribute("agent.user_input", str((state.get("user_input") or "")[:200]))
            result = self.graph.invoke(state)
        return result
