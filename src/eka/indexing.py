from __future__ import annotations

import json
import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer

from eka.chunking import chunk_documents
from eka.ingestion import load_documents
from eka.schemas import Chunk
from eka.settings import settings
from eka.text import tokenize


def save_jsonl(path: Path, rows: list[Chunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(row.model_dump_json(ensure_ascii=False) + "\n")


def load_chunks(index_dir: Path | None = None) -> list[Chunk]:
    index_dir = index_dir or settings.index_dir
    path = index_dir / "chunks.jsonl"
    chunks: list[Chunk] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            chunks.append(Chunk.model_validate_json(line))
    return chunks


def build_index(
    raw_dir: Path | None = None,
    index_dir: Path | None = None,
    with_embeddings: bool = False,
) -> int:
    raw_dir = raw_dir or settings.raw_dir
    index_dir = index_dir or settings.index_dir
    docs = load_documents(raw_dir)
    chunks = chunk_documents(docs, settings.chunk_size, settings.chunk_overlap)
    texts = [f"{c.doc_name} {c.section}\n{c.text}" for c in chunks]

    vectorizer = TfidfVectorizer(tokenizer=tokenize, lowercase=False, min_df=1)
    tfidf = vectorizer.fit_transform(texts)
    tokenized = [tokenize(text) for text in texts]
    bm25 = BM25Okapi(tokenized)

    index_dir.mkdir(parents=True, exist_ok=True)
    save_jsonl(index_dir / "chunks.jsonl", chunks)
    with (index_dir / "tfidf.pkl").open("wb") as f:
        pickle.dump({"vectorizer": vectorizer, "matrix": tfidf}, f)
    with (index_dir / "bm25.pkl").open("wb") as f:
        pickle.dump(bm25, f)
    with (index_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "documents": len(docs),
                "chunks": len(chunks),
                "with_embeddings": with_embeddings,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    if with_embeddings:
        from eka.embeddings import EmbeddingIndex

        EmbeddingIndex(index_dir).build(chunks)
    return len(chunks)
