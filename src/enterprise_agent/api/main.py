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
    try:
        # --- LLM ---
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0.3,
            timeout=60,
        )
        logger.info("LLM 初始化完成: model=%s base_url=%s", settings.llm_model, settings.llm_base_url)

        # --- 记忆层（Redis 短期记忆） ---
        from enterprise_agent.memory.short_term import ShortTermMemory

        memory = ShortTermMemory(settings.redis_url, settings.redis_short_term_ttl)
        logger.info("短期记忆初始化完成: redis=%s", settings.redis_url)

        # --- 工具注册中心 ---
        from enterprise_agent.tools.registry import ToolRegistry

        registry = ToolRegistry()

        # --- Agent 工作流 ---
        from enterprise_agent.orchestration.graph import AgentWorkflow

        workflow = AgentWorkflow(
            llm=llm,
            tools=registry.to_langchain_tools(),
            memory_manager=memory,
        )
        app.state.workflow = workflow
        app.state.llm = llm
        app.state.memory = memory
        logger.info("AgentWorkflow 初始化完成")
    except Exception:
        # 启动初始化失败时打印完整 traceback，便于定位
        import traceback

        logger.error("AgentWorkflow 初始化失败:\n%s", traceback.format_exc())
        app.state.workflow = None
        raise

    logger.info("Enterprise Agent 启动, env=%s", settings.app_env)
    yield
    # 关闭连接池
    try:
        if getattr(app.state, "memory", None) is not None:
            await app.state.memory.close()
    except Exception:
        logger.exception("关闭记忆连接失败")
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
