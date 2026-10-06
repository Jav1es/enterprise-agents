# RAG 知识库演示 (examples/rag_demo)

真实数据、可运行的 RAG（Retrieval-Augmented Generation）演示模块，直接复用仓库知识层
`src/enterprise_agent/knowledge/` 的既有模块：

- `indexer.split_documents` — 语义边界切分（chunk 500 / overlap 50）
- `HybridRetriever` — Dense + BM25 混合检索 + RRF 融合（`ZhHybridRetriever` 子类增强中文分词）
- `CrossEncoderReranker` — Cross-Encoder 重排（可选，需联网下载模型）
- `RAGPipeline` — 检索管线组装

## 目录内容

| 文件 | 说明 |
| --- | --- |
| `sample_policy.md` | 公开企业制度示例文档（员工手册，40 条制度，企业名已脱敏） |
| `eval_set.py` | 评测集：30 题三难度分层（easy/medium/hard 各 10）+ 5 道拒答题，黄金关键词人工标注 |
| `rag_demo.py` | 演示脚本：加载 → 建索引 → 提问 → 返回带引用来源的回答；无 Key 自动降级为 Top-K 检索结果 |
| `requirements.txt` | 额外依赖说明（主要复用仓库根目录依赖） |
| `RAG_Eval_Report.md` | 真实运行评测报告（检索准确率 / 拒答率 / 引用准确率 / 重排增量 / 幻觉风险） |

## 评测结果速览（30 题，真实运行）

| top_k | 检索准确率 |
|---|---|
| @1 | 73.3%（22/30） |
| **@3** | **93.3%（28/30）** |
| @5 | 93.3%（无增益） |

- Cross-Encoder 重排在本规模下**增量为 0**（原因与启用条件见报告第四节）；
- **RRF 分数无法用作拒答阈值** —— 「答得上」与「答不上」的题分数区间完全重叠（报告第五节）。

## 运行方式

```bash
# 1. 安装依赖（仓库根目录）
cd enterprise-agents
pip install uv && uv sync          # 或 pip install chromadb rank-bm25 langchain langchain-openai

# 2. 单问模式（无 LLM Key 时自动降级为 Top-K 检索结果）
PYTHONPATH=src python examples/rag_demo/rag_demo.py \
    --doc examples/rag_demo/sample_policy.md \
    --query "员工带薪年休假有多少天？"

# 3. 可选：配置 LLM（OpenAI 兼容接口，可指向本地 Ollama）
export LLM_API_KEY=YOUR_API_KEY        # 或 OPENAI_API_KEY
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_MODEL=qwen2.5:7b
PYTHONPATH=src python examples/rag_demo/rag_demo.py \
    --doc examples/rag_demo/sample_policy.md \
    --query "法定节假日加班费怎么算？"

# 4. 运行内置评测集（30 题分层 + 5 道拒答题）
PYTHONPATH=src python examples/rag_demo/rag_demo.py --eval --top-k 3

# 5. 对照评测：同时跑「无重排」与「有 Cross-Encoder 重排」并给出增量
#    首次需联网下载 bge-reranker-base
PYTHONPATH=src python examples/rag_demo/rag_demo.py --compare-rerank --top-k 3
```

Windows PowerShell 下设置环境变量：

```powershell
$env:PYTHONPATH = "src"
python examples/rag_demo/rag_demo.py --doc examples/rag_demo/sample_policy.md --query "员工带薪年休假有多少天？"
```

## 说明

- API Key 一律使用环境变量注入，示例占位 `YOUR_API_KEY`，严禁硬编码真实密钥。
- 示例文档企业名、人名均脱敏，内容为通用公开制度框架，仅用于技术演示。
- 无 LLM Key 时脚本降级返回 Top-K 命中片段与引用来源（含章节标注），保证演示可离线跑通。
