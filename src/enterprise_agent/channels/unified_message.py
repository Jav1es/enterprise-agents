"""统一消息模型 — 解决多平台消息格式差异。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UnifiedMessage(BaseModel):
    """多平台统一消息模型。"""

    platform: str = Field(description="dingtalk | wecom | oa | erp")
    user_id: str
    session_id: str
    content: str
    content_type: str = "text"
    channel_token: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    """API 同步/流式对话请求。"""

    session_id: str
    user_id: str
    message: str
    channel: str = "api"
    stream: bool = False


class ChatResponse(BaseModel):
    """API 对话响应（统一 UnifiedMessage 结构）。"""

    session_id: str
    reply: str
    trace_id: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: int = 0
