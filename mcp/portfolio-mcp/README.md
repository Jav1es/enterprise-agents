# portfolio-mcp

> MCP Server 子项目：作品集模块查询与检索。
> 将"个人 AI 作品集"的模块数据（项目定位、痛点、架构、工具、指标等）暴露为 MCP 工具 / 资源 / 提示模板，
> 供 Claude Desktop / Cursor / 任意 MCP 客户端查询、检索，并生成面试口播提示词。
> 所有数据均为 **示例数据**（标注"示例"），不包含任何真实企业名 / 真实密钥 / 真实客户数据。

## 项目定位

面向"求职面试 + 作品集展示"场景的 MCP Server：

- **list_modules()**：列出作品集全部模块（概览卡片）
- **search_portfolio(keyword)**：按关键词在模块的标题 / 定位 / 痛点 / 角色 / 架构 / 工具等字段中检索
- **get_item_detail(project_id)**：按 id 获取单个模块完整详情
- **资源**：`portfolio://modules`（全部模块概览）、`portfolio://module/{id}`（单个模块详情）
- **提示模板**：`interview_pitch_prompt(project_id)`，一键生成 30 秒面试口播提示词

数据加载策略：优先读取 `src/portfolio_mcp/data/portfolio_data.json`；
文件缺失或解析失败时，自动降级到代码内内置示例数据（保证"开箱即跑"）。

## 工具 / 资源 / 提示模板清单

### 工具（Tools）

| 名称 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `list_modules` | 无 | 模块概览列表（id / title / status / 一句话定位） | 返回作品集全部模块的概览 |
| `search_portfolio` | `keyword: str` | 命中模块列表（含相关性说明） | 按关键词在标题、定位、痛点、角色、架构、工具等字段中检索 |
| `get_item_detail` | `project_id: str` | 单个模块完整详情 | 按 id 返回模块详情；未命中返回失败信息 |

### 资源（Resources）

| 资源 URI | 说明 |
|---|---|
| `portfolio://modules` | 全部模块概览（与 list_modules 同源数据） |
| `portfolio://module/{id}` | 单个模块详情（与 get_item_detail 同源数据） |

### 提示模板（Prompts）

| 名称 | 输入 | 说明 |
|---|---|---|
| `interview_pitch_prompt` | `project_id: str` | 输入模块 id，返回一段"30 秒面试口播"提示词，供 LLM 作为系统提示使用 |

## 快速开始

要求：Python 3.11+，已安装 [uv](https://docs.astral.sh/uv/)。

```bash
# 1. 安装依赖（含 dev 分组：pytest / pytest-asyncio）
uv sync --extra dev

# 2. 运行测试
uv run pytest

# 3. 直接运行（stdio 模式，供 MCP 客户端连接）
uv run portfolio-mcp

# 4. 等价入口
uv run python -m portfolio_mcp

# 5. 用 MCP Inspector 可视化调试（推荐开发期使用）
uvx mcp dev src/portfolio_mcp/server.py
```

> `mcp dev` 会启动本地 Inspector 页面，可直观查看工具列表、资源、提示模板并逐个调用测试。

## 配置示例

### Claude Desktop

编辑 `claude_desktop_config.json`（Windows：`%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "portfolio": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Jav1e Flies/家辉专用/千问办公反馈结果/AI作品集网站（离线版）/04-企业级智能体系统(本地开发工程(enterprise-agent)/enterprise-agents/mcp/portfolio-mcp",
        "run",
        "portfolio-mcp"
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
    "portfolio": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Jav1e Flies/家辉专用/千问办公反馈结果/AI作品集网站（离线版）/04-企业级智能体系统(本地开发工程(enterprise-agent)/enterprise-agents/mcp/portfolio-mcp",
        "run",
        "portfolio-mcp"
      ]
    }
  }
}
```

> 路径中的中文与括号请原样保留；若换机/换目录部署，只需修改 `args[1]` 指向本项目的绝对路径。

## 演示截图 / GIF（占位说明）

> 占位：开发验证通过后，建议补充以下演示素材到 `assets/` 目录并在 README 中引用：
> 1. `assets/demo-inspector.png`：MCP Inspector 中工具列表 / 资源 / 提示模板的截图
> 2. `assets/demo-call.png`：在 Inspector 中调用 `list_modules` / `search_portfolio` / `get_item_detail` 的结果截图
> 3. `assets/demo-claude.gif`：Claude Desktop 中通过 MCP 查询作品集模块的演示 GIF

## 安全说明

- **无真实密钥**：本项目为纯本地数据查询，`.env.example` 中仅保留可选配置占位；代码中不含任何真实企业名、真实密钥或真实客户数据。
- **示例数据标注**：`portfolio_data.json` 与内置兜底数据均标注"示例"，仅用于展示工程能力。
- **数据自定义**：将 `src/portfolio_mcp/data/portfolio_data.json` 替换为自己的模块数据即可完成个性化，无需改代码。
- **仅供学习演示**：正式用于求职 / 面试场景时，请替换为本人真实作品集数据并人工核对口径。

## License

MIT。示例数据为演示用途（标注"示例"），与任何真实企业 / 客户无关。
