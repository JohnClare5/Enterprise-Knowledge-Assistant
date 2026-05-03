from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "default.yaml"


def proxied(url: str, proxy_prefix: str) -> str:
    if not proxy_prefix or url.startswith(proxy_prefix):
        return url
    return proxy_prefix + url


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def fetch(name: str | None, limit: int | None, force: bool) -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    proxy_prefix = config["data_sources"]["git_proxy_prefix"]
    repos = config["data_sources"]["handbook_repos"]
    selected = {name: repos[name]} if name else repos

    for repo_name, spec in selected.items():
        target = ROOT / spec["target_dir"]
        if force and target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    proxied(spec["repo_url"], proxy_prefix),
                    str(target),
                ]
            )
        else:
            run(["git", "pull", "--ff-only"], cwd=target)
        if limit:
            prune_markdown(target, limit)
        print(f"Fetched {repo_name} into {target}")


def prune_markdown(root: Path, limit: int) -> None:
    md_files = sorted(root.rglob("*.md"))
    keep = set(md_files[:limit])
    for path in md_files[limit:]:
        path.unlink()
    print(f"Kept {len(keep)} Markdown files under {root}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public handbook repositories.")
    parser.add_argument("--name", choices=["gitlab_handbook", "sourcegraph_handbook"])
    parser.add_argument("--limit", type=int, help="Keep only the first N Markdown files for demos.")
    parser.add_argument("--force", action="store_true", help="Delete target directories before clone.")
    args = parser.parse_args()
    fetch(args.name, args.limit, args.force)


if __name__ == "__main__":
    main()

