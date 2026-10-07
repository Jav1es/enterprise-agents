"""FastAPI 应用入口。

启动: uv run uvicorn enterprise_agent.api.main:app --reload --port 8080
文档: http://localhost:8080/docs
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from langchain_core.language_models.chat_models import BaseChatModel

from enterprise_agent.config.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化依赖（LLM / 记忆 / RAG / 工具注册）。

    ⚠️ 降级契约：**LLM 不可用时服务仍应启动**（workflow=None，/health 正常，
    业务接口返回 503），否则「无 Key 离线演示」这条降级链路等于不存在。
    实测踩过：空字符串 Key 会让 ChatOpenAI 构造直接抛错，此前这里 `raise`
    导致整个进程启动失败 —— 多 worker 场景下父进程还会反复重启子进程刷日志。
    """
    settings = get_settings()
    # 显式标注为 BaseChatModel：两条分支的具体类型不同（StubLLM / ChatOpenAI），
    # 不加注解时 mypy 会先把变量推断成 StubLLM，再遇到 ChatOpenAI 赋值就报错。
    llm: BaseChatModel
    try:
        # --- LLM ---
        # EA_STUB_LLM=1 时用离线路径模型：没有 Key 也能让编排全量跑通，
        # 用于零成本压测与离线演练。不设置时走真实模型。
        if os.environ.get("EA_STUB_LLM") == "1":
            from enterprise_agent.llm.stub import StubLLM

            llm = StubLLM(temperature=0.3)
            logger.info("使用 StubLLM（EA_STUB_LLM=1，零网络零计费）")
        else:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                temperature=0.3,
                timeout=60,
            )
            logger.info("LLM 初始化完成: model=%s base_url=%s",
                        settings.llm_model, settings.llm_base_url)

        # --- 记忆层（Redis 短期记忆） ---
        from enterprise_agent.memory.short_term import ShortTermMemory

        memory = ShortTermMemory(settings.redis_url, settings.redis_short_term_ttl)
        logger.info("短期记忆初始化完成: redis=%s", settings.redis_url)

        # --- 工具注册中心 ---
        from enterprise_agent.tools.registry import ToolRegistry

        registry = ToolRegistry()

        # --- RAG 知识库检索器 ---
        retriever = None
        try:
            from pathlib import Path

            import chromadb
            from chromadb.utils import embedding_functions
            from rank_bm25 import BM25Okapi

            from enterprise_agent.knowledge.indexer import resolve_embedding_model
            from enterprise_agent.knowledge.retriever import HybridRetriever, tokenize_zh

            persist_dir = settings.chroma_persist_dir
            if not Path(persist_dir).is_absolute():
                persist_dir = str(Path.cwd() / persist_dir)
            chroma_client = chromadb.PersistentClient(path=persist_dir)
            model = resolve_embedding_model(settings.embedding_model)
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model)
            collection = chroma_client.get_or_create_collection(
                name="enterprise_kb", embedding_function=ef
            )
            count = collection.count()
            if count > 0:
                all_data = collection.get(include=["documents"])
                corpus = [d or "" for d in (all_data["documents"] or [])]
                bm25 = BM25Okapi([tokenize_zh(t) for t in corpus])
                retriever = HybridRetriever(
                    collection=collection,
                    bm25_index=bm25,
                    doc_ids=list(all_data["ids"]),
                    top_k=6,
                )
                logger.info(
                    "RAG 检索器初始化完成: collection=enterprise_kb chunks=%d model=%s",
                    count,
                    model,
                )
            else:
                logger.warning(
                    "知识库集合为空，请先运行: python -m enterprise_agent.knowledge.indexer"
                )
        except Exception:  # noqa: BLE001 - 检索器初始化失败不阻断服务
            logger.exception("RAG 检索器初始化失败，本次服务无知识检索能力")
            retriever = None

        # --- Agent 工作流 ---
        from enterprise_agent.orchestration.graph import AgentWorkflow

        workflow = AgentWorkflow(
            llm=llm,
            tools=registry.to_langchain_tools(),
            memory_manager=memory,
            retriever=retriever,
        )
        app.state.workflow = workflow
        app.state.llm = llm
        app.state.memory = memory
        logger.info("AgentWorkflow 初始化完成")
    except Exception:
        # 启动初始化失败时打印完整 traceback，便于定位。
        # 注意不 raise —— 降级链路要求服务能起来（/health 可用、业务接口 503），
        # 否则无 Key 的离线演示 / 架构压测全都做不了。
        import traceback

        logger.error("AgentWorkflow 初始化失败，进入降级模式（业务接口将返回 503）:\n%s",
                     traceback.format_exc())
        app.state.workflow = None

    logger.info("Enterprise Agent 启动, env=%s workflow=%s",
                settings.app_env, "ready" if app.state.workflow is not None else "degraded")
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
    """健康检查接口。

    附带 workflow 就绪状态与 LLM 调用预算状态 —— 压测前用它确认
    「服务是否处于离线降级模式」「预算闸是否已武装」。
    """
    from enterprise_agent.api.budget import budget_status

    llm_info: dict[str, Any] = {"mode": "unknown"}
    try:
        if os.environ.get("EA_STUB_LLM") == "1":
            from enterprise_agent.llm.stub import stub_stats

            llm_info = {"mode": "stub", **stub_stats()}
        else:
            llm_info = {"mode": "real"}
    except Exception:
        pass

    return {
        "status": "ok",
        "service": "enterprise-agent",
        "version": "1.0.0",
        "workflow": "ready" if getattr(app.state, "workflow", None) is not None else "degraded",
        "llm": llm_info,
        "llm_budget": budget_status(),
    }


# 路由注册
from enterprise_agent.api.routes import chat  # noqa: E402

app.include_router(chat.router, prefix="/v1", tags=["chat"])
