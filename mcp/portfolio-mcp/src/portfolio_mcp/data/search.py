"""作品集关键词检索实现。

对模块的多个文本字段（标题、JD、定位、痛点、角色、架构、工具、指标）做
包含匹配 + 打分排序：命中字段越多、得分越高。简单、可读、无外部依赖，
适合作为 MCP 工具演示；正式场景可替换为向量检索等更复杂方案。
"""

from __future__ import annotations

from typing import Any

# 参与检索的文本字段（按重要程度排序，用于打分）
_SEARCH_FIELDS: tuple[str, ...] = (
    "title",
    "jd",
    "pitch",
    "pain",
    "role",
    "arch",
    "tools",
    "metrics",
)


def search_modules(data: list[dict[str, Any]], keyword: str) -> list[dict[str, Any]]:
    """在模块列表中按关键词检索。

    Args:
        data: 模块对象列表
        keyword: 检索关键词（已去除首尾空白）

    Returns:
        命中模块列表（含 matched_fields 说明），按得分降序；无命中返回空列表。
    """
    keyword = keyword.strip().lower()
    if not keyword:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for item in data:
        score = 0.0
        matched_fields: list[str] = []
        for idx, field in enumerate(_SEARCH_FIELDS):
            raw_value = item.get(field)
            if raw_value is None:
                continue
            # 字段值可能是字符串或字符串列表，统一转小写文本
            if isinstance(raw_value, (list, tuple)):
                text = " ".join(str(v) for v in raw_value).lower()
            else:
                text = str(raw_value).lower()
            if keyword in text:
                # 权重：越靠前的字段权重越高（1.0 ~ 0.4 递减）
                score += max(0.4, 1.0 - idx * 0.1)
                matched_fields.append(field)
        if matched_fields:
            # 命中同一字段多次不重复加分，但保留字段列表
            scored.append((score, {**item, "matched_fields": matched_fields}))

    # 按得分降序，同分按原顺序
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]
