"""扩展评测集：30 题 × 三难度分层 + 5 道「文档外」拒答题。

设计要点（这是对原 6 题评测集的实质性加强）：

1. **规模**：6 题 → 30 题。6 题时准确率只能取 1/6 = 16.7% 的整数倍，
   统计上无法区分 83% 与 100%；30 题的分辨率是 3.3%，结论才站得住。

2. **难度分层**：
   - easy   (10 题)：黄金关键词为强术语，BM25 就能命中，检验索引与切分是否正确
   - medium (10 题)：问法与制度原文措辞不一致，��同一制度的不同侧面发问
   - hard   (10 题)：跨条款推理型问法（如"迟到 5 小时按什么处理"需同时命中第6条与第5条）

3. **拒答集（5 题）**：文档里**根本没有**的条款（（如"股票期权"），
   检验系统会不会编。这类题的正确答案是「查不到」，命中反而是幻觉。
   ⚠️ 这直接对应 AGENTS.md 的纪律：任何「不存在」的结论必须先做正对照。

评测输出同时给三档 top_k 与「拒答集是否误答」，避免只报一个好看的数字。
"""

from __future__ import annotations

# 黄金章节 + 必须同时出现的关键词（全部来自 sample_policy.md 的真实措辞）
EVAL_SET: list[dict[str, object]] = [
    # ---------- EASY：强术语，BM25 可直接命中 ----------
    {"query": "员工带薪年休假的天数如何规定？", "gold_chapter": "第9条", "difficulty": "easy",
     "gold_keywords": ["年休假", "5 天", "15 天"]},
    {"query": "法定节假日加班费按几倍工资支付？", "gold_chapter": "第16条", "difficulty": "easy",
     "gold_keywords": ["300%", "法定节假日"]},
    {"query": "员工主动离职需要提前多少天提交申请？", "gold_chapter": "第35条", "difficulty": "easy",
     "gold_keywords": ["30 天", "离职申请"]},
    {"query": "虚假的报销单据会被如何处理？", "gold_chapter": "第20条", "difficulty": "easy",
     "gold_keywords": ["2 倍", "虚假报销"]},
    {"query": "违反保密制度有什么后果？", "gold_chapter": "第25条", "difficulty": "easy",
     "gold_keywords": ["解除劳动合同", "保密"]},
    {"query": "公司每个月的发薪日是几号？", "gold_chapter": "第15条", "difficulty": "easy",
     "gold_keywords": ["10 日", "工资"]},
    {"query": "男员工配偶生育可以休几天陪产假？", "gold_chapter": "第12条", "difficulty": "easy",
     "gold_keywords": ["陪产假", "15 天"]},
    {"query": "连续旷工几天公司可以解除劳动合同？", "gold_chapter": "第7条", "difficulty": "easy",
     "gold_keywords": ["旷工", "解除劳动合同"]},
    {"query": "丧假有几天？", "gold_chapter": "第13条", "difficulty": "easy",
     "gold_keywords": ["丧假", "3 天"]},
    {"query": "公司的全勤奖在迟到时会怎么扣？", "gold_chapter": "第6条", "difficulty": "easy",
     "gold_keywords": ["全勤奖", "50 元"]},

    # ---------- MEDIUM：问法与原文措辞不同，需语义匹配 ----------
    {"query": "年休假没休完可以怎么办？", "gold_chapter": "第9条", "difficulty": "medium",
     "gold_keywords": ["顺延", "第一季度"]},
    {"query": "请病假需要提供什么证明？", "gold_chapter": "第10条", "difficulty": "medium",
     "gold_keywords": ["诊断证明", "二级以上医院"]},
    {"query": "事假期间的工资怎么算？", "gold_chapter": "第11条", "difficulty": "medium",
     "gold_keywords": ["事假", "不计发工资"]},
    {"query": "工作日加班和休息日加班的加班费比例分别是多少？", "gold_chapter": "第16条", "difficulty": "medium",
     "gold_keywords": ["150%", "200%"]},
    {"query": "出差住宿费在一线城市每晚最多能报多少？", "gold_chapter": "第19条", "difficulty": "medium",
     "gold_keywords": ["600 元", "一线城市"]},
    {"query": "报销发票有什么格式要求？", "gold_chapter": "第21条", "difficulty": "medium",
     "gold_keywords": ["发票", "PDF 原件"]},
    {"query": "公司信息系统的账号可以借给别人用吗？", "gold_chapter": "第23条", "difficulty": "medium",
     "gold_keywords": ["账号", "禁止转借"]},
    {"query": "绩效考核一年开展几次？结果分几个等级？", "gold_chapter": "第31条", "difficulty": "medium",
     "gold_keywords": ["季度", "S", "D"]},
    {"query": "公司有哪些晋升通道？", "gold_chapter": "第33条", "difficulty": "medium",
     "gold_keywords": ["管理序列", "专业序列"]},
    {"query": "离职时需要交接哪些东西？", "gold_chapter": "第36条", "difficulty": "medium",
     "gold_keywords": ["交接", "系统权限"]},

    # ---------- HARD：跨条款 / 需推理的问法 ----------
    {"query": "员工迟到 5 个小时应该按什么假处理？", "gold_chapter": "第6条", "difficulty": "hard",
     "gold_keywords": ["事假", "一天"]},
    {"query": "员工忘记打卡且 24 小时内没补卡说明会怎样？", "gold_chapter": "第5条", "difficulty": "hard",
     "gold_keywords": ["旷工半日", "补卡"]},
    {"query": "连续工作满 12 年的员工年休假有多少天？", "gold_chapter": "第9条", "difficulty": "hard",
     "gold_keywords": ["10 年", "20 年", "15 天"]},
    {"query": "产假期间难产会增加多少天？", "gold_chapter": "第12条", "difficulty": "hard",
     "gold_keywords": ["98 天", "难产", "15 天"]},
    {"query": "紧急出差可以事后补办手续吗？几天内？", "gold_chapter": "第18条", "difficulty": "hard",
     "gold_keywords": ["补办", "3 个工作日"]},
    {"query": "离职员工的工资什么时候结清？", "gold_chapter": "第37条", "difficulty": "hard",
     "gold_keywords": ["最后一个工作日", "结算"]},
    {"query": "公司对员工年度培训学时的要求是什么？", "gold_chapter": "第34条", "difficulty": "hard",
     "gold_keywords": ["40 学时", "培训"]},
    {"query": "员工收受商务伙伴的礼品多少钱以上要上交？", "gold_chapter": "第26条", "difficulty": "hard",
     "gold_keywords": ["200 元", "上交"]},
    {"query": "绩效面谈应该在考核结束后多久内完成？", "gold_chapter": "第32条", "difficulty": "hard",
     "gold_keywords": ["10 个工作日", "面谈"]},
    {"query": "员工可以对外兼职吗？有什么限制？", "gold_chapter": "第27条", "difficulty": "hard",
     "gold_keywords": ["竞争", "申报"]},
]

# ---------- 拒答集：文档中**不存在**的内容 ----------
# 正确行为是「查不到 / 明确说资料不足」，命中即幻觉。
UNANSWERABLE_SET: list[dict[str, str]] = [
    {"query": "公司的股票期权怎么行权？", "reason": "文档无股权激励条款"},
    {"query": "餐补每天多少钱？", "reason": "文档只有差旅餐饮补贴，无日常餐补"},
    {"query": "住房公积金缴纳比例是多少？", "reason": "文档只提缴纳公积金，未写比例"},
    {"query": "公司的年会预算上限是多少？", "reason": "文档无预算相关内容"},
    {"query": "远程办公可以申请几天？", "reason": "文档无远程办公制度"},
]
