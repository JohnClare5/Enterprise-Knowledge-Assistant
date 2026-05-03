from __future__ import annotations

import time

from eka.schemas import Chunk
from eka.settings import settings
from eka.text import tokenize


class RerankResult:
    def __init__(self, hits: list[tuple[int, float]], trace: dict) -> None:
        self.hits = hits
        self.trace = trace


class CrossEncoderReranker:
    def __init__(self) -> None:
        self._model = None
        self.error: str | None = None

    def rerank(
        self,
        query: str,
        hits: list[tuple[int, float]],
        chunks: list[Chunk],
    ) -> RerankResult:
        if not hits:
            return RerankResult([], {"rerank_mode": "none", "candidate_count": 0})
        if settings.rerank_mode != "cross_encoder":
            return lexical_rerank(query, hits, chunks)
        started = time.perf_counter()
        try:
            model = self._load_model()
            top_hits = hits[: settings.rerank_top_n]
            pairs = [(query, f"{chunks[idx].section}\n{chunks[idx].text}") for idx, _ in top_hits]
            scores = model.predict(pairs, show_progress_bar=False)
            score_map = {idx: float(score) for (idx, _), score in zip(top_hits, scores)}
            reranked = sorted(
                [(idx, score_map.get(idx, score)) for idx, score in hits],
                key=lambda item: item[1],
                reverse=True,
            )
            return RerankResult(
                reranked,
                {
                    "rerank_mode": "cross_encoder",
                    "rerank_model": settings.rerank_model,
                    "candidate_count": len(top_hits),
                    "rerank_latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "rerank_fallback": False,
                },
            )
        except Exception as exc:
            self.error = str(exc)
            result = lexical_rerank(query, hits, chunks)
            result.trace.update(
                {
                    "rerank_fallback": True,
                    "rerank_error": self.error[:300],
                    "requested_rerank_model": settings.rerank_model,
                }
            )
            return result

    def _load_model(self):
        if self._model is not None:
            return self._model
        from sentence_transformers import CrossEncoder
        from eka.embeddings import resolve_device

        self._model = CrossEncoder(
            settings.rerank_model,
            device=resolve_device(settings.rerank_device),
            model_kwargs={"use_safetensors": True},
        )
        return self._model


def lexical_rerank(query: str, hits: list[tuple[int, float]], chunks: list[Chunk]) -> RerankResult:
    query_terms = set(tokenize(query))
    reranked: list[tuple[int, float]] = []
    for idx, score in hits:
        chunk = chunks[idx]
        text_terms = set(tokenize(f"{chunk.doc_name} {chunk.section} {chunk.text}"))
        coverage = len(query_terms & text_terms) / max(len(query_terms), 1)
        title_bonus = 0.08 if query_terms & set(tokenize(chunk.section)) else 0.0
        reranked.append((idx, score + coverage * 0.2 + title_bonus))
    return RerankResult(
        sorted(reranked, key=lambda item: item[1], reverse=True),
        {
            "rerank_mode": "lexical",
            "candidate_count": len(hits),
            "rerank_fallback": settings.rerank_mode == "cross_encoder",
        },
    )
