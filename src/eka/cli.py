from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich import print

from eka.evaluation import run_eval, run_eval_compare, save_eval_compare, save_eval_run
from eka.doctor import run_doctor
from eka.indexing import build_index
from eka.router import EnterpriseAssistant
from eka.sample_data import write_sample_data
from eka.sql_tool import init_sqlite

app = typer.Typer(help="Enterprise Knowledge Assistant CLI")


@app.command()
def init_data() -> None:
    """Write sample policy documents, SQLite rows, and eval set."""
    root = write_sample_data()
    db = init_sqlite()
    print(f"[green]Sample data written to {root}[/green]")
    print(f"[green]SQLite initialized at {db}[/green]")


@app.command()
def build_index_cmd(
    with_embeddings: bool = typer.Option(False, help="Build FAISS sentence-transformer index"),
) -> None:
    """Build hybrid retrieval indexes."""
    count = build_index(with_embeddings=with_embeddings)
    print(f"[green]Built index with {count} chunks[/green]")


app.command(name="build-index")(build_index_cmd)


@app.command()
def ask(
    question: str,
    session_id: str = "cli",
    strategy: str | None = typer.Option(None, help="Retrieval strategy: bm25, tfidf, hybrid, hybrid_rerank"),
    generation: str | None = typer.Option(None, help="Generation mode: extractive, deepseek, openai"),
) -> None:
    """Ask a question."""
    if generation:
        os.environ["EKA_GENERATION_MODE"] = generation
    assistant = EnterpriseAssistant(retrieval_strategy=strategy)
    response = assistant.ask(question, session_id=session_id)
    print(response.model_dump_json(indent=2, ensure_ascii=False))


@app.command(name="eval")
def eval_cmd(
    output: Path | None = None,
    strategy: str | None = typer.Option(None, help="Retrieval strategy to evaluate"),
    report: bool = typer.Option(True, help="Write JSON run and Markdown report"),
) -> None:
    """Run offline evaluation."""
    result = run_eval(retrieval_strategy=strategy)
    if report:
        json_path, md_path = save_eval_run(result)
        print(f"[green]Saved eval run to {json_path}[/green]")
        print(f"[green]Saved report to {md_path}[/green]")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


@app.command(name="eval-compare")
def eval_compare_cmd(
    strategies: str = typer.Option(
        "bm25,tfidf,hybrid,hybrid_rerank",
        help="Comma-separated retrieval strategies",
    ),
) -> None:
    """Compare multiple retrieval strategies in one report."""
    strategy_list = [item.strip() for item in strategies.split(",") if item.strip()]
    result = run_eval_compare(strategy_list)
    json_path, md_path = save_eval_compare(result)
    print(f"[green]Saved compare run to {json_path}[/green]")
    print(f"[green]Saved compare report to {md_path}[/green]")
    print(json.dumps(result, ensure_ascii=False, indent=2))


@app.command(name="doctor")
def doctor_cmd() -> None:
    """Check data, indexes, models, and environment configuration."""
    print(json.dumps(run_doctor(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
