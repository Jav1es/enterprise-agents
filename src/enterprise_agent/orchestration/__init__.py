"""编排层 — LangGraph 状态图工作流。

五阶段链路: Router → Planner → Skill → Tool → Reviewer → END
通过 Pydantic 结构化输出衔接各阶段。
"""
