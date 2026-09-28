"""MCP Server 主体：FastMCP('portfolio')。

暴露内容：
- 工具（Tools）：list_modules / search_portfolio / get_item_detail
- 资源（Resources）：portfolio://modules、portfolio://module/{id}
- 提示模板（Prompts）：interview_pitch_prompt（生成 30 秒面试口播提示词）

数据加载策略（见 data/loader.py）：
- 优先读取 src/portfolio_mcp/data/portfolio_data.json；
- 文件缺失或解析失败时，降级到代码内内置示例数据（保证开箱即跑）。

运行方式：
- uv run portfolio-mcp
- uv run python -m portfolio_mcp
- uvx mcp dev src/portfolio_mcp/server.py（Inspector 调试）
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from portfolio_mcp.data.loader import load_portfolio_data
from portfolio_mcp.data.search import search_modules

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Server 实例
# ---------------------------------------------------------------------------
mcp = FastMCP("portfolio")

# 全局作品集数据（模块列表），启动时加载一次
PORTFOLIO_DATA: list[dict[str, Any]] = load_portfolio_data()


# ---------------------------------------------------------------------------
# 工具（Tools）
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_modules() -> dict[str, Any]:
    """列出作品集全部模块（概览卡片：id / title / status / 一句话定位）。

    Returns:
        模块概览列表
    """
    overviews = []
    for item in PORTFOLIO_DATA:
        overviews.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "pitch": item.get("pitch"),
            }
        )
    return {
        "success": True,
        "data": {"count": len(overviews), "modules": overviews},
        "error": None,
    }


@mcp.tool()
async def search_portfolio(keyword: str) -> dict[str, Any]:
    """按关键词搜索作品集模块（匹配标题、定位、痛点、角色、架构、工具等字段）。

    Args:
        keyword: 检索关键词，如 "MCP" / "简历" / "RAG"
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return {
            "success": False,
            "data": None,
            "error": "keyword 不能为空",
        }

    hits = search_modules(PORTFOLIO_DATA, keyword)
    return {
        "success": True,
        "data": {
            "keyword": keyword,
            "count": len(hits),
            "hits": hits,
            "note": "所有数据均为示例数据，仅用于演示",
        },
        "error": None,
    }


@mcp.tool()
async def get_item_detail(project_id: str) -> dict[str, Any]:
    """按 id 获取作品集模块完整详情。

    Args:
        project_id: 模块 id，如 "mcp-enterprise-agent-tools"
    """
    project_id = (project_id or "").strip()
    for item in PORTFOLIO_DATA:
        if item.get("id") == project_id:
            return {"success": True, "data": item, "error": None}
    return {
        "success": False,
        "data": None,
        "error": f"未找到模块 id={project_id}（示例数据包含：{', '.join(str(i.get('id')) for i in PORTFOLIO_DATA)}）",
    }


# ---------------------------------------------------------------------------
# 资源（Resources）
# ---------------------------------------------------------------------------


@mcp.resource("portfolio://modules")
async def modules_resource() -> str:
    """资源：全部模块概览（与 list_modules 同源数据）。"""
    overviews = []
    for item in PORTFOLIO_DATA:
        overviews.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "pitch": item.get("pitch"),
            }
        )
    return str({"count": len(overviews), "modules": overviews, "note": "示例数据"})


@mcp.resource("portfolio://module/{id}")
async def module_resource(id: str) -> str:
    """资源：单个模块详情（与 get_item_detail 同源数据）。"""
    for item in PORTFOLIO_DATA:
        if item.get("id") == id:
            return str(item)
    return f"未找到模块 id={id}（示例数据）"


# ---------------------------------------------------------------------------
# 提示模板（Prompts）
# ---------------------------------------------------------------------------


@mcp.prompt()
def interview_pitch_prompt(project_id: str) -> str:
    """提示模板：输入模块 id，生成 30 秒面试口播提示词。

    Args:
        project_id: 模块 id，如 "mcp-enterprise-agent-tools"
    """
    item = next((x for x in PORTFOLIO_DATA if x.get("id") == project_id), None)
    if item is None:
        return (
            f"你是一位求职面试教练（演示角色）。\n"
            f"用户请求针对模块 id={project_id} 生成 30 秒面试口播，但该模块在示例数据中不存在。\n"
            f"请礼貌告知用户：示例数据仅包含 {', '.join(str(i.get('id')) for i in PORTFOLIO_DATA)}。"
        )

    title = item.get("title", "")
    pitch = item.get("pitch", "")
    pain = item.get("pain", "")
    role = item.get("role", "")
    arch = item.get("arch", "")
    tools = item.get("tools", [])
    metrics = item.get("metrics", [])

    tool_text = "、".join(tools) if tools else "（未填写）"
    metric_text = "；".join(metrics) if metrics else "（未填写）"
    return (
        f"你是一位资深求职面试教练（演示角色）。\n"
        f"请基于以下作品集模块信息，为用户生成一段 **30 秒面试口播稿**（中文，约 120 字以内）：\n"
        f"\n"
        f"【模块】{title}\n"
        f"【一句话定位】{pitch}\n"
        f"【解决痛点】{pain}\n"
        f"【我的角色】{role}\n"
        f"【技术架构】{arch}\n"
        f"【核心工具】{tool_text}\n"
        f"【关键指标】{metric_text}\n"
        f"\n"
        f"口播要求：\n"
        f"1. 以第一人称讲述，突出「我做了什么、解决什么问题、取得什么结果」；\n"
        f"2. 控制在 30 秒内，语气自然、有说服力；\n"
        f"3. 结尾留一句可被追问的钩子（引导面试官深入提问）。\n"
        f"注意：以上数据均为示例数据，仅用于演示口播生成能力。"
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI 入口：以 stdio 模式启动 MCP Server。"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("portfolio MCP Server starting ... (%d modules loaded)", len(PORTFOLIO_DATA))
    mcp.run()


if __name__ == "__main__":
    main()
