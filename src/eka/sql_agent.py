from __future__ import annotations

import json
import os

import httpx

from eka.settings import settings
from eka.sql_guard import guard_sql


SCHEMA_TEXT = """
Tables:
1. reimbursement_records(id, month, department, employee_type, amount)
2. sales_summary(id, month, region, sales_amount)
3. project_status(id, project_name, owner_department, status, updated_at)

Notes:
- 当前演示数据中，“上个月”默认指 2026-04。
- 只能生成 SELECT 查询。
- 如果问题缺少指标、时间范围或维度，返回 needs_clarification=true。
"""


def generate_sql_with_deepseek(question: str) -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return {"ok": False, "error": "missing_deepseek_api_key"}
    prompt = f"""你是企业数据查询助手。请根据 schema 将用户问题转为只读 SQL。
必须只输出 JSON，不要输出 Markdown。

JSON schema:
{{
  "is_sql": true,
  "sql": "SELECT ...",
  "reason": "...",
  "needs_clarification": false
}}

{SCHEMA_TEXT}

用户问题：{question}
"""
    try:
        with httpx.Client(timeout=45) as client:
            resp = client.post(
                f"{os.getenv('DEEPSEEK_BASE_URL', settings.deepseek_base_url).rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": os.getenv("DEEPSEEK_MODEL", settings.deepseek_model),
                    "messages": [
                        {"role": "system", "content": "你只输出严格 JSON。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 500,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            payload = json.loads(content)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}

    if payload.get("needs_clarification"):
        return {"ok": True, "needs_clarification": True, "reason": payload.get("reason")}
    sql = str(payload.get("sql", ""))
    ok, reason, guarded_sql = guard_sql(sql)
    return {
        "ok": ok,
        "needs_clarification": False,
        "sql": guarded_sql,
        "raw_sql": sql,
        "reason": payload.get("reason"),
        "guard_reason": reason,
    }

