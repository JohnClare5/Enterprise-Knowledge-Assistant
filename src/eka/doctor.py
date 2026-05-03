from __future__ import annotations

import os

from eka.embeddings import embedding_status
from eka.settings import settings


def run_doctor() -> dict:
    index_dir = settings.index_dir
    return {
        "data_raw_exists": settings.raw_dir.exists(),
        "sqlite_exists": settings.sqlite_path.exists(),
        "chunks_exists": (index_dir / "chunks.jsonl").exists(),
        "tfidf_exists": (index_dir / "tfidf.pkl").exists(),
        "bm25_exists": (index_dir / "bm25.pkl").exists(),
        "embedding": embedding_status(index_dir),
        "deepseek_key_exists": bool(os.getenv("DEEPSEEK_API_KEY")),
        "hf_endpoint": os.getenv("HF_ENDPOINT"),
        "retrieval_strategy": settings.retrieval_strategy,
        "embedding_model": settings.embedding_model,
        "rerank_model": settings.rerank_model,
        "sql_mode": settings.sql_mode,
    }

