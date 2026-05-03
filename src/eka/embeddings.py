from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from eka.schemas import Chunk
from eka.settings import settings


def resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


class EmbeddingIndex:
    def __init__(self, index_dir: Path | None = None) -> None:
        self.index_dir = index_dir or settings.index_dir
        self.index_path = self.index_dir / "faiss.index"
        self.manifest_path = self.index_dir / "embedding_manifest.json"
        self._model = None
        self._faiss = None
        self.index = None
        if self.index_path.exists():
            self._load_faiss_index()

    @property
    def available(self) -> bool:
        return self.index is not None

    def build(self, chunks: list[Chunk]) -> None:
        import faiss

        texts = [chunk_text(chunk) for chunk in chunks]
        vectors = self.encode(texts)
        dim = vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(self.index_path))
        self.manifest_path.write_text(
            json.dumps(
                {
                    "model_name": settings.embedding_model,
                    "chunks": len(chunks),
                    "dimension": dim,
                    "normalize_embeddings": settings.normalize_embeddings,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.index = index

    def search(self, query: str, limit: int) -> list[tuple[int, float]]:
        if not self.available:
            return []
        query_vec = self.encode([query])
        scores, ids = self.index.search(query_vec, limit)
        hits: list[tuple[int, float]] = []
        for idx, score in zip(ids[0], scores[0]):
            if idx < 0:
                continue
            hits.append((int(idx), float(score)))
        return hits

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._load_model()
        vectors = model.encode(
            texts,
            batch_size=settings.embedding_batch_size,
            convert_to_numpy=True,
            normalize_embeddings=settings.normalize_embeddings,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype="float32")

    def _load_model(self):
        if self._model is not None:
            return self._model
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            settings.embedding_model,
            device=resolve_device(settings.embedding_device),
            model_kwargs={"use_safetensors": True},
        )
        return self._model

    def _load_faiss_index(self) -> None:
        import faiss

        self._faiss = faiss
        self.index = faiss.read_index(str(self.index_path))


def chunk_text(chunk: Chunk) -> str:
    return f"{chunk.doc_name}\n{chunk.section}\n{chunk.text}"


def embedding_status(index_dir: Path | None = None) -> dict:
    index_dir = index_dir or settings.index_dir
    manifest = index_dir / "embedding_manifest.json"
    return {
        "faiss_index_exists": (index_dir / "faiss.index").exists(),
        "manifest_exists": manifest.exists(),
        "manifest": json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else None,
    }
