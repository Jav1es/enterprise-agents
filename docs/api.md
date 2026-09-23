# API 文档

服务启动后访问 `http://localhost:8080/docs` 获取 Swagger UI 交互式文档。

## 接口列表

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/v1/chat` | 同步对话接口 |
| POST | `/v1/chat/stream` | SSE 流式对话接口 |
| GET | `/health` | 健康检查 |

## A.1 同步问答 /v1/chat

```bash
curl -X POST http://localhost:8080/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "session_id": "sess_001",
    "user_id": "u_1001",
    "message": "本周待发货订单有多少？",
    "channel": "wecom",
    "stream": false
  }'
```

响应示例：

```json
{
  "session_id": "sess_001",
  "reply": "本周共 1,286 笔待发货订单，其中华南仓 412 笔、华东仓 388 笔…",
  "trace_id": "trc_9f2c",
  "citations": [
    {"source": "dws_order_daily", "chunk_id": 1024, "score": 0.91}
  ],
  "latency_ms": 1840
}
```

## A.2 流式问答 /v1/chat/stream（SSE）

```text
data: {"delta": "本周"}
data: {"delta": "共 1,286 笔"}
data: {"delta": "待发货订单"}
data: [DONE]
```

## A.3 工具调用链路（多步）

```
用户：查一下库存低于安全线的 SKU，并生成补货建议
链路：Router(intent=inventory) → Planner(2步) → Tool1:query_stock(低库存) → Tool2:gen_replenish(SKU清单) → Reviewer(校验补货量) → Reply
```

## 压测方案

使用 Locust 进行负载测试，重点关注：

- TTFT（首 Token 时间，流式场景）
- P95/P99 端到端延迟
- 吞吐量（QPS）与错误率

建议：先在 Mock LLM 环境中测出基础设施吞吐量，再叠加真实 LLM 延迟进行全链路压测。
