from __future__ import annotations

import hashlib
from pathlib import Path

from eka.schemas import RawDocument


SUPPORTED_SUFFIXES = {".md", ".txt"}


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def load_documents(raw_dir: Path) -> list[RawDocument]:
    docs: list[RawDocument] = []
    for path in sorted(raw_dir.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        source = path.as_posix()
        doc_id = stable_id(source)
        rel_path = path.relative_to(raw_dir).as_posix()
        source_type = _source_type(rel_path)
        url = _source_url(rel_path, source_type)
        docs.append(
            RawDocument(
                doc_id=doc_id,
                doc_name=path.stem.replace("_", " ").title(),
                source=source,
                text=text,
                metadata={
                    "suffix": path.suffix.lower(),
                    "relative_path": rel_path,
                    "source_type": source_type,
                    "url": url,
                },
            )
        )
    return docs


def _source_type(rel_path: str) -> str:
    if rel_path.startswith("prepared/gitlab_handbook/"):
        return "gitlab_handbook"
    if rel_path.startswith("prepared/sourcegraph_handbook/"):
        return "sourcegraph_handbook"
    if rel_path.startswith("external/gitlab_handbook/"):
        return "gitlab_handbook"
    if rel_path.startswith("external/sourcegraph_handbook/"):
        return "sourcegraph_handbook"
    return "mock_policy"


def _source_url(rel_path: str, source_type: str) -> str:
    if source_type == "gitlab_handbook":
        clean = rel_path.removeprefix("external/gitlab_handbook/").removeprefix(
            "prepared/gitlab_handbook/"
        )
        return "https://handbook.gitlab.com/" + clean
    if source_type == "sourcegraph_handbook":
        clean = rel_path.removeprefix("external/sourcegraph_handbook/").removeprefix(
            "prepared/sourcegraph_handbook/"
        )
        return "https://handbook.sourcegraph.com/" + clean
    return rel_path
