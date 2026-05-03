from __future__ import annotations

import json

from eka.settings import settings


DOCS = {
    "travel_reimbursement.md": """# 差旅报销制度

## 适用范围
本制度适用于正式员工、实习生和外聘顾问因公司业务产生的交通、住宿和餐饮费用。

## 实习生差旅标准
实习生出差需由直属导师提前审批。城市间交通优先选择二等座或经济舱。
实习生住宿标准为一线城市每晚不超过 350 元，其他城市每晚不超过 260 元。
实习生餐补标准为每天 80 元，凭有效票据或电子行程记录报销。

## 正式员工差旅标准
正式员工住宿标准为一线城市每晚不超过 550 元，其他城市每晚不超过 420 元。
部门负责人可在项目预算允许时审批上浮 20%。

## 报销流程
员工应在出差结束后 10 个工作日内提交报销单，上传发票、行程单和审批记录。
财务会在 5 个工作日内完成初审，缺少材料时退回补充。
""",
    "leave_policy.md": """# 请假制度

## 年假
正式员工入职满一年后享有带薪年假。累计工作满 1 年不满 10 年的，每年 5 天；
满 10 年不满 20 年的，每年 10 天；满 20 年的，每年 15 天。

## 病假
病假超过 1 天需提交医院证明。连续病假超过 5 个工作日时，HRBP 会介入确认复工安排。

## 请假流程
员工应在系统中提交请假申请，直属经理审批后生效。紧急情况可先口头报备，返岗后 2 个工作日内补录。
""",
    "onboarding.md": """# 入职流程

## 入职前
HR 在入职日前 3 个工作日发送 offer、材料清单和系统账号开通说明。

## 入职当天
新员工需完成身份核验、劳动合同签署、设备领取和信息安全培训。

## 试用期
试用期目标由直属经理在入职后 7 个工作日内确认，并在第 30、60、90 天进行反馈。
""",
    "engineering_review.md": """# 研发 Code Review 规范

## 评审原则
所有生产代码合并前必须经过至少一名非作者评审。高风险变更需要模块 owner 参与。

## 必查项
评审人应检查正确性、测试覆盖、可维护性、安全风险和回滚方案。

## 时效
普通评审应在 1 个工作日内响应，紧急修复可以先由值班 owner 快速评审，事后补充完整说明。
""",
    "gitlab_handbook_sample.md": """# GitLab Handbook 样例

## 透明协作
公司重要流程、角色职责和决策记录应尽量文档化。异步沟通优先，会议结论需要回写到文档。

## 信息安全
员工需要保护客户数据、访问凭据和内部系统。发现疑似安全事件时，应立即通知安全团队并保留现场证据。
""",
    "sourcegraph_handbook_sample.md": """# Sourcegraph Handbook 样例

## Engineering Process
工程团队通过 RFC、设计评审和迭代计划协作。复杂变更应先写设计文档，再进入实现。

## Product Feedback
产品反馈需要记录来源、影响范围和建议优先级。跨团队问题由 owner 负责推进到关闭。
""",
}


EVAL_ROWS = [
    {
        "question": "实习生差旅报销标准是什么？",
        "route_type": "document_qa",
        "expected_doc": "Travel Reimbursement",
        "expected_terms": ["实习生", "350", "260", "80"],
    },
    {
        "question": "实习生住宿标准是多少？",
        "route_type": "document_qa",
        "expected_doc": "Travel Reimbursement",
        "expected_terms": ["350", "260"],
    },
    {
        "question": "年假制度总结成三条",
        "route_type": "document_qa",
        "expected_doc": "Leave Policy",
        "expected_terms": ["5", "10", "15"],
    },
    {
        "question": "代码评审必须检查哪些内容？",
        "route_type": "document_qa",
        "expected_doc": "Engineering Review",
        "expected_terms": ["正确性", "测试覆盖", "安全风险"],
    },
    {
        "question": "上个月销售额最高的是哪个区域？",
        "route_type": "sql",
        "expected_terms": ["华东区", "1280000"],
    },
    {
        "question": "哪些项目处于 blocked 状态？",
        "route_type": "sql",
        "expected_terms": ["知识库助手", "数据看板"],
    },
    {
        "question": "今天上海天气怎么样？",
        "route_type": "refuse",
        "expected_terms": ["无法回答"],
    },
]


def write_sample_data():
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    settings.eval_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in DOCS.items():
        (settings.raw_dir / filename).write_text(content, encoding="utf-8")
    with (settings.eval_dir / "eval_set.jsonl").open("w", encoding="utf-8") as f:
        for row in EVAL_ROWS:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return settings.data_dir
