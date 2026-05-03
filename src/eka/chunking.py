from __future__ import annotations

import hashlib
import re

from eka.schemas import Chunk, RawDocument


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _hash(*parts: str) -> str:
    return hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:20]


def split_by_headings(text: str) -> list[tuple[str, str]]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("Untitled", text.strip())] if text.strip() else []

    sections: list[tuple[str, str]] = []
    heading_stack: list[tuple[int, str]] = []
    for idx, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        heading_stack = [(lvl, name) for lvl, name in heading_stack if lvl < level]
        heading_stack.append((level, title))
        heading_path = " > ".join(name for _, name in heading_stack)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((heading_path, body))
    return sections


def chunk_documents(
    docs: list[RawDocument],
    chunk_size: int = 900,
    chunk_overlap: int = 120,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        for section, body in split_by_headings(doc.text):
            pieces = split_text(body, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            for i, piece in enumerate(pieces):
                chunk_id = _hash(doc.doc_id, section, str(i), piece[:80])
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        doc_id=doc.doc_id,
                        doc_name=doc.doc_name,
                        section=section,
                        source=doc.source,
                        text=piece.strip(),
                        metadata={**doc.metadata, "section_index": i, "heading_path": section},
                    )
                )
    return chunks


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            pieces.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
        else:
            for start in range(0, len(paragraph), max(chunk_size - chunk_overlap, 1)):
                pieces.append(paragraph[start : start + chunk_size])
            current = ""
    if current:
        pieces.append(current)
    return pieces
