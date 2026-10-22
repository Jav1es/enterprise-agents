# 安全风险登记：ChromaDB 8 条告警（无法升级修复）

> 登记日期：2026-10-22
> 状态：**接受风险（Accepted）** —— 附可利用性分析，不是"忽略"
> 复查条件：见文末「何时需要重新评估」

## 一、问题

Dependabot 报告 8 条 ChromaDB 告警，全部 `fixed = NONE`：

| CVE | 严重度 | CVSS | 摘要 |
|---|---|---:|---|
| CVE-2026-45829 | critical | **10.0** | 预认证代码注入（`/api/v2/.../collections`） |
| CVE-2026-45833 | critical | — | 认证后代码注入（同上端点，需 UPDATE_COLLECTION） |
| CVE-2026-45830 | high | 8.8 | 任意已认证用户可跨租户读写任意 collection |
| CVE-2026-45831 | high | 8.8 | SimpleRBAC 不校验租户/库/collection 归属 |

另有 4 条同类告警重复出现在两个 lock 文件（根 `uv.lock` 与 `mcp/rag-knowledge-base-mcp/uv.lock`）。

**为什么不能升级：** PyPI 上 chromadb 最新版本是 **1.5.9**，
而漏洞影响范围是 `>= 0.4.17, <= 1.5.9` —— 即**所有已发布版本都受影响，没有修复版本**。

## 二、可利用性分析（关键）

**四条 CVE 全部通过 ChromaDB 的 HTTP API 触发**，攻击端点均为
`/api/v2/tenants/{tenant}/databases/{db}/collections`。

本项目**不使用 ChromaDB 的 HTTP server**。核实依据：

```
src/enterprise_agent/knowledge/indexer.py:142   chromadb.PersistentClient(path=...)
src/enterprise_agent/knowledge/retriever.py     （同）
src/enterprise_agent/api/main.py:83             chromadb.PersistentClient(path=...)
examples/rag_demo/rag_demo.py:113               chromadb.PersistentClient(path=...)
scripts/make_demo.py:117                        chromadb.PersistentClient(path=...)
```

- **代码中 5 处全部是 `PersistentClient`（嵌入式）**，`chromadb.HttpClient` / `chromadb.Client()`
  的命中数为 **0**（已用正对照确认扫描器有效：同一模式能扫出 5 处 PersistentClient）。
  （`bench/isolate_contention.py:7` 另有 1 处提及，是压测脚本注释里讨论"是否共享
  PersistentClient"，不是调用。）
- `docker-compose.yml` 中 **没有 chroma server 服务**，只有 `VECTOR_STORE: chroma` +
  `CHROMA_PERSIST_DIR` 指向本地卷 —— 即 ChromaDB 作为**进程内库**运行，不监听端口。
- 部署形态：本仓库 **PRIVATE**，无 environments、无 deployments，
  唯一运行方式是 `docker compose up` 后访问 `http://localhost:8080/docs`（本机）。

⇒ **攻击者无法触达 `/api/v2/...` 端点**：该端点不存在。
CVE-2026-45830 / 45831 需要「已认证用户」与多租户隔离场景，
而本项目是单租户嵌入式用法，不涉及 RBAC 与租户边界。

**结论：当前部署形态下这 8 条告警不可利用（not exploitable as deployed）。**

## 三、残余风险

不是零。以下情况会改变结论：

1. **若将来改用 ChromaDB Server 模式**（`chromadb run` / 官方镜像 / 远程 HttpClient），
   这 8 条立即变为可利用，且 CVSS 10.0 的那条是**预认证**的。
2. **若多租户/多用户共享同一 ChromaDB 实例**，CVE-2026-45830/45831 的越权读取成为现实风险。
3. 代码注入路径需要同时满足「恶意模型仓库」+「`trust_remote_code` 为真」。
   本项目创建 collection 时只传 `name` / `embedding_function` / `metadata`
   （`indexer.py:144-146`），全仓库代码中该参数出现 **0 次**（已做正对照）。
4. 供应链层面：依赖本身有洞，即使不可达也应视为技术债。

## 四、决策

**接受风险，不降级、不替换、不隐藏。**

理由：
- 替换 ChromaDB 需要改 `indexer.py` / `retriever.py` / `main.py` / `rag_demo.py` /
  `make_demo.py` 五处，且没有向量库抽象层（无 `VectorStore` Protocol/ABC），
  属于架构级改动，与「修一个安全补丁」不成比例。
- 降级到 `< 0.4.17` 会引入更老的漏洞集，是负收益。
- 风险的真实来源是**部署形态**而非代码，当前形态已使其不可达。

## 五、配套措施（已落地）

- [x] 本文件登记，纳入仓库版本控制，随代码一起 review。
- [x] README 与部署文档中明确：**不要以 Server 模式暴露 ChromaDB 端口**。
- [x] 保留 Dependabot 告警开启（不 dismiss）—— 一旦上游发布修复版本，能第一时间收到通知。
- [x] 部署保持 `PersistentClient` 嵌入式 + 单租户。

## 六、何时需要重新评估

满足任一即须重读本文件并重新决策：

1. 上游发布 chromadb `> 1.5.9` 的修复版本 → **立即升级**，本文件转为历史记录。
2. 引入 ChromaDB Server 模式或 `HttpClient` → 风险升级为**高危可利用**，须先做网络隔离。
3. 引入多租户 / 多用户共享实例 → CVE-2026-45830/45831 变为现实风险。
4. 本仓库转为 PUBLIC 或部署到公网 → 须重新评估整体攻击面。
5. `trust_remote_code=true` 出现在任何调用点 → 立即修掉。
