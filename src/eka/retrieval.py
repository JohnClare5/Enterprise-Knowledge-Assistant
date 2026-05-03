from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from eka.embeddings import EmbeddingIndex
from eka.indexing import load_chunks
from eka.memory import memory
from eka.rerank import CrossEncoderReranker, lexical_rerank
from eka.schemas import Chunk, Evidence
from eka.settings import settings
from eka.text import normalize_question, tokenize


class HybridRetriever:
    def __init__(self, index_dir: Path | None = None, strategy: str | None = None) -> None:
        self.index_dir = index_dir or settings.index_dir
        self.strategy = strategy or settings.retrieval_strategy
        self.chunks = load_chunks(self.index_dir)
        with (self.index_dir / "tfidf.pkl").open("rb") as f:
            payload = pickle.load(f)
        with (self.index_dir / "bm25.pkl").open("rb") as f:
            self.bm25 = pickle.load(f)
        self.vectorizer = payload["vectorizer"]
        self.matrix = payload["matrix"]
        self.embedding_index = self._try_embedding_index()
        self.reranker = CrossEncoderReranker()
        self.last_trace: dict = {}

    def rewrite_query(self, question: str, session_id: str = "default") -> str:
        q = normalize_question(question)
        pronouns = ("那", "这个", "该", "上述", "它", "他们", "其")
        if q.startswith(pronouns) or len(tokenize(q)) <= 8:
            topic = memory.topic_hint(session_id)
            if topic and topic not in q:
                return f"{topic} {q}"
        return q

    def retrieve(self, question: str, session_id: str = "default", top_k: int | None = None) -> list[Evidence]:
        top_k = top_k or settings.top_k
        query = self.rewrite_query(question, session_id)
        dense_hits = self._dense(query, limit=max(settings.dense_top_k, top_k))
        keyword_hits = self._keyword(query, limit=max(settings.bm25_top_k, top_k))
        vector_hits = self._vector(query, limit=max(settings.vector_top_k, top_k))
        method = ""
        trace = {
            "requested_strategy": self.strategy,
            "vector_available": self.embedding_index is not None and self.embedding_index.available,
            "embedding_model": settings.embedding_model,
        }

        if self.strategy in {"tfidf", "dense"}:
            hits = dense_hits
            method = "tfidf"
        elif self.strategy == "vector":
            hits = vector_hits or dense_hits
            method = "vector" if vector_hits else "tfidf_fallback"
        elif self.strategy in {"bm25", "keyword"}:
            hits = keyword_hits
            method = "bm25"
        elif self.strategy in {"vector_bm25", "vector_bm25_rerank"}:
            if vector_hits:
                hits = self._rrf([vector_hits, keyword_hits], k=settings.rrf_k)
                method = "vector_bm25_rrf"
            else:
                hits = self._rrf([dense_hits, keyword_hits], k=settings.rrf_k)
                method = "hybrid_rrf_embedding_fallback"
                trace["fallback_reason"] = "faiss index missing or embedding load failed"
        else:
            hits = self._rrf([dense_hits, keyword_hits], k=settings.rrf_k)
            method = "hybrid_rrf"

        should_rerank = self.strategy in {"hybrid_rerank", "vector_bm25_rerank"} or (
            self.strategy == "hybrid" and settings.rerank
        )
        if should_rerank:
            if self.strategy == "vector_bm25_rerank" and settings.rerank_mode == "cross_encoder":
                reranked = self.reranker.rerank(query, hits, self.chunks)
                hits = reranked.hits
                trace.update(reranked.trace)
                method += "_cross_rerank" if not reranked.trace.get("rerank_fallback") else "_lexical_rerank"
            else:
                reranked = lexical_rerank(query, hits, self.chunks)
                hits = reranked.hits
                trace.update(reranked.trace)
                method += "_rerank"

        hits = self._limit_doc_repetition(hits)
        self.last_trace = trace
        return [
            Evidence(
                chunk=self.chunks[idx],
                score=float(score),
                rank=rank + 1,
                retrieval_method=method,
            )
            for rank, (idx, score) in enumerate(hits[:top_k])
        ]

    def _dense(self, query: str, limit: int) -> list[tuple[int, float]]:
        qv = self.vectorizer.transform([query])
        sims = cosine_similarity(qv, self.matrix).ravel()
        order = np.argsort(sims)[::-1][:limit]
        return [(int(i), float(sims[i])) for i in order if sims[i] > 0]

    def _keyword(self, query: str, limit: int) -> list[tuple[int, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        order = np.argsort(scores)[::-1][:limit]
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0]

    def _vector(self, query: str, limit: int) -> list[tuple[int, float]]:
        if not self.embedding_index or not self.embedding_index.available:
            return []
        try:
            return self.embedding_index.search(query, limit)
        except Exception as exc:
            self.last_trace["vector_error"] = str(exc)[:300]
            return []

    def _rrf(self, ranked_lists: list[list[tuple[int, float]]], k: int = 60) -> list[tuple[int, float]]:
        scores: dict[int, float] = {}
        for hits in ranked_lists:
            for rank, (idx, score) in enumerate(hits):
                scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1) + min(score, 1.0) * 0.01
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    def _rerank(self, query: str, hits: list[tuple[int, float]]) -> list[tuple[int, float]]:
        query_terms = set(tokenize(query))
        reranked: list[tuple[int, float]] = []
        for idx, score in hits:
            chunk: Chunk = self.chunks[idx]
            text_terms = set(tokenize(f"{chunk.doc_name} {chunk.section} {chunk.text}"))
            coverage = len(query_terms & text_terms) / max(len(query_terms), 1)
            title_bonus = 0.08 if query_terms & set(tokenize(chunk.section)) else 0.0
            reranked.append((idx, score + coverage * 0.2 + title_bonus))
        return sorted(reranked, key=lambda item: item[1], reverse=True)

    def _try_embedding_index(self) -> EmbeddingIndex | None:
        try:
            index = EmbeddingIndex(self.index_dir)
            return index if index.available else None
        except Exception:
            return None

    def _limit_doc_repetition(self, hits: list[tuple[int, float]]) -> list[tuple[int, float]]:
        if settings.max_chunks_per_doc <= 0:
            return hits
        counts: dict[str, int] = {}
        filtered: list[tuple[int, float]] = []
        for idx, score in hits:
            doc_id = self.chunks[idx].doc_id
            if counts.get(doc_id, 0) >= settings.max_chunks_per_doc:
                continue
            counts[doc_id] = counts.get(doc_id, 0) + 1
            filtered.append((idx, score))
        return filtered
