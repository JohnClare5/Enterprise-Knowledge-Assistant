from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel
from dotenv import load_dotenv
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseModel):
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    index_dir: Path = PROJECT_ROOT / "data" / "indexes"
    structured_dir: Path = PROJECT_ROOT / "data" / "structured"
    eval_dir: Path = PROJECT_ROOT / "data" / "eval"
    sqlite_path: Path = PROJECT_ROOT / "data" / "structured" / "business.sqlite"
    chunk_size: int = 900
    chunk_overlap: int = 120
    top_k: int = 5
    dense_top_k: int = 12
    bm25_top_k: int = 12
    vector_top_k: int = 20
    rrf_k: int = 60
    rerank: bool = True
    retrieval_strategy: str = "hybrid_rerank"
    max_chunks_per_doc: int = 3
    generation_mode: str = "extractive"
    min_grounding_score: float = 0.18
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_max_tokens: int = 800
    llm_temperature: float = 0.0
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "auto"
    embedding_batch_size: int = 32
    normalize_embeddings: bool = True
    rerank_mode: str = "cross_encoder"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_device: str = "auto"
    rerank_top_n: int = 20
    sql_mode: str = "llm_guarded"
    sql_max_rows: int = 20
    sql_allowed_tables: list[str] = [
        "reimbursement_records",
        "sales_summary",
        "project_status",
    ]
    git_proxy_prefix: str = "https://gh.llkk.cc/"
    config: dict[str, Any] = {}


def load_settings() -> Settings:
    config_path = PROJECT_ROOT / "config" / "default.yaml"
    if not config_path.exists():
        return Settings()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    retrieval = payload.get("retrieval", {})
    generation = payload.get("generation", {})
    data_sources = payload.get("data_sources", {})
    embedding = payload.get("embedding", {})
    rerank = payload.get("rerank", {})
    sql = payload.get("sql", {})
    return Settings(
        top_k=int(retrieval.get("final_top_k", Settings().top_k)),
        dense_top_k=int(retrieval.get("dense_top_k", Settings().dense_top_k)),
        bm25_top_k=int(retrieval.get("bm25_top_k", Settings().bm25_top_k)),
        vector_top_k=int(retrieval.get("vector_top_k", Settings().vector_top_k)),
        rrf_k=int(retrieval.get("rrf_k", Settings().rrf_k)),
        rerank=bool(retrieval.get("rerank", Settings().rerank)),
        retrieval_strategy=str(retrieval.get("strategy", Settings().retrieval_strategy)),
        max_chunks_per_doc=int(retrieval.get("max_chunks_per_doc", Settings().max_chunks_per_doc)),
        generation_mode=str(generation.get("mode", Settings().generation_mode)),
        min_grounding_score=float(
            generation.get("min_grounding_score", Settings().min_grounding_score)
        ),
        deepseek_base_url=str(generation.get("deepseek_base_url", Settings().deepseek_base_url)),
        deepseek_model=str(generation.get("deepseek_model", Settings().deepseek_model)),
        llm_max_tokens=int(generation.get("max_tokens", Settings().llm_max_tokens)),
        llm_temperature=float(generation.get("temperature", Settings().llm_temperature)),
        embedding_model=str(embedding.get("model_name", Settings().embedding_model)),
        embedding_device=str(embedding.get("device", Settings().embedding_device)),
        embedding_batch_size=int(embedding.get("batch_size", Settings().embedding_batch_size)),
        normalize_embeddings=bool(
            embedding.get("normalize_embeddings", Settings().normalize_embeddings)
        ),
        rerank_mode=str(rerank.get("mode", Settings().rerank_mode)),
        rerank_model=str(rerank.get("model_name", Settings().rerank_model)),
        rerank_device=str(rerank.get("device", Settings().rerank_device)),
        rerank_top_n=int(rerank.get("top_n", Settings().rerank_top_n)),
        sql_mode=str(sql.get("mode", Settings().sql_mode)),
        sql_max_rows=int(sql.get("max_rows", Settings().sql_max_rows)),
        sql_allowed_tables=list(sql.get("allowed_tables", Settings().sql_allowed_tables)),
        git_proxy_prefix=str(data_sources.get("git_proxy_prefix", Settings().git_proxy_prefix)),
        config=payload,
    )


settings = load_settings()
