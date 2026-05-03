from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from eka.schemas import AssistantResponse, RouteType
from eka.settings import settings
from eka.sql_agent import generate_sql_with_deepseek
from eka.sql_guard import guard_sql


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reimbursement_records (
  id INTEGER PRIMARY KEY,
  month TEXT NOT NULL,
  department TEXT NOT NULL,
  employee_type TEXT NOT NULL,
  amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sales_summary (
  id INTEGER PRIMARY KEY,
  month TEXT NOT NULL,
  region TEXT NOT NULL,
  sales_amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS project_status (
  id INTEGER PRIMARY KEY,
  project_name TEXT NOT NULL,
  owner_department TEXT NOT NULL,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


SEED_SQL = """
DELETE FROM reimbursement_records;
DELETE FROM sales_summary;
DELETE FROM project_status;
INSERT INTO reimbursement_records(month, department, employee_type, amount) VALUES
('2026-04', '研发部', '正式员工', 32800),
('2026-04', '销售部', '正式员工', 42600),
('2026-04', '市场部', '实习生', 8900),
('2026-03', '研发部', '实习生', 5200);
INSERT INTO sales_summary(month, region, sales_amount) VALUES
('2026-04', '华东区', 1280000),
('2026-04', '华南区', 980000),
('2026-04', '华北区', 1100000),
('2026-03', '华东区', 1020000);
INSERT INTO project_status(project_name, owner_department, status, updated_at) VALUES
('知识库助手', 'AI平台部', 'blocked', '2026-04-29'),
('CRM改造', '业务平台部', 'active', '2026-04-30'),
('数据看板', '数据部', 'blocked', '2026-04-28');
"""


def init_sqlite(path: Path | None = None) -> Path:
    path = path or settings.sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_SQL)
    return path


def question_to_sql(question: str) -> str | None:
    q = question.lower()
    if "报销" in question and ("最多" in question or "最高" in question):
        return """
SELECT department, SUM(amount) AS total_amount
FROM reimbursement_records
WHERE month = '2026-04'
GROUP BY department
ORDER BY total_amount DESC
LIMIT 1;
""".strip()
    if "销售额" in question and "最高" in question:
        return """
SELECT region, sales_amount
FROM sales_summary
WHERE month = '2026-04'
ORDER BY sales_amount DESC
LIMIT 1;
""".strip()
    if "华东" in question and "销售额" in question:
        return """
SELECT region, sales_amount
FROM sales_summary
WHERE month = '2026-04' AND region = '华东区';
""".strip()
    if "blocked" in q or "阻塞" in question:
        return """
SELECT project_name, owner_department, updated_at
FROM project_status
WHERE status = 'blocked'
ORDER BY updated_at DESC;
""".strip()
    return None


def run_sql_question(question: str, db_path: Path | None = None) -> AssistantResponse:
    db_path = db_path or settings.sqlite_path
    trace: dict[str, Any] = {"sql_mode": settings.sql_mode}
    sql = None
    if settings.sql_mode == "llm_guarded":
        generated = generate_sql_with_deepseek(question)
        trace["llm_sql"] = generated
        if generated.get("ok") and generated.get("needs_clarification"):
            return AssistantResponse(
                answer="这个数据查询还需要澄清具体指标、时间范围或维度。",
                route_type=RouteType.CLARIFY,
                needs_clarification=True,
                refusal_reason="sql_needs_clarification",
                trace=trace,
            )
        if generated.get("ok") and generated.get("sql"):
            sql = generated["sql"]
    if not sql:
        sql = question_to_sql(question)
    if not sql:
        return AssistantResponse(
            answer="这个数据查询还需要澄清具体指标、时间范围或维度。",
            route_type=RouteType.CLARIFY,
            needs_clarification=True,
            refusal_reason="unsupported_sql_question",
            trace=trace,
        )
    ok, guard_reason, guarded_sql = guard_sql(sql)
    trace.update({"guard_passed": ok, "guard_reason": guard_reason, "generated_sql": sql})
    if not ok or not guarded_sql:
        return AssistantResponse(
            answer="该结构化查询未通过安全校验，无法执行。",
            route_type=RouteType.REFUSE,
            refusal_reason=guard_reason or "sql_guard_failed",
            trace=trace,
        )
    sql = guarded_sql
    rows: list[dict[str, Any]]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(sql).fetchall()]
    if not rows:
        answer = "结构化数据库中没有查到匹配结果。"
    else:
        answer = f"查询结果：{rows}"
    return AssistantResponse(
        answer=answer,
        route_type=RouteType.SQL,
        confidence=0.85,
        grounded=True,
        sql=sql,
        raw_result=rows,
        trace={**trace, "rows": len(rows)},
    )
