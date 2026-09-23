# 开发指引

## 环境准备

```bash
# 安装 uv（Python 包管理器）
pip install uv

# 同步依赖（生成 .venv 与 uv.lock）
uv sync

# 安装全部可选分组
uv sync --all-extras
```

## 本地开发

```bash
# 配置环境变量
cp .env.example .env

# 启动依赖服务
docker compose up -d redis postgres

# 启动开发服务器（热重载）
uv run uvicorn enterprise_agent.api.main:app --reload --port 8080
```

## 代码规范

```bash
# Lint
uv run ruff check src tests

# 格式化
uv run ruff format src tests

# 类型检查
uv run mypy src

# 单元测试
uv run pytest -v
```

## 提交前检查

```bash
bash scripts/check_sensitive.sh
```

## 模块开发清单

- [ ] orchestration: 节点实现（router/planner/retrieve/tool_call/reviewer/respond）
- [ ] memory: Redis 短期记忆读写 + PostgreSQL 长期事实三元组
- [ ] knowledge: 文档加载、切分、向量化、混合检索、重排
- [ ] tools: ERP/CRM 客户端封装、MCP 客户端、HTTP Connector
- [ ] channels: 钉钉/企微/OA 通道实现
- [ ] api: 同步/流式对话路由接入真实工作流
- [ ] middleware: 重试/降级/熔断接入 LLM 调用链
