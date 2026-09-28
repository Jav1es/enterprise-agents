# rag-knowledge-base-mcp

> MCP Server 子项目：基于 RAG 的企业知识库问答。
> 将企业制度 / 规范文档入库（BM25 检索），通过 MCP 工具 / 资源 / 提示模板暴露给
> Claude Desktop / Cursor / 任意 MCP 客户端，支持文档入库、Top-K 检索、引用证据返回与制度问答提示词生成。
> 所有数据均为 **示例数据**（标注"示例"），不包含任何真实企业名 / 真实密钥 / 真实客户数据。

## 项目定位

面向"企业知识库问答"场景的 RAG MCP Server：

- **add_document(title, content, source)**：文档入库，自动切分片段并增量更新 BM25 索引
- **search(query, top_k=5)**：Top-K 检索，返回命中文档片段（doc_id / 来源 / 片段 / 分数）
- **retrieve_with_evidence(query, top_k=5)**：检索并附引用证据（doc_id / 来源 / 片段 / 置信分）；未配置 LLM Key 时自动降级为纯 Top-K 检索结果
- **资源**：`knowledge://doc/{doc_id}`（文档全文）、`knowledge://kpi/{kpi_code}`（KPI 口径定义）
- **提示模板**：`policy_qa_prompt(query, top_k=5)`，基于检索片段生成制度问答提示词

检索引擎：**BM25（rank-bm25）**，零外部服务依赖、开箱即跑；
可选安装 `vector` extra（chromadb + sentence-transformers）后可在代码中扩展向量检索（默认不安装也能运行）。

## 工具 / 资源 / 提示模板清单

### 工具（Tools）

| 名称 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `add_document` | `title: str, content: str, source: str` | doc_id / 片段数 / 库内文档总数 | 文档入库并建立/增量更新 BM25 索引 |
| `search` | `query: str, top_k: int = 5` | 命中片段列表（doc_id / source / text / score） | Top-K 检索返回文档片段 |
| `retrieve_with_evidence` | `query: str, top_k: int = 5` | 引用证据列表 + 可选 LLM 生成答案 | 检索并附引用证据；无 LLM Key 降级为纯 Top-K 结果 |

### 资源（Resources）

| 资源 URI | 说明 |
|---|---|
| `knowledge://doc/{doc_id}` | 指定文档全文（标题 / 来源 / 正文 / 片段数） |
| `knowledge://kpi/{kpi_code}` | 指定 KPI 口径定义（名称 / 定义 / 公式 / 频率 / 数据来源） |

### 提示模板（Prompts）

| 名称 | 输入 | 说明 |
|---|---|---|
| `policy_qa_prompt` | `query: str, top_k: int = 5` | 基于检索片段生成制度问答提示词，要求 LLM 依据片段回答并标注来源 |

## 内置示例数据

- `data/documents.py`：3 条示例企业制度（考勤管理 / 报销管理 / 信息安全），全部标注"示例"；
- `data/kpis.py`：4 个示例 KPI 口径（考勤出勤率 / 报销处理时效 / 信息安全事件数 / 员工满意度），全部标注"示例"。

替换这两个文件即可完成个性化，无需改代码。

## 快速开始

要求：Python 3.11+，已安装 [uv](https://docs.astral.sh/uv/)。

```bash
# 1. 安装依赖（含 dev 分组：pytest / pytest-asyncio；默认不安装 vector 分组）
uv sync --extra dev

# 2. 运行测试
uv run pytest

# 3. 直接运行（stdio 模式，供 MCP 客户端连接）
uv run rag-knowledge-base-mcp

# 4. 等价入口
uv run python -m rag_knowledge_base_mcp

# 5. 用 MCP Inspector 可视化调试（推荐开发期使用）
uvx mcp dev src/rag_knowledge_base_mcp/server.py

# 6.（可选）安装向量检索增强依赖（chromadb + sentence-transformers，体积较大）
uv sync --extra vector
# 或
uv pip install 'chromadb>=0.5.0' 'sentence-transformers>=2.7.0'
```

> `mcp dev` 会启动本地 Inspector 页面，可直观查看工具列表、资源、提示模板并逐个调用测试。

## 配置示例

### Claude Desktop

编辑 `claude_desktop_config.json`（Windows：`%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "rag-knowledge-base": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Jav1e Flies/家辉专用/千问办公反馈结果/AI作品集网站（离线版）/04-企业级智能体系统(本地开发工程(enterprise-agent)/enterprise-agents/mcp/rag-knowledge-base-mcp",
        "run",
        "rag-knowledge-base-mcp"
      ]
    }
  }
}
```

### Cursor

编辑项目根目录 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "rag-knowledge-base": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Jav1e Flies/家辉专用/千问办公反馈结果/AI作品集网站（离线版）/04-企业级智能体系统(本地开发工程(enterprise-agent)/enterprise-agents/mcp/rag-knowledge-base-mcp",
        "run",
        "rag-knowledge-base-mcp"
      ]
    }
  }
}
```

> 路径中的中文与括号请原样保留；若换机/换目录部署，只需修改 `args[1]` 指向本项目的绝对路径。

## 演示截图 / GIF（占位说明）

> 占位：开发验证通过后，建议补充以下演示素材到 `assets/` 目录并在 README 中引用：
> 1. `assets/demo-inspector.png`：MCP Inspector 中工具列表 / 资源 / 提示模板的截图
> 2. `assets/demo-search.png`：调用 `search` / `retrieve_with_evidence` 返回片段与引用证据的截图
> 3. `assets/demo-claude.gif`：Claude Desktop 中通过 MCP 查询企业制度的演示 GIF

## 安全说明

- **无真实密钥**：`retrieve_with_evidence` 未配置 `LLM_API_KEY`（占位 `YOUR_LLM_API_KEY`）时自动降级为纯 Top-K 检索，不会发起任何外部请求；
- **示例数据标注**：内置制度与 KPI 均标注"示例"，仅用于展示工程能力；
- **数据自定义**：替换 `src/rag_knowledge_base_mcp/data/documents.py` 与 `data/kpis.py` 即可接入真实制度 / KPI 口径；
- **仅供学习演示**：正式用于企业内部场景时，请替换为经脱敏处理的真实数据并人工核对口径，且建议将知识库迁移到服务端部署。

## License

MIT。示例数据为演示用途（标注"示例"），与任何真实企业 / 客户无关。
