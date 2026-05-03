from __future__ import annotations

import re

from eka.schemas import Evidence
from eka.text import tokenize


NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def evidence_text(evidences: list[Evidence]) -> str:
    return "\n".join(ev.chunk.text for ev in evidences)


def unsupported_numbers(answer: str, evidences: list[Evidence]) -> list[str]:
    source = evidence_text(evidences)
    cleaned = re.sub(r"\[\d+\]", "", answer)
    cleaned = re.sub(r"(?m)^\s*\d+\.\s*", "", cleaned)
    return sorted({num for num in NUMBER_RE.findall(cleaned) if num not in source})


def citation_precision(answer: str, evidences: list[Evidence]) -> float:
    cited = {int(i) for i in re.findall(r"\[(\d+)\]", answer)}
    if not cited:
        return 0.0
    valid = {ev.rank for ev in evidences}
    return len(cited & valid) / len(cited)


def lexical_support(answer: str, evidences: list[Evidence]) -> float:
    answer_terms = set(tokenize(answer))
    if not answer_terms:
        return 0.0
    source_terms = set(tokenize(evidence_text(evidences)))
    return len(answer_terms & source_terms) / len(answer_terms)
