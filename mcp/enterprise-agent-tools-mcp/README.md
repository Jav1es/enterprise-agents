# enterprise-agent-tools-mcp

> 基于 [enterprise-agents](https://github.com/Jav1es/enterprise-agents) 的 tools 层抽象精简复用的 MCP Server 子项目。
> 面向企业场景的工具调用：ERP 库存/订单查询、补货建议、知识检索、通用 HTTP 请求。
> 所有数据均为 **mock 示例数据**，无真实 API Key 即可运行，适合演示与二次开发。

## 项目定位

为 Claude Desktop / Cursor / 任意 MCP 客户端提供一组"企业工具"：

- **ERP 域**：库存查询、订单状态查询、补货建议生成（mock 数据 + 接口占位）
- **知识域**：企业内部知识库关键词检索（mock 文档片段）
- **HTTP 域**：通用 `http_get` / `http_post`（对接真实 REST 服务时填入真实 URL 与凭证）

设计上精简复用了 `enterprise-agent` 的 `BaseTool / ToolInput / ToolOutput` 抽象（MIT 许可，保留归属注释），
每个工具输入输出均有 Pydantic Schema 约束，LLM 可准确理解工具用途。

## 工具 / 资源 / 提示模板清单

### 工具（Tools）

| 名称 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `query_inventory` | `product_code: str` | `ToolOutput`（库存信息） | 查询 ERP 库存（mock 示例数据，`ERP_API_URL` 未配置时走降级） |
| `get_order_status` | `order_id: str` | `ToolOutput`（订单状态） | 查询订单状态（mock 示例数据，`ERP_API_URL` 未配置时走降级） |
| `generate_replenishment` | `sku_list: list[str]` | `ToolOutput`（补货建议） | 根据 SKU 列表与 mock 库存生成补货建议 |
| `search_knowledge` | `query: str, top_k: int = 5` | `ToolOutput`（知识片段列表） | 企业内部知识库关键词检索（mock 文档片段） |
| `http_get` | `url: str` | `ToolOutput`（响应 JSON/文本） | 通用 HTTP GET，超时 30s，失败返回错误信息 |
| `http_post` | `url: str, json: dict` | `ToolOutput`（响应 JSON/文本） | 通用 HTTP POST，超时 30s，失败返回错误信息 |

### 资源（Resources）

| 资源 URI | 说明 |
|---|---|
| `enterprise://inventory/{product_code}` | 按产品编码读取库存（mock 数据，内容标注"示例"） |
| `enterprise://orders/{order_id}` | 按订单号读取订单状态（mock 数据，内容标注"示例"） |

### 提示模板（Prompts）

| 名称 | 输入 | 说明 |
|---|---|---|
| `replenishment_prompt` | `sku_list: list[str]` | 输入 SKU 列表，返回一段"补货建议"提示词，供 LLM 作为系统提示使用 |

## 快速开始

要求：Python 3.11+，已安装 [uv](https://docs.astral.sh/uv/)。

```bash
# 1. 安装依赖（含 dev 分组：pytest / pytest-asyncio）
uv sync --extra dev

# 2. 运行测试
uv run pytest

# 3. 直接运行（stdio 模式，供 MCP 客户端连接）
uv run enterprise-agent-tools-mcp

# 4. 等价入口
uv run python -m enterprise_agent_tools_mcp

# 5. 用 MCP Inspector 可视化调试（推荐开发期使用）
uvx mcp dev src/enterprise_agent_tools_mcp/server.py
```

> `mcp dev` 会启动本地 Inspector 页面，可直观查看工具列表、资源、提示模板并逐个调用测试。

## 配置示例

### Claude Desktop

编辑 `claude_desktop_config.json`（Windows：`%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "enterprise-agent-tools": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Jav1e Flies/家辉专用/千问办公反馈结果/AI作品集网站（离线版）/04-企业级智能体系统(本地开发工程(enterprise-agent)/enterprise-agents/mcp/enterprise-agent-tools-mcp",
        "run",
        "enterprise-agent-tools-mcp"
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
    "enterprise-agent-tools": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Jav1e Flies/家辉专用/千问办公反馈结果/AI作品集网站（离线版）/04-企业级智能体系统(本地开发工程(enterprise-agent)/enterprise-agents/mcp/enterprise-agent-tools-mcp",
        "run",
        "enterprise-agent-tools-mcp"
      ]
    }
  }
}
```

> 路径中的中文与括号请原样保留；若换机/换目录部署，只需修改 `args[1]` 指向本项目的绝对路径。

## 演示截图 / GIF 占位

> TODO：运行 `uvx mcp dev src/enterprise_agent_tools_mcp/server.py` 后，截图 Inspector 中
> 工具列表与 `query_inventory` 调用结果，另录制一段调用 `generate_replenishment` 的 GIF，
> 替换本段为图片并补充到 `assets/` 目录。

## 安全说明

- **无真实密钥**：`.env.example` 中所有密钥均为 `YOUR_*` 占位；代码中不含任何真实企业名、真实密钥或真实客户数据。
- **降级策略**：未配置 `ERP_API_URL` / `ERP_API_TOKEN` 时，ERP 域工具自动返回 **mock 示例数据**（数据均标注"示例"），保证无 Key 可运行、可演示。
- **凭证注入**：真实接入时通过环境变量注入凭证，严禁硬编码；`.env`、`config.yaml`、`*.key`、`*.pem` 已被 `.gitignore` 排除，不会入库。
- **HTTP 工具提醒**：`http_get` / `http_post` 面向已授权接口调用，调用方需自行确保 URL 与权限合法，且不要向未授权接口发送敏感数据。
- **仅供学习演示**：本项目的 mock 数据与接口占位仅用于展示工程能力，正式使用请替换为真实业务实现与鉴权。

## License

MIT。`tools/base.py` 派生自 [enterprise-agents](https://github.com/Jav1es/enterprise-agents)（MIT），保留原作者归属注释。
