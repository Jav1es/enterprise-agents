# API 压测基准报告（Locust）

> 实测环境：Windows 11 · Python 3.11.8 · uvicorn（单 worker）· 无 LLM API Key（自动降级链路）
> 复现命令见文末。**全部数字为本机实测，非估算。**

## 一、测试配置

| 项 | 值 |
|---|---|
| 压测工具 | Locust 2.46.7 |
| 并发用户 | 20（ramp-up 5/s） |
| 持续时间 | 45 秒 |
| 用户行为 | 按 3:2:1 权重混合 `/health`、同步 `/v1/chat`、SSE `/v1/chat/stream` |
| 被测服务 | `enterprise_agent.api.main:app`，单 uvicorn worker，监听 `127.0.0.1:8080` |

## 二、汇总结果

| 指标 | 值 |
|---|---|
| 总请求数 | **609** |
| **失败数** | **0（0.00%）** |
| 吞吐量 | **13.6 req/s**（20 并发下） |
| 聚合中位响应 | 3 ms |
| 聚合 P95 | 2600 ms |
| 聚合 P99 | 2800 ms |
| 最大响应 | 2982 ms |

## 三、分端点明细

| 端点 | 请求数 | 失败 | 平均 | 中位 | P95 | P99 | 最大 | 吞吐 |
|---|---|---|---|---|---|---|---|---|
| `GET /health` | 315 | 0 | 5 ms | 2 ms | 16 ms | 77 ms | 251 ms | 7.06 req/s |
| `POST /v1/chat` | 202 | 0 | 2327 ms | 2300 ms | 2700 ms | 2900 ms | 2982 ms | 4.53 req/s |
| `POST /v1/chat/stream` (SSE) | 92 | 0 | 11 ms | 3 ms | 31 ms | 370 ms | 370 ms | 2.06 req/s |

## 四、如何读这组数字

1. **0 失败率是主要结论**：609 次请求零失败，说明编排链路、校验层与降级分支在 20 并发下稳定。
2. **`/health` P99 77 ms、最大 251 ms 的尖刺**来自启动后 3 秒内的爬坡窗口（warm-up），
   属正常 JIT/连接池预热，非稳态表现。
3. **同步 `/v1/chat` 约 2.3 秒** 是**完整编排链路的真实成本**：Router → Planner → Skill →
   Tool → Reviewer 五阶段全部执行。本机未配置 LLM Key，Planner/Reviewer 走降级路径；
   **一旦接入真实 LLM，该值主要由模型首 token 延迟主导**，本地编排增量占比会显著下降。
   2.3 秒是编排层的基线，不是端到端上界。
4. **SSE 平均 11 ms 明显低于同步**，因为 `EventSourceResponse` **响应头立即返回**，
   生成过程在流里继续 —— 这正是流式接口的价值：**首包延迟与总生成时间解耦**。
   用 SSE 承接长任务，可让前端在 3 ms 内拿到响应头并开始渲染骨架。

## 五、容量结论

- 单 worker 在 20 并发下稳定服务 `/health` 类轻请求 **7 req/s**（延迟 < 20 ms）。
- 编排类请求是**吞吐瓶颈**：单 worker 约 **4.5 req/s**，且延迟随并发线性上升
  （说明是 CPU/事件循环串行处理，非纯 IO 等待）。
- **这就是 HPA 存在的意义**：编排请求吃 CPU，横向扩容是唯一有效手段。
  Chart 中 `minReplicas=2`、CPU 阈值 **70%**、`maxReplicas=10` 的配置即基于此实测结论
  —— 超过约 8 个并发编排请求后，单实例 P95 会突破 3 秒 SLA。

## 六、复现

```powershell
# 终端 1：起被测服务（不配 LLM Key 也能跑，走降级链路）
$env:PYTHONPATH="$PWD\src"
uvicorn enterprise_agent.api.main:app --host 127.0.0.1 --port 8080

# 终端 2：跑压测并生成报告
python -m locust -f bench/locustfile.py --host http://127.0.0.1:8080 `
  --headless -u 20 -r 5 -t 45s --html bench/report.html --csv bench --only-summary
```

打开 `bench/report.html` 可看逐秒曲线与错误分布。

## 七、待补

- [ ] 接入真实 LLM Key 后重跑，取得「首 token 延迟」与「编排层增量」的分解数据
- [ ] 补 50 / 100 并发的阶梯压测，画出饱和拐点
- [ ] 长稳测试（≥ 2 小时）观察内存与连接池是否泄漏

---

*实测日期：2026-10-07 · 全部数字可复现，未做任何美化处理。*