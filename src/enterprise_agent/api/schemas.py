"""API 数据模型。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求（兼容 UnifiedMessage 语义）。"""

    session_id: str
    user_id: str
    message: str
    channel: str = "api"
    stream: bool = False


class Citation(BaseModel):
    """引用来源。"""

    source: str
    chunk_id: int
    score: float


class ChatResponse(BaseModel):
    """对话响应。"""

    session_id: str
    reply: str
    trace_id: str = ""
    citations: List[Citation] = Field(default_factory=list)
    latency_ms: int = 0
