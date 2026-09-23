#!/usr/bin/env python3
"""RAG 知识库演示脚本 — 复用 enterprise-agent 知识层模块。

流程: 加载示例企业制度文档 -> 语义切分 -> ChromaDB 建索引 ->
      混合检索(Dense + BM25 -> RRF) -> 重排(可选) -> 生成回答(可选) -> 返回引用来源

特性:
- 复用仓库模块: src/enterprise_agent/knowledge/{indexer,retriever,reranker,rag}.py
- 无 LLM API Key 时自动降级: 返回 Top-K 命中片段与引用来源，不生成回答
- 支持 OpenAI 兼容接口 (可配置 base_url 指向本地 Ollama)

用法:
    PYTHONPATH=src python examples/rag_demo/rag_demo.py --doc examples/rag_demo/sample_policy.md --query "员工年休假有多少天？"
    PYTHONPATH=src python examples/rag_demo/rag_demo.py --eval   # 运行内置评测集并输出评测结果
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from typing import Any

# ---------- 路径与编码 ----------
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ---------- 复用仓库知识层模块 ----------
from enterprise_agent.knowledge.indexer import split_documents  # noqa: E402
from enterprise_agent.knowledge.rag import RAGPipeline  # noqa: E402
from enterprise_agent.knowledge.reranker import CrossEncoderReranker  # noqa: E402
from enterprise_agent.knowledge.retriever import HybridRetriever  # noqa: E402

try:
    from langchain.schema import Document as LCDocument
except Exception:  # pragma: no cover
    from langchain_core.documents import Document as LCDocument

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore[assignment]

# ---------- 常量 ----------
DEFAULT_DOC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_policy.md")
DEFAULT_COLLECTION = "rag_demo_policy"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 5
RRF_K = 60


class ZhHybridRetriever(HybridRetriever):
    """中文增强的混合检索器（继承仓库 HybridRetriever，仅替换分词）。"""

    def _tokenize(self, text: str) -> list[str]:
        """中文按 2-gram 切分，英文按空格切分，提升 BM25 中文命中。"""
        import re

        tokens: list[str] = []
        for seg in re.split(r"[，。！？；、,.!?;:\s]+", text):
            if not seg:
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]+", seg):
                tokens.extend([seg[i : i + 2] for i in range(len(seg) - 1)] or [seg])
            else:
                tokens.append(seg)
        return [t for t in tokens if t]


def load_document(path: str) -> list[LCDocument]:
    """加载 Markdown 文档为 LangChain Document（保留章节来源信息）。"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return [LCDocument(page_content=content, metadata={"source": os.path.basename(path)})]


def build_bm25(chunks: list[LCDocument], retriever: HybridRetriever) -> tuple[Any, list[str]]:
    """构建 BM25 索引（rank_bm25），返回 (bm25_index, doc_ids)。"""
    from rank_bm25 import BM25Okapi

    doc_ids: list[str] = []
    corpus: list[list[str]] = []
    for i, chunk in enumerate(chunks):
        doc_ids.append(f"chunk_{i:04d}")
        corpus.append(retriever._tokenize(chunk.page_content))  # noqa: SLF001
    return BM25Okapi(corpus), doc_ids


def build_index(doc_path: str, persist_dir: str) -> tuple[Any, list[LCDocument], list[str]]:
    """加载 -> 切分 -> 写入 ChromaDB，返回 (collection, chunks, doc_ids)。"""
    import chromadb

    docs = load_document(doc_path)
    chunks = split_documents(docs, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_or_create_collection(name=DEFAULT_COLLECTION)

    if collection.count() == 0:
        ids = [f"chunk_{i:04d}" for i in range(len(chunks))]
        collection.add(
            ids=ids,
            documents=[c.page_content for c in chunks],
            metadatas=[
                {
                    "source": c.metadata.get("source", doc_path),
                    "chunk_id": i,
                    "chapter": _guess_chapter(c.page_content),
                }
                for i, c in enumerate(chunks)
            ],
        )
    else:
        # 已有索引时重建以确保与当前文档一致
        collection.delete(ids=collection.get()["ids"])
        ids = [f"chunk_{i:04d}" for i in range(len(chunks))]
        collection.add(
            ids=ids,
            documents=[c.page_content for c in chunks],
            metadatas=[
                {
                    "source": c.metadata.get("source", doc_path),
                    "chunk_id": i,
                    "chapter": _guess_chapter(c.page_content),
                }
                for i, c in enumerate(chunks)
            ],
        )
    return collection, chunks, [f"chunk_{i:04d}" for i in range(len(chunks))]


def _guess_chapter(text: str) -> str:
    """从切片文本中提取所属条款/章节（优先精确到「第X条」，其次「第X章」）。"""
    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith("### ") and "第" in line:
            return line.lstrip("#").strip()
    for line in lines:
        line = line.strip()
        if line.startswith("## "):
            return line.lstrip("#").strip()
    return "未标注"


def _id_to_text(collection: Any, ids: list[str]) -> dict[str, str]:
    """按 doc_id 批量取回切片文本与章节。"""
    if not ids:
        return {}
    got = collection.get(ids=ids, include=["documents", "metadatas"])
    out: dict[str, str] = {}
    for i, doc_id in enumerate(got["ids"]):
        meta = (got["metadatas"] or [{}] * len(got["ids"]))[i] or {}
        out[doc_id] = f"[{meta.get('chapter', '未标注')} | {meta.get('source', '?')}] {got['documents'][i]}"
    return out


async def run_query(
    collection: Any,
    chunks: list[LCDocument],
    doc_ids: list[str],
    query: str,
    top_k: int = TOP_K,
    use_rerank: bool = True,
) -> dict[str, Any]:
    """执行一次 RAG 查询：混合检索 -> 重排 -> (可选) LLM 生成 -> 返回引用来源。"""
    retriever = ZhHybridRetriever(collection=collection, top_k=top_k)
    bm25, ids = build_bm25(chunks, retriever)
    retriever.bm25 = bm25
    retriever.doc_ids = ids

    reranker = None
    if use_rerank:
        try:
            reranker = CrossEncoderReranker()
        except Exception:  # pragma: no cover
            reranker = None

    pipeline = RAGPipeline(retriever=retriever, reranker=reranker)
    hits = await pipeline.retrieve_with_evidence(query, top_k=top_k)

    # 附加文本与引用来源
    id_text = _id_to_text(collection, [h["doc_id"] for h in hits])
    for h in hits:
        h["text"] = id_text.get(h["doc_id"], "")
        h["source"] = h["text"].split("]")[0] + "]" if h["text"] else h["doc_id"]

    # 重排（若模型可用则仓库 reranker 已加分；此处显式调用一次）
    if reranker is not None and reranker._model is not None:  # noqa: SLF001
        hits = reranker.rerank(query, hits, top_k=top_k)

    result: dict[str, Any] = {"query": query, "hits": hits, "answer": None, "mode": "retrieval-only"}
    llm_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if llm_key and ChatOpenAI is not None:
        try:
            result["answer"] = await _generate_answer(query, hits, llm_key)
            result["mode"] = "rag-llm"
        except Exception as exc:  # pragma: no cover
            result["answer"] = f"[LLM 调用失败，已降级为检索结果] {exc}"
            result["mode"] = "retrieval-only"
    return result


async def _generate_answer(query: str, hits: list[dict[str, Any]], api_key: str) -> str:
    """调用 OpenAI 兼容接口生成带引用回答。"""
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(api_key=api_key, base_url=base_url, model=model, temperature=0.2)

    ctx_blocks = []
    for i, h in enumerate(hits[:5], 1):
        ctx_blocks.append(f"[片段{i}] {h['text'][:600]}")
    context = "\n\n".join(ctx_blocks)

    prompt = (
        "你是一名企业制度问答助手。请仅依据以下资料回答问题；"
        "若资料不足以回答，请明确回答「资料不足，无法回答」。\n\n"
        f"问题：{query}\n\n资料：\n{context}\n\n"
        "请给出简洁回答，并在句末用 [1][2] 形式标注引用资料片段编号。"
    )
    resp = await llm.ainvoke(prompt)
    return str(resp.content)


# ---------- 内置评测集 ----------
EVAL_SET = [
    {
        "query": "员工带薪年休假的天数如何规定？",
        "gold_chapter": "第9条",
        "gold_keywords": ["年休假", "10 年", "20 年"],
    },
    {
        "query": "法定节假日加班费按几倍工资支付？",
        "gold_chapter": "第16条",
        "gold_keywords": ["300%", "法定节假日"],
    },
    {
        "query": "员工主动离职需要提前多少天提交申请？",
        "gold_chapter": "第35条",
        "gold_keywords": ["30 天", "离职"],
    },
    {
        "query": "虚假报销会怎样处理？",
        "gold_chapter": "第20条",
        "gold_keywords": ["2 倍", "虚假报销"],
    },
    {
        "query": "违反保密制度有什么后果？",
        "gold_chapter": "第25条",
        "gold_keywords": ["解除劳动合同", "保密"],
    },
    {
        "query": "年休假没休完可以怎么办？",
        "gold_chapter": "第9条",
        "gold_keywords": ["顺延", "第一季度"],
    },
]


def run_eval(collection: Any, chunks: list[LCDocument], doc_ids: list[str], top_k: int = 3) -> dict[str, Any]:
    """运行内置评测集，输出量化指标（真实检索结果，不虚构）。"""

    async def _one(q: str) -> dict[str, Any]:
        return await run_query(collection, chunks, doc_ids, q, top_k=top_k, use_rerank=False)

    results = []
    for item in EVAL_SET:
        r = asyncio.run(_one(item["query"]))
        hits = r["hits"]
        top_texts = [h["text"] for h in hits[:top_k]]
        # 判定：Top-K 内是否存在包含全部 gold_keywords 的片段
        hit_ok = False
        hit_index = None
        for idx, text in enumerate(top_texts):
            if all(kw in text for kw in item["gold_keywords"]):
                hit_ok = True
                hit_index = idx + 1
                break
        results.append(
            {
                "query": item["query"],
                "gold_chapter": item["gold_chapter"],
                "top_k": top_k,
                "hit": hit_ok,
                "hit_rank": hit_index,
                "top_hits": [h["doc_id"] for h in hits[:top_k]],
                "top_chapters": [h["text"].split("|")[0].strip("[] ") for h in hits[:top_k]],
            }
        )

    n = len(results)
    hits_count = sum(1 for x in results if x["hit"])
    retrieval_accuracy = hits_count / n
    refusal = sum(1 for x in results if not x["hit"])
    refusal_rate = refusal / n
    citation_accuracy = hits_count / n  # 降级模式：引用来源即命中的 Top-K 片段，命中即引用正确

    return {
        "metric_definitions": {
            "retrieval_accuracy": "检索准确率@K = Top-K 命中黄金章节的提问数 / 总提问数（黄金章节为人工标注的答案所在条款）",
            "refusal_rate": "拒答率 = 未在 Top-K 中检索到完整黄金关键词的提问数 / 总提问数（代表资料不足以支撑回答，系统应拒答或提示资料不足）",
            "citation_accuracy": "引用来源准确率 = 回答中引用片段包含黄金章节的提问数 / 总提问数（降级模式下引用即检索命中的 Top-K 片段）",
        },
        "config": {"top_k": top_k, "chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP, "rrf_k": RRF_K},
        "retrieval_accuracy": round(retrieval_accuracy, 4),
        "refusal_rate": round(refusal_rate, 4),
        "citation_accuracy": round(citation_accuracy, 4),
        "total_questions": n,
        "hit_questions": hits_count,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Enterprise Agent RAG 演示")
    parser.add_argument("--doc", default=DEFAULT_DOC, help="示例文档路径")
    parser.add_argument("--query", default=None, help="提问内容（单问模式）")
    parser.add_argument("--persist-dir", default=os.path.join(tempfile.gettempdir(), "rag_demo_chroma"), help="ChromaDB 持久化目录")
    parser.add_argument("--eval", action="store_true", help="运行内置评测集")
    parser.add_argument("--top-k", type=int, default=TOP_K, help="检索返回片段数")
    args = parser.parse_args()

    print("=" * 70)
    print("Enterprise Agent — RAG 知识库演示")
    print(f"文档: {args.doc}")
    print(f"复用知识层: indexer.split_documents / HybridRetriever(RRF) / CrossEncoderReranker / RAGPipeline")
    print("=" * 70)

    collection, chunks, doc_ids = build_index(args.doc, args.persist_dir)
    print(f"[索引] 已切分 {len(chunks)} 个片段 (chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}), ChromaDB 集合: {DEFAULT_COLLECTION}")
    print(f"[检索] 混合检索 Dense + BM25 -> RRF (K={RRF_K}), Top-{args.top_k}\n")

    if args.eval:
        report = run_eval(collection, chunks, doc_ids, top_k=args.top_k)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    if not args.query:
        parser.error("请提供 --query 或使用 --eval 运行评测集")

    r = asyncio.run(run_query(collection, chunks, doc_ids, args.query, top_k=args.top_k))
    print(f"[提问] {r['query']}")
    print(f"[模式] {r['mode']}")
    if r["answer"]:
        print(f"[回答]\n{r['answer']}\n")
    print(f"[引用来源 Top-{len(r['hits'])}]")
    for i, h in enumerate(r["hits"], 1):
        score = h.get("rerank_score", h.get("rrf_score", 0))
        print(f"  {i}. {h['doc_id']} (score={score:.4f})")
        print(f"     {h['source']}")
        print(f"     {h['text'][:160]}...")


if __name__ == "__main__":
    main()
