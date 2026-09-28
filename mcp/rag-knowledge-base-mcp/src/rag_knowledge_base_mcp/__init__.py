"""rag-knowledge-base-mcp：基于 RAG 的企业知识库问答 MCP Server。

将企业制度 / 规范文档入库（BM25 检索），暴露为
MCP 工具（add_document / search / retrieve_with_evidence）、
资源（knowledge://doc/{doc_id}、knowledge://kpi/{kpi_code}）与
提示模板（policy_qa_prompt）。

所有数据均为示例数据（标注"示例"），不含真实企业名 / 真实密钥 / 真实客户数据。
"""

__version__ = "0.1.0"
