from __future__ import annotations

import os
import re

import httpx

from eka.grounding import citation_precision, lexical_support, unsupported_numbers
from eka.schemas import AssistantResponse, Citation, Evidence, RouteType
from eka.settings import settings
from eka.text import tokenize


ANSWER_PROMPT = """你是企业知识助手。只能依据给定证据回答。
如果证据不足，明确说不知道。回答要简洁，关键结论必须在句末引用来源编号，例如 [1]。
不要使用证据之外的事实、数字、人名、政策或推断。

问题：{question}

证据：
{context}
"""


def _context(evidences: list[Evidence]) -> str:
    lines = []
    for idx, ev in enumerate(evidences, 1):
        c = ev.chunk
        lines.append(f"[{idx}] {c.doc_name} / {c.section} / {c.source}\n{c.text}")
    return "\n\n".join(lines)


def _grounding_score(question: str, evidences: list[Evidence]) -> float:
    q_terms = set(tokenize(question))
    if not q_terms or not evidences:
        return 0.0
    evidence_terms = set()
    for ev in evidences[:3]:
        evidence_terms.update(tokenize(f"{ev.chunk.section} {ev.chunk.text}"))
    lexical = len(q_terms & evidence_terms) / len(q_terms)
    retrieval = max((ev.score for ev in evidences), default=0.0)
    return min(1.0, lexical * 0.7 + retrieval * 3.0)


def citations_from(evidences: list[Evidence], limit: int = 3) -> list[Citation]:
    seen: set[str] = set()
    citations: list[Citation] = []
    for ev in evidences:
        key = ev.chunk.chunk_id
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            Citation(
                doc_name=ev.chunk.doc_name,
                section=ev.chunk.section,
                source=ev.chunk.source,
                chunk_id=ev.chunk.chunk_id,
                source_type=ev.chunk.metadata.get("source_type"),
                url=ev.chunk.metadata.get("url"),
            )
        )
        if len(citations) >= limit:
            break
    return citations


def answer_from_evidence(question: str, evidences: list[Evidence]) -> AssistantResponse:
    score = _grounding_score(question, evidences)
    if score < settings.min_grounding_score:
        return AssistantResponse(
            answer="我不知道。当前知识库中没有足够证据回答这个问题。",
            route_type=RouteType.REFUSE,
            retrieved_chunks=evidences,
            refusal_reason="insufficient_evidence",
            confidence=score,
            grounded=False,
        )

    used_evidences = evidences[:3]
    llm_answer = _try_llm_answer(question, used_evidences)
    if llm_answer:
        answer = llm_answer
    else:
        answer, used_evidences = _compose_answer(question, evidences)

    unsupported = unsupported_numbers(answer, used_evidences)
    support = lexical_support(answer, used_evidences)
    cite_precision = citation_precision(answer, used_evidences)

    return AssistantResponse(
        answer=answer,
        route_type=RouteType.DOCUMENT_QA,
        citations=citations_from(used_evidences),
        retrieved_chunks=evidences,
        confidence=score,
        grounded=not unsupported and support >= 0.35,
        trace={
            "unsupported_numbers": unsupported,
            "lexical_support": round(support, 3),
            "citation_precision": round(cite_precision, 3),
            "used_chunk_ids": [ev.chunk.chunk_id for ev in used_evidences],
        },
    )


def _try_llm_answer(question: str, evidences: list[Evidence]) -> str | None:
    mode = os.getenv("EKA_GENERATION_MODE", settings.generation_mode).lower()
    if mode == "deepseek":
        return _try_deepseek_answer(question, evidences)
    if mode == "openai":
        return _try_openai_answer(question, evidences)
    return None


def _try_deepseek_answer(question: str, evidences: list[Evidence]) -> str | None:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("DEEPSEEK_BASE_URL", settings.deepseek_base_url).rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", settings.deepseek_model)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的企业知识助手，只能基于用户提供的证据回答。"},
            {
                "role": "user",
                "content": ANSWER_PROMPT.format(question=question, context=_context(evidences)),
            },
        ],
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }
    try:
        with httpx.Client(timeout=45) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def _try_openai_answer(question: str, evidences: list[Evidence]) -> str | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_template(ANSWER_PROMPT)
        llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)
        return (prompt | llm).invoke({"question": question, "context": _context(evidences)}).content
    except Exception:
        return None


def _compose_answer(question: str, evidences: list[Evidence]) -> tuple[str, list[Evidence]]:
    relevant = _select_relevant(evidences, limit=3)
    if "总结" in question or "三条" in question or "3条" in question:
        bullets = _best_sentences(question, relevant, limit=3)
        lines = [f"{idx}. {sentence} [{_rank_for_sentence(sentence, relevant)}]" for idx, sentence in enumerate(bullets, 1)]
        return "\n".join(lines), _used_evidences(bullets, relevant)

    if any(word in question for word in ("多少", "标准", "金额", "天", "几天", "哪些内容", "检查哪些")):
        limit = 1 if any(word in question for word in ("住宿", "多少")) else 2
        sentences = _best_sentences(question, relevant, limit=limit)
        answer = " ".join(
            f"{sentence} [{_rank_for_sentence(sentence, relevant)}]" for sentence in sentences
        )
        return answer, _used_evidences(sentences, relevant)

    sentences = _best_sentences(question, relevant, limit=2)
    answer = " ".join(f"{sentence} [{_rank_for_sentence(sentence, relevant)}]" for sentence in sentences)
    return answer, _used_evidences(sentences, relevant)


def _select_relevant(evidences: list[Evidence], limit: int) -> list[Evidence]:
    selected: list[Evidence] = []
    seen_docs: dict[str, int] = {}
    for ev in evidences:
        count = seen_docs.get(ev.chunk.doc_id, 0)
        if count >= 2:
            continue
        selected.append(ev)
        seen_docs[ev.chunk.doc_id] = count + 1
        if len(selected) >= limit:
            break
    return selected or evidences[:limit]


def _best_sentences(question: str, evidences: list[Evidence], limit: int) -> list[str]:
    q_terms = set(tokenize(question))
    candidates: list[tuple[float, str]] = []
    for ev in evidences:
        for sentence in _sentences(ev.chunk.text):
            terms = set(tokenize(sentence))
            overlap = len(q_terms & terms) / max(len(q_terms), 1)
            number_bonus = 0.15 if re.search(r"\d", sentence) and re.search(r"多少|标准|天|金额", question) else 0
            exact_bonus = 0.25 if any(term in sentence for term in q_terms if len(term) > 1) else 0
            title_bonus = 0.1 if q_terms & set(tokenize(ev.chunk.section)) else 0
            candidates.append((overlap + exact_bonus + number_bonus + title_bonus + ev.score * 0.2, sentence))
    ordered = [sentence for _, sentence in sorted(candidates, key=lambda item: item[0], reverse=True)]
    deduped: list[str] = []
    for sentence in ordered:
        if sentence not in deduped:
            deduped.append(sentence)
        if len(deduped) >= limit:
            break
    return deduped


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])\s*|\n+", text.replace("\r", "\n"))
    return [part.strip(" -\t") for part in parts if len(part.strip()) >= 8]


def _rank_for_sentence(sentence: str, evidences: list[Evidence]) -> int:
    for ev in evidences:
        if sentence in ev.chunk.text:
            return ev.rank
    return evidences[0].rank if evidences else 1


def _used_evidences(sentences: list[str], evidences: list[Evidence]) -> list[Evidence]:
    used: list[Evidence] = []
    for sentence in sentences:
        for ev in evidences:
            if sentence in ev.chunk.text and ev not in used:
                used.append(ev)
    return used or evidences[:1]
