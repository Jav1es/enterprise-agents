# MCP 服务集合（mcp/）

> 本目录为 `enterprise-agents` 仓库下的 **MCP Server 子项目集合**，包含三个相互独立的 MCP Server：
> `enterprise-agent-tools-mcp`（企业工具）、`portfolio-mcp`（作品集）、`rag-knowledge-base-mcp`（RAG 知识库）。
> 三者均基于 **mcp 1.x 的 FastMCP API**（`mcp>=1.2.0,<2`），可用 Claude Desktop / Cursor 统一接入。
>
> **本文档中所有 Server 名称、工具、资源、命令、配置均为示例，禁止在真实环境直接套用真实企业名 / 密钥 / 客户数据。**

---

## 一、三个 MCP Server 用途对比

| Server 名 | 定位 | 工具（Tools） | 资源（Resources） | 提示（Prompts） | 默认依赖 |
| --- | --- | --- | --- | --- | --- |
| `enterprise-agent-tools-mcp` | 企业场景工具调用：ERP 库存/订单查询、补货建议、知识检索、通用 HTTP 请求（示例） | `query_inventory`、`get_order_status`、`generate_replenishment`、`search_knowledge`、`http_get`、`http_post` | `enterprise://inventory/{product_code}`、`enterprise://orders/{order_id}` | `replenishment_prompt` | `mcp>=1.2.0,<2`、`pydantic>=2.8.0`、`pydantic-settings>=2.4.0` |
| `portfolio-mcp` | 个人作品集模块查询与检索：列出模块、关键词搜索、项目详情（示例） | `list_modules`、`search_portfolio`、`get_item_detail` | `portfolio://modules`、`portfolio://module/{id}` | `interview_pitch_prompt` | `mcp>=1.2.0,<2`、`pydantic>=2.8.0` |
| `rag-knowledge-base-mcp` | RAG 企业知识库问答：文档入库、BM25 检索、带引用证据的问答（示例） | `add_document`、`search`、`retrieve_with_evidence` | `knowledge://doc/{doc_id}`、`knowledge://kpi/{kpi_code}` | `policy_qa_prompt` | `mcp>=1.2.0,<2`、`rank-bm25>=0.2.2`、`langchain-text-splitters>=0.2.0`、`pydantic>=2.8.0` |

> 可选依赖：`rag-knowledge-base-mcp` 提供 `vector` 扩展（`chromadb` / `sentence-transformers`）；三项目均提供 `dev` 扩展（`pytest` / `pytest-asyncio`）。

---

## 二、目录结构树

```
mcp/
├── README.md                              # 本文件：三 Server 汇总说明（示例）
├── enterprise-agent-tools-mcp/            # Server 1：企业工具（示例）
│   ├── pyproject.toml                     # 项目元数据 + 依赖 + 入口（enterprise-agent-tools-mcp）
│   ├── README.md                          # 子项目独立说明（示例）
│   ├── .env.example                       # 环境变量模板（示例，不入库）
│   ├── uv.lock                            # 依赖锁文件
│   ├── src/
│   │   └── enterprise_agent_tools_mcp/
│   │       └── server.py                  # FastMCP 服务入口（示例）
│   └── tests/                             # pytest 测试（示例）
├── portfolio-mcp/                         # Server 2：作品集（示例）
│   ├── pyproject.toml                     # 项目元数据 + 依赖 + 入口（portfolio-mcp）
│   ├── README.md                          # 子项目独立说明（示例）
│   ├── .env.example                       # 环境变量模板（示例，不入库）
│   ├── uv.lock                            # 依赖锁文件
│   ├── src/
│   │   └── portfolio_mcp/
│   │       └── server.py                  # FastMCP 服务入口（示例）
│   └── tests/                             # pytest 测试（示例）
└── rag-knowledge-base-mcp/                # Server 3：RAG 知识库（示例）
    ├── pyproject.toml                     # 项目元数据 + 依赖 + 入口（rag-knowledge-base-mcp）
    ├── README.md                          # 子项目独立说明（示例）
    ├── .env.example                       # 环境变量模板（示例，不入库）
    ├── uv.lock                            # 依赖锁文件
    ├── src/
    │   └── rag_knowledge_base_mcp/
    │       └── server.py                  # FastMCP 服务入口（示例）
    ├── data/                              # 示例知识数据（示例）
    └── tests/                             # pytest 测试（示例）
```

---

## 三、快速启动命令

以下命令均在各子项目目录内执行（示例，路径按本仓库实际位置为准）。

### 1. 安装依赖（含开发依赖）

```bash
cd mcp/enterprise-agent-tools-mcp   # 或 portfolio-mcp / rag-knowledge-base-mcp
uv sync --extra dev
```

### 2. 启动 Server（stdio 模式，本地运行）

```bash
# Server 1：企业工具
uv run enterprise-agent-tools-mcp

# Server 2：作品集
uv run portfolio-mcp

# Server 3：RAG 知识库
uv run rag-knowledge-base-mcp
```

### 3. 调试模式（MCP Inspector）

```bash
# Server 1：企业工具
uvx mcp dev src/enterprise_agent_tools_mcp/server.py

# Server 2：作品集
uvx mcp dev src/portfolio_mcp/server.py

# Server 3：RAG 知识库
uvx mcp dev src/rag_knowledge_base_mcp/server.py
```

---

## 四、Claude Desktop / Cursor 统一配置 JSON 示例

> 以下配置为**示例**：`command` 统一使用 `uv` + `run <入口名>` 指向本地已安装项目；若本地未执行 `uv sync`，请先按第三节完成安装。**请勿直接照抄到真实生产环境。**

### 4.1 Claude Desktop

配置文件：`claude_desktop_config.json`（Claude Desktop 的 MCP 配置，路径因操作系统而异，示例）：

```json
{
  "mcpServers": {
    "enterprise-agent-tools": {
      "command": "uv",
      "args": ["run", "enterprise-agent-tools-mcp"],
      "cwd": "D:/path/to/enterprise-agents/mcp/enterprise-agent-tools-mcp"
    },
    "portfolio": {
      "command": "uv",
      "args": ["run", "portfolio-mcp"],
      "cwd": "D:/path/to/enterprise-agents/mcp/portfolio-mcp"
    },
    "rag-knowledge-base": {
      "command": "uv",
      "args": ["run", "rag-knowledge-base-mcp"],
      "cwd": "D:/path/to/enterprise-agents/mcp/rag-knowledge-base-mcp"
    }
  }
}
```

> 说明（示例）：`command` 也可替换为 `uvx` 并去掉 `run`（如 `["uvx", "enterprise-agent-tools-mcp"]`），前提是入口已发布至 PyPI 或本地可被 `uvx` 解析；本仓库以 `uv run` 本地方式为准。

### 4.2 Cursor

配置文件：项目内 `.cursor/mcp.json`（示例）：

```json
{
  "mcpServers": {
    "enterprise-agent-tools": {
      "command": "uv",
      "args": ["run", "enterprise-agent-tools-mcp"],
      "cwd": "D:/path/to/enterprise-agents/mcp/enterprise-agent-tools-mcp"
    },
    "portfolio": {
      "command": "uv",
      "args": ["run", "portfolio-mcp"],
      "cwd": "D:/path/to/enterprise-agents/mcp/portfolio-mcp"
    },
    "rag-knowledge-base": {
      "command": "uv",
      "args": ["run", "rag-knowledge-base-mcp"],
      "cwd": "D:/path/to/enterprise-agents/mcp/rag-knowledge-base-mcp"
    }
  }
}
```

> 说明（示例）：Cursor 亦支持用户级全局配置（`~/.cursor/mcp.json`），格式相同；`cwd` 可省略（需确保 `uv` 在 PATH 中且项目已安装）。

---

## 五、安全说明

- **无真实密钥**：三个 Server 均使用**示例数据**与**示例配置**，不含任何真实企业名、API Key、Token、数据库密码或客户数据。
- **示例数据标注**：所有工具返回、资源内容、知识库文档均为演示用途，已明确标注“示例”，禁止直接用于生产。
- **敏感文件不入库**：`.env`、`config.yaml`、`*.key`、`*.pem` 等含敏感信息的文件已加入各子项目 `.gitignore`，仅提供 `.env.example` 模板，严禁提交真实凭据。
- **依赖锁定**：使用 `uv.lock` 锁定依赖版本，降低供应链风险。
- **生产使用前**：请替换为经过授权的真实数据、密钥与安全评审后的配置，并遵守所在组织的数据安全规范。
