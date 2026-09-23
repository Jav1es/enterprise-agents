"""FastAPI 应用入口。

启动: uv run uvicorn enterprise_agent.api.main:app --reload --port 8080
文档: http://localhost:8080/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from enterprise_agent.config.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化依赖（LLM / 记忆 / RAG / 工具注册）。"""
    settings = get_settings()
    # TODO: 初始化 AgentWorkflow / 记忆存储 / RAG 检索器 / 工具注册中心
    logger.info("Enterprise Agent 启动, env=%s", settings.app_env)
    yield
    # TODO: 关闭连接池 / MCP 会话
    logger.info("Enterprise Agent 已关闭")


app = FastAPI(
    title="Enterprise Agent API",
    description="面向企业场景的本地智能体系统 API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """健康检查接口。"""
    return {"status": "ok", "service": "enterprise-agent", "version": "1.0.0"}


# 路由注册
from enterprise_agent.api.routes import chat  # noqa: E402

app.include_router(chat.router, prefix="/v1", tags=["chat"])
