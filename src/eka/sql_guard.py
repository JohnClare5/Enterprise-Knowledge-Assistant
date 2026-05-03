from __future__ import annotations

import re

from eka.settings import settings


FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|pragma|vacuum)\b", re.I)
TABLE_RE = re.compile(r"\bfrom\s+([A-Za-z_][A-Za-z0-9_]*)|\bjoin\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)


def guard_sql(sql: str) -> tuple[bool, str | None, str | None]:
    normalized = sql.strip().rstrip(";")
    if not normalized:
        return False, "empty_sql", None
    if ";" in normalized:
        return False, "multiple_statements_forbidden", None
    if not normalized.lower().startswith("select"):
        return False, "only_select_allowed", None
    if FORBIDDEN.search(normalized):
        return False, "forbidden_keyword", None
    tables = {a or b for a, b in TABLE_RE.findall(normalized)}
    if not tables:
        return False, "no_table_found", None
    disallowed = sorted(t for t in tables if t not in settings.sql_allowed_tables)
    if disallowed:
        return False, f"disallowed_tables:{','.join(disallowed)}", None
    if " limit " not in f" {normalized.lower()} ":
        normalized = f"{normalized} LIMIT {settings.sql_max_rows}"
    return True, None, normalized

