"""内置示例 KPI 口径数据（仅演示用途，全部标注"示例"）。

替换本文件即可接入真实 KPI 口径，无需改动 server.py。
字段说明：
- kpi_code:   KPI 唯一编码（用于 knowledge://kpi/{kpi_code} 资源）
- name:       KPI 名称
- definition: 口径定义
- formula:    计算公式
- frequency:  统计频率
- data_source: 数据来源
- note:       说明（示例标注）
"""

# 【示例】考勤出勤率
KPI_ATTENDANCE_RATE = {
    "kpi_code": "kpi-attendance-rate",
    "name": "考勤出勤率",
    "definition": "统计周期内员工实际出勤人日数与应出勤人日数的比值，衡量整体出勤水平。",
    "formula": "出勤率 = 实际出勤人日数 / 应出勤人日数 × 100%",
    "frequency": "月度",
    "data_source": "考勤系统打卡记录（示例）",
    "note": "示例 KPI，仅用于演示 MCP 资源能力",
}

# 【示例】报销处理时效
KPI_REIMBURSEMENT_TAT = {
    "kpi_code": "kpi-reimbursement-tat",
    "name": "报销处理时效（TAT）",
    "definition": "从员工提交报销单到财务完成打款的平均自然日天数，衡量报销流程效率。",
    "formula": "平均处理时效 = Σ(打款日期 - 提交日期) / 报销单数量",
    "frequency": "月度",
    "data_source": "OA 报销系统（示例）",
    "note": "示例 KPI，仅用于演示 MCP 资源能力",
}

# 【示例】信息安全事件数
KPI_SECURITY_INCIDENTS = {
    "kpi_code": "kpi-security-incidents",
    "name": "信息安全事件数",
    "definition": "统计周期内发生的信息安全事件数量（含病毒、钓鱼、数据泄露、违规操作等），越低越好。",
    "formula": "事件数 = 已确认的信息安全事件累计数量",
    "frequency": "季度",
    "data_source": "安全运营平台（示例）",
    "note": "示例 KPI，仅用于演示 MCP 资源能力",
}

# 【示例】员工满意度
KPI_EMPLOYEE_SATISFACTION = {
    "kpi_code": "kpi-employee-satisfaction",
    "name": "员工满意度",
    "definition": "通过年度/半年度员工调研获得的综合满意度得分，反映组织氛围与员工体验。",
    "formula": "满意度 = 满意及非常满意样本数 / 有效回收样本数 × 100%",
    "frequency": "半年度",
    "data_source": "员工调研问卷（示例）",
    "note": "示例 KPI，仅用于演示 MCP 资源能力",
}

# 全部示例 KPI 列表
KPIS = [
    KPI_ATTENDANCE_RATE,
    KPI_REIMBURSEMENT_TAT,
    KPI_SECURITY_INCIDENTS,
    KPI_EMPLOYEE_SATISFACTION,
]
