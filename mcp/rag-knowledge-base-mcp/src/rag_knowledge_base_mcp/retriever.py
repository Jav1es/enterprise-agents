"""BM25 检索引擎（基于 rank-bm25）。

设计要点：
- DocumentStore：内存文档库，保存文档元信息与切分后的片段（chunks）；
- BM25Retriever：对全部片段建立 BM25Okapi 倒排索引，检索时按分数返回 Top-K；
- 支持增量更新：新文档通过 add_document 入库后调用 rebuild() 重建索引
  （示例规模下重建成本可忽略；数据量大时可升级为按 doc 维护增量索引）。
- 中英文分词：英文按整词、中文按字符 bigram 切分（零额外依赖）。
"""

from __future__ import annotations

import re
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

# 默认文本切分参数（可通过环境变量 CHUNK_SIZE / CHUNK_OVERLAP 覆盖）
_DEFAULT_CHUNK_SIZE = 200
_DEFAULT_CHUNK_OVERLAP = 20


# CJK 统一表意文字范围（用于识别连续中文字段）
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+|[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """中英文混合分词（零额外依赖方案）。

    - 小写化 + 常见标点替换为空格；
    - 英文 / 数字按整词保留（如 oa、5000）；
    - 连续中文按字符 bigram 切分（如"报销流程"→ 报销/销流/流程），
      使 query 中的子词（如"报销"）也能精确命中 BM25 倒排索引；
    - 单字 / 双字中文直接保留原词。
    """
    text = (text or "").lower()
    # 常见中文/英文标点统一替换为空格
    text = re.sub(
        r"[\s，。；：、！？（）()【】\[\]“”\"\"‘’《》<>,.!?;:·\-—_/\\|]+",
        " ",
        text,
    )
    tokens: list[str] = []
    for raw in text.split():
        # 分离连续中文段与非中文段（混合片段如 "oa系统" 会拆开处理）
        for piece in _CJK_RE.findall(raw):
            if re.fullmatch(r"[\u4e00-\u9fff]+", piece):
                if len(piece) <= 2:
                    tokens.append(piece)
                else:
                    # 中文 bigram 切分
                    for idx in range(len(piece) - 1):
                        tokens.append(piece[idx : idx + 2])
            else:
                tokens.append(piece)
    return tokens


def _chunk_text(content: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """按字符数切分文本为重叠片段。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    return [seg.strip() for seg in splitter.split_text(content) if seg.strip()]


class DocumentStore:
    """内存文档库：保存文档元信息与切分后的检索片段。"""

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, Any]] = {}
        self._chunks: list[dict[str, Any]] = []

    def add(
        self,
        doc_id: str,
        title: str,
        source: str,
        content: str,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
    ) -> dict[str, Any]:
        """入库一篇文档：切分片段并保存元信息。若 doc_id 已存在则覆盖。"""
        segments = _chunk_text(content, chunk_size, chunk_overlap)
        if not segments:
            segments = [content.strip()]

        # 构造片段记录（含 doc 元信息冗余，便于检索后直接返回）
        chunks = []
        for idx, text in enumerate(segments, start=1):
            chunks.append(
                {
                    "chunk_id": f"{doc_id}#{idx}",
                    "doc_id": doc_id,
                    "title": title,
                    "source": source,
                    "text": text,
                }
            )

        # 覆盖式更新：先移除旧文档的片段，再追加新片段
        self._chunks = [c for c in self._chunks if c["doc_id"] != doc_id]
        self._chunks.extend(chunks)
        self._documents[doc_id] = {
            "doc_id": doc_id,
            "title": title,
            "source": source,
            "content": content,
            "chunk_count": len(chunks),
        }
        return {"doc_id": doc_id, "chunk_count": len(chunks)}

    def get(self, doc_id: str) -> dict[str, Any] | None:
        """按 doc_id 取文档元信息（含全文）。"""
        return self._documents.get(doc_id)

    def all_chunks(self) -> list[dict[str, Any]]:
        """返回全部检索片段。"""
        return self._chunks

    def doc_count(self) -> int:
        return len(self._documents)

    def total_chunks(self) -> int:
        return len(self._chunks)


class BM25Retriever:
    """BM25 检索器：对片段库建立倒排索引并打分检索。"""

    def __init__(self, store: DocumentStore) -> None:
        self._store = store
        self._bm25: BM25Okapi | None = None
        self._corpus_texts: list[str] = []

    def rebuild(self) -> None:
        """根据当前片段库重建 BM25 索引（增量更新入口）。"""
        chunks = self._store.all_chunks()
        self._corpus_texts = [c["text"] for c in chunks]
        if not self._corpus_texts:
            # rank-bm25 不允许空语料（IDF 计算除零），置空索引
            self._bm25 = None
            return
        self._bm25 = BM25Okapi([tokenize(t) for t in self._corpus_texts])

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Top-K 检索：返回命中的片段列表（含分数，分数为 BM25 原始得分）。"""
        if self._bm25 is None or not query.strip():
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        chunks = self._store.all_chunks()

        # 按分数降序取 Top-K
        ranked = sorted(
            zip(chunks, scores, strict=False),
            key=lambda pair: pair[1],
            reverse=True,
        )
        hits = []
        for chunk, score in ranked[:top_k]:
            # 过滤完全无关的片段（BM25 分数为 0）
            if score <= 0:
                continue
            hit = dict(chunk)
            hit["score"] = round(float(score), 6)
            hits.append(hit)
        return hits
