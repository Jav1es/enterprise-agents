"""作品集数据加载器。

加载策略（两级降级，保证"开箱即跑"）：
1. 优先读取 src/portfolio_mcp/data/portfolio_data.json（与 server.py 同仓库部署时数据源唯一）；
2. 文件缺失或 JSON 解析失败时，降级到本文件内置的示例数据（BUILTIN_PORTFOLIO_DATA）。

所有内置数据均标注"示例"，不含任何真实企业名 / 真实密钥 / 真实客户数据。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 数据文件绝对路径：data/portfolio_data.json（与 loader.py 同目录）
DATA_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_data.json")

# 可选：通过环境变量 PORTFOLIO_DATA_PATH 覆盖数据文件路径
_ENV_DATA_PATH = os.getenv("PORTFOLIO_DATA_PATH")

# ---------------------------------------------------------------------------
# 内置示例数据（兜底：portfolio_data.json 缺失或解析失败时使用）
# ---------------------------------------------------------------------------
BUILTIN_PORTFOLIO_DATA: list[dict[str, Any]] = [
    {
        "id": "mcp-enterprise-agent-tools",
        "title": "企业级智能体工具 MCP Server（示例）",
        "status": "已上线（示例）",
        "jd": "面向企业场景的 MCP Server，提供 ERP 库存/订单查询、补货建议、知识检索与通用 HTTP 工具（示例）",
        "pitch": "把企业常用能力封装成 6 个 MCP 工具，LLM 开箱即用（示例）",
        "pain": "企业数据散落在 ERP / 知识库 / 各业务系统，LLM 无法直接调用（示例）",
        "role": "独立完成架构设计与实现（示例）",
        "arch": "FastMCP + BaseTool 抽象 + mock 降级（示例）",
        "tools": ["FastMCP", "httpx", "pydantic", "pytest"],
        "metrics": ["6 个工具注册", "10 项测试全过", "无 Key 可运行（示例）"],
        "note": "示例数据",
    },
    {
        "id": "mcp-portfolio",
        "title": "作品集查询 MCP Server（示例）",
        "status": "已上线（示例）",
        "jd": "将个人作品集模块数据暴露为 MCP 工具/资源/提示模板，支持查询、检索与面试口播生成（示例）",
        "pitch": "作品集变 MCP 数据源，面试场景一键调取（示例）",
        "pain": "作品集内容散落在网页/文档，面试前难以快速组织口播与应答（示例）",
        "role": "独立完成设计、数据建模与实现（示例）",
        "arch": "FastMCP + JSON 数据驱动 + 关键词检索（示例）",
        "tools": ["FastMCP", "pydantic", "pytest", "JSON"],
        "metrics": ["3 个工具", "2 个资源", "1 个提示模板（示例）"],
        "note": "示例数据",
    },
    {
        "id": "mcp-rag-knowledge-base",
        "title": "RAG 知识库 MCP Server（示例）",
        "status": "开发中（示例）",
        "jd": "基于 RAG 的企业知识库问答 MCP Server，支持文档入库、向量检索与检索增强生成（示例）",
        "pitch": "把企业文档变成 LLM 可检索的知识底座（示例）",
        "pain": "企业文档多且杂，直接喂给 LLM 成本高、时效差（示例）",
        "role": "独立完成 RAG 流水线与 MCP 封装（示例）",
        "arch": "FastMCP + 文档解析 + 向量检索 + RAGPipeline（示例）",
        "tools": ["FastMCP", "向量库", "HybridRetriever", "pytest"],
        "metrics": ["文档入库", "混合检索", "引用溯源（示例）"],
        "note": "示例数据",
    },
    {
        "id": "tailored-resume-generator",
        "title": "智能简历生成器（示例）",
        "status": "已上线（示例）",
        "jd": "根据岗位 JD 自动改写简历项目经历，突出关键词匹配与量化结果（示例）",
        "pitch": "一份简历打天下 → 一岗一简历（示例）",
        "pain": "海投简历与 JD 匹配度低，人工改写费时费力（示例）",
        "role": "独立完成提示词工程与工具链集成（示例）",
        "arch": "LLM 提示词工程 + 简历模板 + 关键词分析（示例）",
        "tools": ["LLM API", "提示词工程", "Markdown", "PDF 导出"],
        "metrics": ["匹配度提升", "批量生成", "多模板支持（示例）"],
        "note": "示例数据",
    },
]


def load_portfolio_data() -> list[dict[str, Any]]:
    """加载作品集模块数据（两级降级）。

    Returns:
        模块对象列表；任何异常都不会抛出，最终至少返回内置示例数据。
    """
    candidates: list[str] = []
    if _ENV_DATA_PATH:
        candidates.append(_ENV_DATA_PATH)
    candidates.append(DATA_FILE_PATH)

    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, list):
                logger.warning("数据文件 %s 顶层不是数组，跳过并降级", path)
                continue
            # 简单校验：数组中元素应为 dict 且含 id 字段
            items = [x for x in raw if isinstance(x, dict) and x.get("id")]
            if not items:
                logger.warning("数据文件 %s 无有效模块对象，跳过并降级", path)
                continue
            logger.info("已从 %s 加载 %d 个模块", path, len(items))
            return items
        except FileNotFoundError:
            logger.warning("数据文件不存在：%s，降级", path)
        except json.JSONDecodeError as exc:
            logger.warning("数据文件解析失败：%s（%s），降级", path, exc)
        except OSError as exc:
            logger.warning("数据文件读取失败：%s（%s），降级", path, exc)

    logger.info("使用内置示例数据（%d 个模块）", len(BUILTIN_PORTFOLIO_DATA))
    return BUILTIN_PORTFOLIO_DATA
