# Enterprise Agent

> 面向企业场景的本地智能体（Agent）系统：工作流编排、工具调用、记忆管理、RAG 知识库四大核心能力。

Enterprise Agent 是一个可本地部署的企业级智能体系统，通过标准化 API 层对接 ERP/CRM/OA/钉钉/企微等企业系统，内置容错重试与降级机制，支持 Docker Compose 本地部署及 Kubernetes 集群部署。

因为我认为 AI 落地不能只停留在概念，所以我花时间搭建了这个企业级智能体系统。架构上我设计了六层（接入、编排、工具、记忆、知识、LLM），编排用了 LangGraph，记忆做了 Redis 短期和 PostgreSQL 长期的双视野设计，RAG 用了 Dense+BM25 混合检索和 Cross-Encoder 重排。工程上我用 Docker Compose 和 Helm 做了部署，并且配了 GitHub Actions 做 CI，确保代码质量和敏感信息不泄露。虽然底层代码是我在 AI 辅助下完成的，但整个架构的设计和落地的思路是我主导的。

## 技术栈

Python 3.11+ · FastAPI · LangGraph · LangChain · Pydantic v2 · ChromaDB/Milvus · Redis · SQLAlchemy · MCP SDK · Docker · Helm/K8s

## 六层架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    接入层 (Channel Layer)               │
│  钉钉 Channel │ 企微 Channel │ OA Channel │ ERP/CRM     │
├─────────────────────────────────────────────────────────┤
│                   编排层 (Orchestration Layer)          │
│  LangGraph StateGraph: Router → Planner → Skill →     │
│                        Tool → Reviewer → END          │
├─────────────────────────────────────────────────────────┤
│                     工具层 (Tool Layer)                 │
│      Native Tool Calling │ MCP Protocol │ HTTP Connector│
├─────────────────────────────────────────────────────────┤
│                    记忆层 (Memory Layer)                │
│  短期记忆: Redis (会话状态/TTL/滚动摘要)                │
│  长期记忆: MySQL/PostgreSQL (事实三元组/偏好/历史)      │
├─────────────────────────────────────────────────────────┤
│                   知识层 (Knowledge Layer)              │
│  向量库: ChromaDB(开发) / Milvus(生产)                 │
│  检索: Dense + BM25 → RRF → Cross-Encoder 重排         │
├─────────────────────────────────────────────────────────┤
│                     LLM 推理层                          │
│  DeepSeek / Qwen / Ollama 本地模型 (OpenAI 兼容接口)   │
└─────────────────────────────────────────────────────────┘
```

## 核心能力

- **工作流编排**：基于 LangGraph StateGraph 的五阶段链路（Router → Planner → Skill → Tool → Reviewer），Pydantic 结构化输出衔接各阶段。
- **工具调用**：统一工具抽象（Pydantic Schema），支持 Native Tool Calling / MCP Protocol / HTTP Connector。
- **记忆管理**：双视野记忆模型——短期会话（Redis，TTL 30 分钟、滚动摘要）+ 长期持久（PostgreSQL 事实三元组，去重与冲突检测、热度提升、时间修剪）。
- **RAG 知识库**：语义边界切分（chunk 500 / overlap 50）→ Dense + BM25 混合检索 → RRF 融合 → Cross-Encoder 重排，检索结果附引用来源。
- **容错降级**：指数退避重试、LLM 可恢复错误回传 ToolMessage、Provider 宕机自动降级备用模型、调用次数限制防死循环、熔断器。
- **统一接入**：钉钉 / 企微（wecom-aibot-python-sdk WebSocket 长连接）/ OA / ERP 消息统一抽象为 UnifiedMessage。

## 快速开始

```bash
# 1. 克隆项目并安装依赖
cd enterprise-agents
pip install uv && uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM API Key、企业系统凭证 (ERP/CRM/钉钉/企微)

# 3. 启动依赖服务（Redis + PostgreSQL）
docker compose up -d redis postgres

# 4. 初始化 RAG 知识库
uv run python -m enterprise_agent.knowledge.indexer --docs ./docs/

# 5. 启动 Agent 服务
uv run uvicorn enterprise_agent.api.main:app --reload --port 8080

# 6. 访问 API 文档
open http://localhost:8080/docs
```

## API 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/v1/chat` | 同步对话接口 |
| POST | `/v1/chat/stream` | SSE 流式对话接口 |
| GET | `/health` | 健康检查 |

启动后访问 `http://localhost:8080/docs` 获取自动生成的 Swagger UI 交互式文档。

## 项目结构

```
enterprise-agents/
├── src/
│   └── enterprise_agent/
│       ├── orchestration/          # LangGraph 编排层
│       ├── memory/                 # 双视野记忆层
│       ├── knowledge/              # RAG 知识层
│       ├── tools/                  # 工具层
│       ├── channels/               # 接入层
│       ├── api/                    # FastAPI 服务入口
│       ├── middleware/             # 容错重试降级中间件
│       └── config/                 # 配置管理
├── tests/
├── docs/
├── scripts/
├── .github/workflows/
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── config.example.yaml
```

## 文档

- [架构设计](docs/architecture.md)
- [API 文档](docs/api.md)

## 安全说明

- `.env`、`config.yaml`、`*.key`、`*.pem` 等敏感文件已被 `.gitignore` 排除，严禁提交。
- 所有密钥一律使用环境变量注入，示例见 `.env.example`。
- 提交前运行 `bash scripts/check_sensitive.sh` 扫描硬编码密钥。

## License

MIT License — 详见 [LICENSE](LICENSE)。
