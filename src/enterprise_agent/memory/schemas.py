"""记忆层数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Fact(BaseModel):
    """事实三元组。"""

    id: Optional[int] = None
    session_id: str
    user_id: str = ""
    subject: str = Field(description="主体")
    predicate: str = Field(description="谓词")
    object: str = Field(description="客体")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    access_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None


class MemoryStats(BaseModel):
    """记忆层统计信息。"""

    short_term_sessions: int = 0
    long_term_facts: int = 0
    redis_memory_usage_bytes: int = 0
