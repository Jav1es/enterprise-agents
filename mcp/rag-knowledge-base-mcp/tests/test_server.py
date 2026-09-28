"""rag-knowledge-base-mcp 测试：工具注册 / 三工具基本调用 / 资源与提示模板 / KPI 资源读取。

运行：cd 项目根目录 && PYTHONPATH=src python -m pytest tests -q
"""

import pytest

from rag_knowledge_base_mcp import server


# ============================ 实例与注册 ============================


def test_server_instance_name():
    """FastMCP 实例名应为 rag-knowledge-base。"""
    assert server.mcp.name == "rag-knowledge-base"


@pytest.mark.asyncio
async def test_tools_registered():
    """三个核心工具必须注册。"""
    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    assert {"add_document", "search", "retrieve_with_evidence"} <= names


@pytest.mark.asyncio
async def test_resources_and_templates_registered():
    """资源模板必须注册（knowledge://doc/{doc_id}、knowledge://kpi/{kpi_code}）。"""
    templates = await server.mcp.list_resource_templates()
    template_uris = {t.uriTemplate for t in templates}
    assert "knowledge://doc/{doc_id}" in template_uris
    assert "knowledge://kpi/{kpi_code}" in template_uris


@pytest.mark.asyncio
async def test_prompts_registered():
    """提示模板 policy_qa_prompt 必须注册。"""
    prompts = await server.mcp.list_prompts()
    assert "policy_qa_prompt" in {p.name for p in prompts}


def test_builtin_seed_loaded():
    """启动时应自动载入内置示例制度并建立 BM25 索引。"""
    assert server.STORE.doc_count() >= 3
    assert server.RETRIEVER._bm25 is not None


# ============================ add_document ============================


def test_add_document_ok():
    """add_document 应入库文档、返回 doc_id / 片段数 / 文档总数。"""
    before = server.STORE.doc_count()
    result = server.add_document(
        title="【示例】加班审批细则",
        content=(
            "第一条 工作日加班需提前 1 小时在 OA 提交加班申请，经直属主管审批后方可生效。"
            "第二条 加班时长按月累计，可申请调休或按国家规定支付加班费。"
            "第三条 法定节假日加班按 300% 支付加班工资。"
        ),
        source="示例-人力资源部",
    )
    assert result["success"] is True
    data = result["data"]
    assert data["doc_id"].startswith("doc-")
    assert data["chunk_count"] >= 1
    assert data["total_documents"] == before + 1


def test_add_document_missing_content():
    """content 为空时应返回失败而非崩溃。"""
    result = server.add_document(title="空文档", content="", source="示例")
    assert result["success"] is False
    assert "error" in result


# ============================ search ============================


def test_search_hits_builtin_policy():
    """search 应命中内置示例制度（考勤）。"""
    result = server.search(query="考勤 迟到 请假")
    assert result["success"] is True
    data = result["data"]
    assert data["total_hits"] > 0
    assert any("考勤" in h["title"] for h in data["hits"])
    # 每个命中片段都应包含可追溯字段
    for hit in data["hits"]:
        assert hit["doc_id"]
        assert hit["source"]
        assert hit["text"]
        assert hit["score"] > 0


def test_search_empty_query_fails():
    """空 query 应返回失败。"""
    result = server.search(query="")
    assert result["success"] is False


# ============================ retrieve_with_evidence ============================


def test_retrieve_with_evidence_no_key_falls_back():
    """未配置 LLM Key 时：返回引用证据并降级为纯 Top-K 检索结果。"""
    result = server.retrieve_with_evidence(query="报销 发票 流程")
    assert result["success"] is True
    data = result["data"]
    evidences = data["evidences"]
    assert len(evidences) > 0
    for ev in evidences:
        assert ev["doc_id"]
        assert ev["source"]
        assert ev["excerpt"]
        assert 0 <= ev["confidence"] <= 1
    # 未配置 LLM_API_KEY → generated_answer 为 None 且 note 提示降级
    assert data["generated_answer"] is None
    assert data["note"] is not None
    assert "降级" in data["note"]


def test_retrieve_with_evidence_top_k_respected():
    """top_k 应被尊重。"""
    result = server.retrieve_with_evidence(query="制度 管理", top_k=3)
    assert result["success"] is True
    assert len(result["data"]["evidences"]) <= 3


# ============================ 资源读取 ============================


@pytest.mark.asyncio
async def test_kpi_resource_read():
    """KPI 资源应返回指定 KPI 的口径定义文本。"""
    text = await server.kpi_resource("kpi-attendance-rate")
    assert "考勤出勤率" in text
    assert "公式" in text
    assert "示例" in text


@pytest.mark.asyncio
async def test_kpi_resource_not_found():
    """不存在的 KPI 编码应返回友好提示。"""
    text = await server.kpi_resource("kpi-not-exists")
    assert "未找到" in text


@pytest.mark.asyncio
async def test_doc_resource_read():
    """文档资源应返回文档全文。"""
    text = await server.doc_resource("policy-attendance")
    assert "考勤" in text
    assert "第一章" in text
    assert "全文" in text


@pytest.mark.asyncio
async def test_doc_resource_not_found():
    """不存在的 doc_id 应返回友好提示。"""
    text = await server.doc_resource("doc-not-exists")
    assert "未找到" in text


# ============================ 提示模板 ============================


def test_policy_qa_prompt_contains_context():
    """提示模板应包含检索片段与用户问题。"""
    prompt = server.policy_qa_prompt("报销标准是什么", top_k=3)
    assert "【用户问题】" in prompt
    assert "报销标准是什么" in prompt
    assert "【检索片段】" in prompt
