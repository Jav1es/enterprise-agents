# 部署文档

## 1. Docker Compose 本地部署

```bash
# 一键启动全部服务（agent-api + redis + postgres-pgvector）
docker compose up -d --build

# 仅启动依赖服务
docker compose up -d redis postgres

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f agent-api
```

访问 `http://localhost:8080/docs` 查看 Swagger UI。

## 2. 生产环境（K8s + Helm）

```bash
# 安装 Helm Chart
helm install enterprise-agent ./deploy/helm

# 升级
helm upgrade enterprise-agent ./deploy/helm

# 卸载
helm uninstall enterprise-agent
```

### 生产配置要点

- HPA 自动扩缩容：CPU 阈值 70%
- Liveness / Readiness 探针
- Secret 加密存储（勿写入 ConfigMap）
- 网络策略最小化
- 镜像签名与漏洞扫描（trivy）

### ⚠️ ChromaDB 必须以嵌入式方式使用

**不要把 ChromaDB 以 Server 模式暴露任何端口。**

本项目所有调用点都使用 `chromadb.PersistentClient(path=...)`（进程内嵌入式），
`docker-compose.yml` 里也没有 chroma server 服务 —— 这是刻意的安全选择，不是省事。

原因：ChromaDB 现有全部版本（`0.4.17` ~ `1.5.9`）存在 8 条未修复漏洞，
其中 **CVE-2026-45829 是 CVSS 10.0 的预认证代码注入**，攻击面正是它的 HTTP API
（`/api/v2/tenants/{tenant}/databases/{db}/collections`）。嵌入式模式下该端点不存在，
漏洞不可触达；一旦起 server 模式并监听端口，这些漏洞立即变为可利用。

完整分析、残余风险与重新评估条件见
[`docs/security-risk-chromadb.md`](./security-risk-chromadb.md)。

**若确需 server 模式**（例如多进程共享向量库），必须先完成：
1. 绑定 `127.0.0.1` 或置于内网，绝不对公网暴露；
2. 前置认证网关，不依赖 ChromaDB 自带的 RBAC（CVE-2026-45830/45831 说明其校验不可信）；
3. 单租户部署，不与他人共享实例。

## 3. 可观测性

| 组件 | 说明 |
| --- | --- |
| 日志 | 结构化 JSON，trace_id 贯穿全链路，保留 30 天；审计日志 180 天 |
| 指标 | Prometheus（QPS/延迟分位/错误率/LLM 调用/工具成功率），Grafana 大盘 |
| 追踪 | OpenTelemetry + Jaeger，按 trace_id 回放会话全链路 |
| 告警 | P0 服务不可用 10 分钟响应；P1 核心功能受损 30 分钟；P2 一般异常当日处理 |
