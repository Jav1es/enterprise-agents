"""对话路由 — 同步 /v1/chat 与 SSE 流式 /v1/chat/stream。"""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from enterprise_agent.api.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _workflow():
    """获取全局 AgentWorkflow 实例。

    TODO: 从应用生命周期容器中获取（当前返回 None 占位）。
    """
    return None


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """同步对话接口。"""
    workflow = _workflow()
    if workflow is None:
        raise HTTPException(status_code=503, detail="Agent 工作流尚未初始化")

    start = time.perf_counter()
    # TODO: 注入记忆历史与 RAG 证据
    # result = await workflow.ainvoke({
    #     "user_input": request.message,
    #     "session_id": request.session_id,
    #     "chat_history": [],
    # })
    result = {"final_output": ""}
    latency_ms = int((time.perf_counter() - start) * 1000)

    return ChatResponse(
        session_id=request.session_id,
        reply=result.get("final_output", ""),
        trace_id=f"trc_{uuid.uuid4().hex[:8]}",
        latency_ms=latency_ms,
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> EventSourceResponse:
    """SSE 流式对话接口。"""
    workflow = _workflow()
    if workflow is None:
        raise HTTPException(status_code=503, detail="Agent 工作流尚未初始化")

    async def event_generator():
        # TODO: workflow.astream() 逐事件产出
        # async for event in workflow.astream({...}):
        #     yield {"event": "message", "data": json.dumps(event)}
        yield {"event": "message", "data": json.dumps({"delta": ""})}
        yield {"event": "message", "data": json.dumps({"delta": "[DONE]"})}

    return EventSourceResponse(event_generator())
