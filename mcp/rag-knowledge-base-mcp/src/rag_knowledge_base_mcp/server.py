"""rag-knowledge-base MCP Server 主模块。

暴露能力：
- 工具：add_document（入库）/ search（Top-K 检索）/ retrieve_with_evidence（检索+引用证据）
- 资源：knowledge://doc/{doc_id}（文档全文）、knowledge://kpi/{kpi_code}（KPI 口径）
- 提示：policy_qa_prompt（基于检索片段的制度问答提示词）

运行：uv run rag-knowledge-base-mcp 或 uv run python -m rag_knowledge_base_mcp
调试：uvx mcp dev src/rag_knowledge_base_mcp/server.py
"""

from __future__ import annotations

import os
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from rag_knowledge_base_mcp.data import DOCUMENTS, KPIS
from rag_knowledge_base_mcp.retriever import BM25Retriever, DocumentStore

# LLM API Key 占位说明：本示例不接入任何真实 LLM 服务。
# 配置真实 Key 后请在 _generate_answer_with_llm 中接入你的 LLM 客户端。
_YOUR_LLM_API_KEY_PLACEHOLDER = "YOUR_LLM_API_KEY"

# FastMCP 实例（Server 名称：rag-knowledge-base）
mcp = FastMCP("rag-knowledge-base")

# 全局文档库与 BM25 检索器
STORE = DocumentStore()
RETRIEVER = BM25Retriever(STORE)


def _env_int(name: str, default: int) -> int:
    """读取环境变量为整数，失败时返回默认值。"""
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _make_doc_id(title: str) -> str:
    """由标题生成可读 doc_id（slug + 序号，保证唯一）。"""
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", title).strip("-").lower()
    slug = (slug[:40] or "doc").rstrip("-")
    seq = STORE.doc_count() + 1
    return f"doc-{slug}-{seq:03d}"


def _seed_data() -> None:
    """启动时载入内置示例数据（全部标注"示例"，无真实企业数据）。"""
    chunk_size = _env_int("CHUNK_SIZE", 200)
    chunk_overlap = _env_int("CHUNK_OVERLAP", 20)
    for doc in DOCUMENTS:
        STORE.add(
            doc_id=doc["doc_id"],
            title=doc["title"],
            source=doc["source"],
            content=doc["content"],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    RETRIEVER.rebuild()


def _generate_answer_with_llm(query: str, evidences: list[dict[str, Any]]) -> str | None:
    """LLM 生成答案接口（占位实现）。

    未配置 LLM_API_KEY（或为占位值 YOUR_LLM_API_KEY）时返回 None，
    retrieve_with_evidence 自动降级为纯 Top-K 检索结果，不发起任何外部请求。
    如需启用 LLM 生成：在下方接入你的 LLM 客户端（OpenAI / 通义 / 本地模型等），
    将 query 与 evidences 组装为提示词后调用并返回答案文本即可。
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key or api_key == _YOUR_LLM_API_KEY_PLACEHOLDER:
        return None
    # TODO(示例): 接入真实 LLM 客户端后，取消下行异常并返回生成答案
    raise NotImplementedError(
        "LLM 客户端未接入：请在 _generate_answer_with_llm 中实现调用逻辑"
    )


# ============================ 工具（Tools） ============================


@mcp.tool()
def add_document(title: str, content: str, source: str) -> dict[str, Any]:
    """文档入库：保存文档并增量更新 BM25 索引。

    参数：
        title: 文档标题（同时用于生成 doc_id）
        content: 文档正文（自动切分为检索片段）
        source: 来源（部门 / 文档编号等）
    返回：success + data(doc_id / chunk_count / total_documents) 或 error
    """
    if not title or not content:
        return {"success": False, "error": "title 与 content 不能为空"}
    if not source:
        source = "未指定"

    chunk_size = _env_int("CHUNK_SIZE", 200)
    chunk_overlap = _env_int("CHUNK_OVERLAP", 20)
    doc_id = _make_doc_id(title)
    STORE.add(
        doc_id=doc_id,
        title=title,
        source=source,
        content=content,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    # 新文档入库后重建索引（增量更新）
    RETRIEVER.rebuild()
    doc = STORE.get(doc_id)
    return {
        "success": True,
        "data": {
            "doc_id": doc_id,
            "chunk_count": doc["chunk_count"],
            "total_documents": STORE.doc_count(),
        },
    }


@mcp.tool()
def search(query: str, top_k: int = 5) -> dict[str, Any]:
    """Top-K 检索：按 BM25 分数返回命中的文档片段。

    参数：
        query: 检索问题 / 关键词
        top_k: 返回片段数（1-20，默认 5）
    返回：success + data(query / hits / total_hits) 或 error
    """
    if not query or not query.strip():
        return {"success": False, "error": "query 不能为空"}
    k = max(1, min(int(top_k), 20))
    hits = RETRIEVER.search(query, top_k=k)
    return {
        "success": True,
        "data": {"query": query, "hits": hits, "total_hits": len(hits)},
    }


@mcp.tool()
def retrieve_with_evidence(query: str, top_k: int = 5) -> dict[str, Any]:
    """检索并附引用证据：doc_id / 来源 / 片段 / 置信分。

    未配置 LLM_API_KEY（占位 YOUR_LLM_API_KEY）时自动降级为纯 Top-K 检索结果，
    generated_answer 为 None 并在 note 中说明；不会发起任何外部请求。

    参数：
        query: 检索问题 / 关键词
        top_k: 返回片段数（1-20，默认 5）
    返回：success + data(query / evidences / generated_answer / note) 或 error
    """
    if not query or not query.strip():
        return {"success": False, "error": "query 不能为空"}
    k = max(1, min(int(top_k), 20))
    hits = RETRIEVER.search(query, top_k=k)

    # 构造引用证据（含置信分：对本次查询的 BM25 分数做 min-max 归一化到 0~1）
    evidences: list[dict[str, Any]] = []
    if hits:
        scores = [h["score"] for h in hits]
        max_score, min_score = max(scores), min(scores)
        denom = max_score - min_score
        for hit in hits:
            confidence = 1.0 if denom == 0 else (hit["score"] - min_score) / denom
            evidences.append(
                {
                    "doc_id": hit["doc_id"],
                    "source": hit["source"],
                    "title": hit["title"],
                    "excerpt": hit["text"],
                    "confidence": round(float(confidence), 4),
                }
            )

    # LLM 生成答案：未配置 Key 时返回 None（降级为纯 Top-K 检索结果）
    generated_answer = _generate_answer_with_llm(query, evidences)
    note = None
    if generated_answer is None:
        note = (
            f"未配置 LLM API Key（占位：{_YOUR_LLM_API_KEY_PLACEHOLDER}），"
            "已降级为纯 Top-K 检索结果"
        )

    return {
        "success": True,
        "data": {
            "query": query,
            "evidences": evidences,
            "generated_answer": generated_answer,
            "note": note,
        },
    }


# ============================ 资源（Resources） ============================


@mcp.resource("knowledge://doc/{doc_id}")
async def doc_resource(doc_id: str) -> str:
    """返回指定文档全文（标题 / 来源 / 正文 / 片段数）。"""
    doc = STORE.get(doc_id)
    if doc is None:
        return f"未找到文档：{doc_id}"
    return (
        f"文档 ID：{doc['doc_id']}\n"
        f"标题：{doc['title']}\n"
        f"来源：{doc['source']}\n"
        f"片段数：{doc['chunk_count']}\n\n"
        f"全文：\n{doc['content']}"
    )


@mcp.resource("knowledge://kpi/{kpi_code}")
async def kpi_resource(kpi_code: str) -> str:
    """返回指定 KPI 口径定义（名称 / 定义 / 公式 / 频率 / 数据来源）。"""
    kpi = next((k for k in KPIS if k["kpi_code"] == kpi_code), None)
    if kpi is None:
        return f"未找到 KPI 口径：{kpi_code}"
    return (
        f"KPI 编码：{kpi['kpi_code']}\n"
        f"名称：{kpi['name']}\n"
        f"口径定义：{kpi['definition']}\n"
        f"计算公式：{kpi['formula']}\n"
        f"统计频率：{kpi['frequency']}\n"
        f"数据来源：{kpi['data_source']}\n"
        f"说明：{kpi['note']}"
    )


# ============================ 提示模板（Prompts） ============================


@mcp.prompt()
def policy_qa_prompt(query: str, top_k: int = 5) -> str:
    """基于检索片段生成制度问答提示词（要求依据片段回答并标注来源）。"""
    hits = RETRIEVER.search(query, top_k=max(1, min(int(top_k), 20)))
    if not hits:
        return (
            f"用户问题：{query}\n\n"
            "知识库中未检索到相关制度片段，请基于通用知识回答，"
            "并明确说明'未在示例知识库中找到直接依据'。"
        )
    context_lines = []
    for idx, hit in enumerate(hits, start=1):
        context_lines.append(
            f"[片段{idx}] 文档：{hit['title']}（doc_id: {hit['doc_id']}，"
            f"来源：{hit['source']}）\n{hit['text']}"
        )
    context = "\n\n".join(context_lines)
    return (
        "你是一名企业制度问答助手。请严格基于以下从企业知识库检索到的制度片段回答问题。\n"
        "要求：\n"
        "1. 优先依据片段内容回答，不得编造片段中不存在的条款；\n"
        "2. 回答中标注所依据的文档标题与来源；\n"
        "3. 若片段不足以回答，请明确说明并给出建议查询方向。\n\n"
        f"【检索片段】\n{context}\n\n"
        f"【用户问题】\n{query}"
    )


# ============================ 入口 ============================


def main() -> None:
    """命令行入口：以 stdio 模式启动 MCP Server。"""
    mcp.run()


# 模块导入时自动载入内置示例数据并建立索引
_seed_data()
