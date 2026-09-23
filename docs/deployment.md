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

## 3. 可观测性

| 组件 | 说明 |
| --- | --- |
| 日志 | 结构化 JSON，trace_id 贯穿全链路，保留 30 天；审计日志 180 天 |
| 指标 | Prometheus（QPS/延迟分位/错误率/LLM 调用/工具成功率），Grafana 大盘 |
| 追踪 | OpenTelemetry + Jaeger，按 trace_id 回放会话全链路 |
| 告警 | P0 服务不可用 10 分钟响应；P1 核心功能受损 30 分钟；P2 一般异常当日处理 |
