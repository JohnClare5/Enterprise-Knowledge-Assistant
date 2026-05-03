from __future__ import annotations

import re


TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


def normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())

