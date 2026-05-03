from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from eka.router import EnterpriseAssistant
from eka.schemas import RouteType
from eka.settings import settings


def load_eval_set(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or settings.eval_dir / "eval_set.jsonl"
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def run_eval(path: Path | None = None, retrieval_strategy: str | None = None) -> dict[str, Any]:
    assistant = EnterpriseAssistant(retrieval_strategy=retrieval_strategy)
    rows = load_eval_set(path)
    details: list[dict[str, Any]] = []
    retrieval_hits = 0
    reciprocal_ranks: list[float] = []
    route_hits = 0
    refusal_hits = 0
    citation_hits = 0
    answer_hits = 0

    for item in rows:
        response = assistant.ask(item["question"], session_id="eval")
        expected_route = item.get("route_type")
        expected_doc = item.get("expected_doc")
        expected_terms = item.get("expected_terms", [])
        if expected_route and response.route_type.value == expected_route:
            route_hits += 1
        expected_doc_rank = _first_doc_rank(response, expected_doc) if expected_doc else None
        if expected_doc_rank:
            retrieval_hits += 1
            reciprocal_ranks.append(1.0 / expected_doc_rank)
        if expected_route == RouteType.REFUSE.value and response.refusal_reason:
            refusal_hits += 1
        if response.citations:
            citation_hits += 1
        if expected_terms and all(term in response.answer for term in expected_terms):
            answer_hits += 1
        details.append(
            {
                "question": item["question"],
                "expected_route": expected_route,
                "actual_route": response.route_type.value,
                "expected_doc": expected_doc,
                "expected_doc_rank": expected_doc_rank,
                "citations": [c.model_dump() for c in response.citations],
                "answer": response.answer,
                "trace": response.trace,
            }
        )

    total = len(rows) or 1
    doc_cases = max(sum(1 for r in rows if r.get("expected_doc")), 1)
    answer_cases = max(sum(1 for r in rows if r.get("expected_terms")), 1)
    return {
        "run_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "retrieval_strategy": retrieval_strategy or "default",
        "total": len(rows),
        "route_accuracy": round(route_hits / total, 3),
        "retrieval_hit_at_k": round(retrieval_hits / doc_cases, 3),
        "mrr": round(sum(reciprocal_ranks) / doc_cases, 3),
        "citation_rate": round(citation_hits / total, 3),
        "refusal_hit_rate": round(refusal_hits / max(sum(1 for r in rows if r.get("route_type") == "refuse"), 1), 3),
        "answer_contains_expected": round(answer_hits / answer_cases, 3),
        "details": details,
    }


def save_eval_run(result: dict[str, Any], reports_dir: Path | None = None) -> tuple[Path, Path]:
    reports_dir = reports_dir or settings.project_root / "reports"
    runs_dir = settings.eval_dir / "runs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = result["run_at"].replace(":", "").replace("-", "")
    strategy = str(result["retrieval_strategy"]).replace("/", "_")
    json_path = runs_dir / f"{stamp}_{strategy}.json"
    md_path = reports_dir / "eval_report.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_report(result), encoding="utf-8")
    return json_path, md_path


def run_eval_compare(strategies: list[str], path: Path | None = None) -> dict[str, Any]:
    results = [run_eval(path=path, retrieval_strategy=strategy) for strategy in strategies]
    best = max(results, key=lambda item: (item["mrr"], item["retrieval_hit_at_k"], item["answer_contains_expected"]))
    return {
        "run_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "strategies": strategies,
        "best_strategy": best["retrieval_strategy"],
        "results": results,
    }


def save_eval_compare(compare: dict[str, Any], reports_dir: Path | None = None) -> tuple[Path, Path]:
    reports_dir = reports_dir or settings.project_root / "reports"
    runs_dir = settings.eval_dir / "runs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = compare["run_at"].replace(":", "").replace("-", "")
    json_path = runs_dir / f"{stamp}_compare.json"
    md_path = reports_dir / "eval_compare.md"
    json_path.write_text(json.dumps(compare, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_compare_report(compare), encoding="utf-8")
    return json_path, md_path


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# Enterprise Knowledge Assistant Eval Report",
        "",
        f"- run_at: `{result['run_at']}`",
        f"- retrieval_strategy: `{result['retrieval_strategy']}`",
        f"- total: `{result['total']}`",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| route_accuracy | {result['route_accuracy']} |",
        f"| retrieval_hit_at_k | {result['retrieval_hit_at_k']} |",
        f"| mrr | {result['mrr']} |",
        f"| citation_rate | {result['citation_rate']} |",
        f"| refusal_hit_rate | {result['refusal_hit_rate']} |",
        f"| answer_contains_expected | {result['answer_contains_expected']} |",
        "",
        "## Cases",
        "",
    ]
    for item in result["details"]:
        lines.append(
            f"- `{item['actual_route']}` {item['question']} "
            f"(expected_route={item['expected_route']}, expected_doc_rank={item['expected_doc_rank']})"
        )
    return "\n".join(lines) + "\n"


def render_compare_report(compare: dict[str, Any]) -> str:
    lines = [
        "# Retrieval Strategy Comparison",
        "",
        f"- run_at: `{compare['run_at']}`",
        f"- best_strategy: `{compare['best_strategy']}`",
        "",
        "| strategy | route_acc | hit@k | mrr | citation_rate | refusal_hit | answer_hit |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in compare["results"]:
        marker = " **best**" if result["retrieval_strategy"] == compare["best_strategy"] else ""
        lines.append(
            f"| {result['retrieval_strategy']}{marker} | {result['route_accuracy']} | "
            f"{result['retrieval_hit_at_k']} | {result['mrr']} | {result['citation_rate']} | "
            f"{result['refusal_hit_rate']} | {result['answer_contains_expected']} |"
        )
    lines.extend(["", "## Case-Level Diff", ""])
    questions = [item["question"] for item in compare["results"][0]["details"]]
    for idx, question in enumerate(questions):
        lines.append(f"### {question}")
        for result in compare["results"]:
            detail = result["details"][idx]
            lines.append(
                f"- `{result['retrieval_strategy']}` route={detail['actual_route']} "
                f"doc_rank={detail['expected_doc_rank']}"
            )
        lines.append("")
    return "\n".join(lines)


def _first_doc_rank(response, expected_doc: str | None) -> int | None:
    if not expected_doc:
        return None
    for ev in response.retrieved_chunks:
        if ev.chunk.doc_name == expected_doc:
            return ev.rank
    return None
