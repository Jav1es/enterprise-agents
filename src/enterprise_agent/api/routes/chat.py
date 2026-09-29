"""对话路由 — 同步 /v1/chat 与 SSE 流式 /v1/chat/stream。"""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from enterprise_agent.api.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _workflow(request: Request):
    """从应用生命周期容器中获取全局 AgentWorkflow 实例。"""
    return getattr(request.app.state, "workflow", None)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """同步对话接口。"""
    workflow = _workflow(request)
    if workflow is None:
        raise HTTPException(status_code=503, detail="Agent 工作流尚未初始化")

    start = time.perf_counter()
    # 注入记忆历史与 RAG 证据
    state = {
        "user_input": body.message,
        "session_id": body.session_id,
        "chat_history": [],
    }
    result = await workflow.ainvoke(state)
    latency_ms = int((time.perf_counter() - start) * 1000)

    return ChatResponse(
        session_id=body.session_id,
        reply=result.get("final_output") or "",
        trace_id=f"trc_{uuid.uuid4().hex[:8]}",
        latency_ms=latency_ms,
    )


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> EventSourceResponse:
    """SSE 流式对话接口。"""
    workflow = _workflow(request)
    if workflow is None:
        raise HTTPException(status_code=503, detail="Agent 工作流尚未初始化")

    async def event_generator():
        # workflow.astream() 逐事件产出
        async for event in workflow.graph.astream(
            {
                "user_input": body.message,
                "session_id": body.session_id,
                "chat_history": [],
            },
            stream_mode="messages",
        ):
            if isinstance(event, tuple):
                chunk = event[0]
                text = getattr(chunk, "content", "")
            else:
                text = str(event)
            if text:
                yield {"event": "message", "data": json.dumps({"delta": text})}
        yield {"event": "message", "data": json.dumps({"delta": "[DONE]"})}

    return EventSourceResponse(event_generator())
