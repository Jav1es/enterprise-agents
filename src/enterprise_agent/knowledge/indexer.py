"""文档加载、智能切分与知识库索引 CLI。

用法（在项目根目录执行）:
    uv run python -m enterprise_agent.knowledge.indexer [--docs docs] [--persist ./data/chroma] [--collection enterprise_kb]
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 自定义切分分隔符（按优先级）
_SPLIT_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", ". ", " ", ""]


def _load_markdown_docs(docs_dir: Path) -> list[dict[str, Any]]:
    """用标准库扫描 docs 目录下的 .md 文件，返回 [{text, source}] 列表。"""
    docs: list[dict[str, Any]] = []
    for p in sorted(docs_dir.rglob("*.md")):
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                docs.append({"text": text, "source": str(p)})
    return docs


def _split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """按分隔符优先级递归切分长文本（近似 RecursiveCharacterTextSplitter）。"""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    for sep in _SPLIT_SEPARATORS:
        if sep == "":
            break
        if sep in text:
            parts = text.split(sep)
            if len(parts) > 1:
                chunks: list[str] = []
                buf = ""
                for part in parts:
                    piece = part if sep == "\n" else part + sep
                    if len(buf) + len(piece) <= chunk_size:
                        buf += piece
                    else:
                        if buf:
                            chunks.append(buf.strip())
                        buf = piece
                if buf:
                    chunks.append(buf.strip())
                if len(chunks) > 1:
                    merged: list[str] = []
                    for c in chunks:
                        if len(c) <= chunk_size:
                            merged.append(c)
                        else:
                            merged.extend(
                                _split_text(c, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                            )
                    return merged
            break
    step = chunk_size - chunk_overlap
    return [text[i : i + chunk_size] for i in range(0, len(text), step) if text[i : i + chunk_size].strip()]


def split_documents(
    documents: list[dict[str, Any]],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[dict[str, Any]]:
    """按语义边界切分文档（标准库实现，兼容旧调用方）。

    Args:
        documents: [{"text": ..., "source": ...}, ...] 列表
        chunk_size: 切片大小（默认 500）
        chunk_overlap: 切片重叠（默认 50）

    Returns:
        切分后的 [{"text", "source"}] 列表
    """
    chunks: list[dict[str, Any]] = []
    for doc in documents:
        for piece in _split_text(doc["text"], chunk_size, chunk_overlap):
            chunks.append({"text": piece, "source": doc["source"]})
    return chunks


def resolve_embedding_model(model: str) -> str:
    """优先使用本地缓存的模型目录，避免运行时联网下载。"""
    local_dir = os.path.join(os.path.expanduser("~"), ".marvis-models", os.path.basename(model.rstrip("/")))
    if os.path.isdir(local_dir):
        logger.info("使用本地模型目录: %s", local_dir)
        return local_dir
    logger.info("使用在线模型: %s", model)
    return model


def build_knowledge_index(
    docs_dir: str,
    persist_dir: str,
    collection_name: str = "enterprise_kb",
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> dict[str, Any]:
    """扫描 docs 目录 -> 切分 -> 写入 ChromaDB 持久化集合。

    Returns:
        {"docs": int, "chunks": int, "collection": str, "persist_dir": str,
         "embedding_model": str, "count": int}
    """
    from enterprise_agent.config.settings import get_settings

    settings = get_settings()
    model = resolve_embedding_model(settings.embedding_model)

    docs_dir = Path(docs_dir)
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"docs 目录不存在: {docs_dir}")

    docs = _load_markdown_docs(docs_dir)
    if not docs:
        raise RuntimeError(f"docs 目录下未发现 .md 文档: {docs_dir}")
    for d in docs:
        d["text"] = d["text"].strip()

    chunks = split_documents(docs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(persist_dir))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model)
    collection = client.get_or_create_collection(
        name=collection_name, embedding_function=ef, metadata={"hnsw:space": "cosine"}
    )

    ids = [str(i) for i in range(len(chunks))]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {
            "source": str(c["source"]),
            "chunk_id": i,
            "title": Path(str(c["source"])).stem,
        }
        for i, c in enumerate(chunks)
    ]
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    result = {
        "docs": len(docs),
        "chunks": len(chunks),
        "collection": collection_name,
        "persist_dir": str(persist_dir),
        "embedding_model": model,
        "count": collection.count(),
    }
    logger.info("知识库索引完成: %s", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="重建企业知识库索引")
    parser.add_argument("--docs", default=None, help="docs 目录路径（默认项目根/docs）")
    parser.add_argument("--persist", default=None, help="Chroma 持久化目录")
    parser.add_argument("--collection", default="enterprise_kb")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--chunk-overlap", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    project_root = Path(__file__).resolve().parents[3]
    docs_dir = args.docs or str(project_root / "docs")
    from enterprise_agent.config.settings import get_settings

    persist_dir = args.persist or get_settings().chroma_persist_dir
    if not Path(persist_dir).is_absolute():
        persist_dir = str(project_root / persist_dir)

    result = build_knowledge_index(
        docs_dir=docs_dir,
        persist_dir=persist_dir,
        collection_name=args.collection,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    print("INDEX_RESULT " + str(result))


if __name__ == "__main__":
    main()
