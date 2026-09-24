"""文档加载与智能切分。

优先按语义边界（段落 → 换行 → 句子）分割，保留上下文连贯性。
"""

from __future__ import annotations

from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_documents(
    documents: list[Any],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[Any]:
    """按语义边界切分文档。

    Args:
        documents: LangChain Document 列表
        chunk_size: 切片大小（默认 500）
        chunk_overlap: 切片重叠（默认 50）

    Returns:
        切分后的 Document 列表
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", " ", ""],
    )
    return splitter.split_documents(documents)
