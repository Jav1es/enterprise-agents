# 架构设计文档

本文档基于《企业级智能体系统开发文档.md》整理，描述 enterprise-agent 的整体架构。

## 1. 六层架构

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

## 2. 编排层设计

LangGraph StateGraph 五阶段链路：Router → Planner → Skill → Tool → Reviewer → END。

- **Router**: 任务路由（knowledge / data / mixed）
- **Planner**: 步骤规划
- **Retrieve**: RAG 知识检索
- **Tool Call**: 工具执行（支持多步循环）
- **Reviewer**: 结构化校验
- **Respond**: 最终回复

状态对象见 `src/enterprise_agent/orchestration/state.py`。

## 3. 记忆层设计

双视野记忆模型：

| 视野 | 存储 | 能力 |
| --- | --- | --- |
| 短期记忆 | Redis | 会话状态、TTL 30 分钟、滚动摘要、上下文预算 |
| 长期记忆 | PostgreSQL | 事实三元组、用户偏好、冲突检测、热度提升、时间修剪 |

## 4. 知识层设计

RAG 链路：语义边界切分（chunk 500 / overlap 50）→ 向量化 → Dense + BM25 混合检索 → RRF 融合（k=60）→ Cross-Encoder 重排（BAAI/bge-reranker-base）→ 附带引用来源。

## 5. 容错设计

| 错误类型 | 处理策略 | 实现 |
| --- | --- | --- |
| 瞬态错误（网络/限流） | 指数退避重试 | ModelRetryMiddleware |
| LLM 可恢复错误 | 转为 ToolMessage 反馈 | ToolErrorMiddleware |
| Provider 宕机 | 自动降级备用模型 | ModelFallbackMiddleware |
| 过度调用（死循环） | 限制调用次数 | ModelCallLimitMiddleware |
| 连续失败 | 熔断（阈值 5，半开恢复） | CircuitBreaker |

## 6. 部署

- 本地开发：Docker Compose（agent-api / redis / postgres-pgvector）
- 生产：K8s Helm Chart（HPA CPU 阈值 70%，Liveness/Readiness 探针）
