from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CONFIG = ROOT / "config" / "default.yaml"
MANIFEST = RAW / "external_manifest.json"

KEEP_HINTS = (
    "engineering",
    "security",
    "people",
    "handbook",
    "product",
    "team",
    "communication",
    "process",
    "onboarding",
    "benefits",
    "finance",
)
SKIP_HINTS = (
    "node_modules",
    ".github",
    "redirect",
    "changelog",
    "index.md",
    "readme.md",
    "license",
)


def should_keep(path: Path, text: str, min_chars: int) -> bool:
    rel = path.as_posix().lower()
    if any(hint in rel for hint in SKIP_HINTS):
        return False
    if len(text.strip()) < min_chars:
        return False
    return any(hint in rel for hint in KEEP_HINTS)


def prepare(limit: int | None, min_chars: int) -> list[dict]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    repos = config["data_sources"]["handbook_repos"]
    manifest: list[dict] = []

    for name, spec in repos.items():
        source_root = ROOT / spec["target_dir"]
        prepared_root = RAW / "prepared" / name
        if prepared_root.exists():
            shutil.rmtree(prepared_root)
        prepared_root.mkdir(parents=True, exist_ok=True)

        kept = 0
        scanned = 0
        for path in sorted(source_root.rglob("*.md")) if source_root.exists() else []:
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            if not should_keep(path.relative_to(source_root), text, min_chars):
                continue
            rel = path.relative_to(source_root)
            target = prepared_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_front_matter(name, spec, rel) + text, encoding="utf-8")
            kept += 1
            if limit and kept >= limit:
                break
        manifest.append(
            {
                "name": name,
                "source_type": spec["source_type"],
                "source_root": source_root.as_posix(),
                "prepared_root": prepared_root.as_posix(),
                "scanned_markdown": scanned,
                "kept_markdown": kept,
                "limit": limit,
                "min_chars": min_chars,
            }
        )

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _front_matter(name: str, spec: dict, rel: Path) -> str:
    url = spec["url_prefix"].rstrip("/") + "/" + rel.as_posix()
    return f"# External Source Metadata\n\nsource_name: {name}\nsource_url: {url}\n\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter and prepare fetched handbook Markdown.")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--min-chars", type=int, default=500)
    args = parser.parse_args()
    manifest = prepare(limit=args.limit, min_chars=args.min_chars)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

