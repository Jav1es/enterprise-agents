"""Agent 状态定义 — LangGraph State 类型。"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    """贯穿整个 Agent 工作流的状态对象。

    字段说明：
        user_input: 用户输入
        session_id: 会话标识
        route: 任务路由结果 (knowledge | data | mixed)
        chat_history: 对话历史（OpenAI 消息格式）
        intermediate_steps: 执行轨迹
        knowledge_evidence: 检索到的知识证据
        tool_results: 工具调用结果
        final_output: 最终输出
        retry_count: 重试计数
        step_number: 当前步骤编号
        errors: 错误记录
    """

    user_input: str
    session_id: str
    route: Literal["knowledge", "data", "mixed"]
    chat_history: list[dict[str, Any]]
    intermediate_steps: list[tuple[str, str, Any]]
    knowledge_evidence: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    final_output: str | None
    retry_count: int
    step_number: int
    errors: list[str]
