#!/usr/bin/env python3
"""
eval/run_eval.py

Rigorous evaluation runner for CodeAtlas.

Metrics computed:
  1. Retrieval accuracy : did expected_repo appear in retrieved chunks/citations?
  2. File hit rate      : did expected_file substring appear in retrieved files/citations?
  3. Answer quality     : non-empty, grounded response (or correct fallback for negative tests)
  4. Latency            : ms per query execution
  5. Ambiguity detection: did the system raise ambiguity flag for true conflicting-impl queries?
  6. Hallucination check: did the negative test properly decline to invent code?

Scoring rules:
  - Questions with expected_repo == "NONE" (negative/hallucination tests) are EXCLUDED from
    repo_hit and file_hit numerators AND denominators. They only count toward answer_ok.
  - Ambiguity detection is scored only for questions where is_ambiguity_test == True
    (genuine conflicting-implementation cases). Broad multi-repo queries (Q14, Q15, Q16)
    are NOT flagged as ambiguity tests.

Usage:
  python -m eval.run_eval
  python -m eval.run_eval --questions 1,2,5   # run specific question IDs
  python -m eval.run_eval --output results.json
  python -m eval.run_eval --verbose            # print retrieved files on misses
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.graph import build_graph
from agents.state import AgentState
from eval.test_questions import EVAL_QUESTIONS

app = typer.Typer(add_completion=False)
console = Console()


def _run_query(graph, query: str, repo_allowlist: list[str] | None = None) -> tuple[dict, float]:
    """Run a single query through the full pipeline. Returns (result, latency_ms)."""
    t0 = time.perf_counter()
    result = graph.invoke({
        "query": query,
        "routed_repos": repo_allowlist or [],   # allowlist pre-seeds the router
        "routed_types": [],
        "code_chunks": [],
        "commit_chunks": [],
        "readme_chunks": [],
        "ambiguity_flag": False,
        "ambiguity_detail": "",
        "final_answer": "",
        "citations": [],
    })
    latency_ms = (time.perf_counter() - t0) * 1000
    return result, latency_ms


def _collect_file_paths(result: dict) -> list[str]:
    """Collect all retrieved file paths from chunks and citations."""
    paths: list[str] = []
    all_chunks = (
        result.get("code_chunks", [])
        + result.get("commit_chunks", [])
        + result.get("readme_chunks", [])
    )
    for c in all_chunks:
        fp = c.get("file_path") or ""
        if fp:
            paths.append(fp)
    for c in result.get("citations", []):
        fp = c.get("file_path") or ""
        if fp and fp not in paths:
            paths.append(fp)
    return paths


def _check_repo_hit(result: dict, expected_repo) -> bool | None:
    """
    Did expected repo appear in retrieved chunks or citations?

    Returns None for NONE-repo questions (excluded from metric entirely).
    """
    if expected_repo is None:
        return False  # Require explicit ground truth
    if expected_repo == "NONE":
        return None  # Negative test — excluded from this metric

    expected = [expected_repo] if isinstance(expected_repo, str) else expected_repo

    all_chunks = (
        result.get("code_chunks", [])
        + result.get("commit_chunks", [])
        + result.get("readme_chunks", [])
    )
    retrieved_repos = {c.get("repo") for c in all_chunks if c.get("repo")}
    citation_repos = {c.get("repo") for c in result.get("citations", []) if c.get("repo")}
    all_found = retrieved_repos | citation_repos

    return any(r in all_found for r in expected)


def _check_file_hit(result: dict, expected_file: str | None, expected_repo) -> bool | None:
    """
    Did expected_file substring appear in retrieved chunks or citations?

    Returns None for NONE-repo questions (excluded from metric entirely).
    """
    if expected_repo == "NONE":
        return None  # Negative test — excluded from this metric
    if expected_file is None:
        return False  # Require explicit ground truth

    target = expected_file.lower()

    # Check citations
    for c in result.get("citations", []):
        fp = (c.get("file_path") or "").lower()
        if target in fp:
            return True

    # Check all retrieved chunks — also scan changed_files list for commit chunks
    all_chunks = (
        result.get("code_chunks", [])
        + result.get("commit_chunks", [])
        + result.get("readme_chunks", [])
    )
    for c in all_chunks:
        fp = (c.get("file_path") or "").lower()
        if target in fp:
            return True
        # For commit chunks: file_path is primary file, but also check all changed_files
        for cf in c.get("changed_files") or []:
            if target in cf.lower():
                return True

    return False


def _check_answer_quality(result: dict, expected_repo) -> bool:
    """Was a non-empty, non-error answer generated?"""
    answer = result.get("final_answer", "")
    if not answer or len(answer) < 30:
        return False

    if expected_repo == "NONE":
        # Hallucination / Negative test check — system should decline to answer
        negative_phrases = [
            "not found", "cannot find", "no relevant", "not in the codebase",
            "no code", "doesn't appear", "does not contain", "not available",
            "no information", "cannot locate", "not present",
        ]
        return any(p in answer.lower() for p in negative_phrases) or len(result.get("citations", [])) == 0

    error_phrases = ["fatal error", "exception occurred", "traceback", "internal server error"]
    return not any(p in answer.lower() for p in error_phrases)


@app.command()
def main(
    questions: str = typer.Option(None, "--questions", help="Comma-separated question IDs to run, e.g. 1,2,5"),
    output: Path = typer.Option(None, "--output", help="Save results to JSON file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print retrieved file paths on misses"),
    repos: str = typer.Option(
        None,
        "--repos",
        help=(
            "Comma-separated allowlist of repo names to restrict retrieval to, e.g. "
            "'LearnSphere,SketchXPad,MultiSource-RAG-Agent'. "
            "Defaults to all repos in the index. Use this to pin eval runs to a "
            "fixed repo set for reproducibility."
        ),
    ),
) -> None:
    """
    Run the evaluation suite against the full LangGraph pipeline with strict ground truth.
    """
    console.print("\n[bold green]📊 CodeAtlas — Rigorous Evaluation Suite[/bold green]\n")

    # Parse repo allowlist (for deterministic, drift-proof eval runs)
    repo_allowlist: list[str] | None = None
    if repos:
        repo_allowlist = [r.strip() for r in repos.split(",") if r.strip()]
        console.print(f"[bold]Repo allowlist:[/bold] {repo_allowlist}")
    else:
        console.print("[dim]Repo allowlist: all (no --repos flag — index may contain extra repos)[/dim]")

    # Filter questions
    if questions:
        ids = {int(x.strip()) for x in questions.split(",")}
        to_run = [q for q in EVAL_QUESTIONS if q["id"] in ids]
    else:
        to_run = EVAL_QUESTIONS

    console.print(f"Running {len(to_run)} questions against strict ground truth…\n")

    graph = build_graph()

    rows: list[dict] = []

    # Separate counters: retrieval metrics exclude NONE-repo questions
    n_retrieval_total = 0   # denominator for repo_hit and file_hit
    n_repo_hit = 0
    n_file_hit = 0

    n_answer_ok = 0          # denominator = all questions

    # Ambiguity: only true conflicting-implementation cases
    n_ambiguity_checked = 0
    n_ambiguity_correct = 0

    total_latency = 0.0

    for q in to_run:
        qid = q["id"]
        query = q["query"]
        expected_repo = q["expected_repo"]
        expected_file = q["expected_file"]
        is_ambiguity_test = q.get("is_ambiguity_test", False)
        is_negative_test = expected_repo == "NONE"

        console.print(f"[dim]Q{qid}:[/dim] {query[:70]}…" if len(query) > 70 else f"[dim]Q{qid}:[/dim] {query}")

        try:
            result, latency_ms = _run_query(graph, query, repo_allowlist)
        except Exception as e:
            console.print(f"  [red]✗ Error: {e}[/red]")
            rows.append({"id": qid, "query": query, "error": str(e)})
            continue

        repo_hit = _check_repo_hit(result, expected_repo)   # None for NONE-repo
        file_hit = _check_file_hit(result, expected_file, expected_repo)   # None for NONE-repo
        answer_ok = _check_answer_quality(result, expected_repo)
        ambiguity_flag = result.get("ambiguity_flag", False)

        # ── Update counters ──────────────────────────────────────────────
        # Repo/file hit: only count questions that have a real expected target
        if not is_negative_test:
            n_retrieval_total += 1
            n_repo_hit += int(repo_hit)
            n_file_hit += int(file_hit)

        n_answer_ok += int(answer_ok)
        total_latency += latency_ms

        # Ambiguity: only true conflicting-implementation cases
        if is_ambiguity_test:
            n_ambiguity_checked += 1
            if ambiguity_flag:
                n_ambiguity_correct += 1

        # ── Diagnostics: print file paths on misses (always for NONE, verbose for hits) ──
        retrieved_files = _collect_file_paths(result)
        if not is_negative_test and not file_hit:
            console.print(
                f"  [yellow]⚠ file_hit MISS[/yellow] — expected [bold]{expected_file!r}[/bold] | "
                f"got: {[Path(f).name for f in retrieved_files[:6]] or ['(none)']}"
            )
        elif verbose and not is_negative_test and file_hit:
            console.print(f"  [dim]retrieved: {[Path(f).name for f in retrieved_files[:4]]}[/dim]")
        if is_negative_test and verbose:
            console.print(f"  [dim]retrieved files: {[Path(f).name for f in retrieved_files[:6]] or ['(none)']}"
                          f" | citations: {len(result.get('citations', []))}[/dim]")

        # ── Row record ───────────────────────────────────────────────────
        row = {
            "id": qid,
            "query": query,
            "expected_repo": expected_repo,
            "expected_file": expected_file,
            "expected_type": q["expected_type"],
            "is_ambiguity_test": is_ambiguity_test,
            "is_negative_test": is_negative_test,
            "routed_types": result.get("routed_types", []),
            "routed_repos": result.get("routed_repos", []),
            "repo_hit": repo_hit,       # None for negative tests
            "file_hit": file_hit,       # None for negative tests
            "answer_ok": answer_ok,
            "ambiguity_flag": ambiguity_flag,
            "latency_ms": round(latency_ms, 1),
            "retrieved_files": retrieved_files[:8],
            "answer_snippet": result.get("final_answer", "")[:200],
        }
        rows.append(row)

        # ── Per-question status icon ──────────────────────────────────────
        if is_negative_test:
            icon = "[green]✓[/green]" if answer_ok else "[red]✗[/red]"
        else:
            icon = (
                "[green]✓[/green]" if repo_hit and file_hit and answer_ok
                else "[yellow]▲[/yellow]" if repo_hit
                else "[red]✗[/red]"
            )

        console.print(
            f"  {icon} repo_hit={repo_hit} file_hit={file_hit} "
            f"answer_ok={answer_ok} latency={latency_ms:.0f}ms ambiguity={ambiguity_flag}"
        )

        if verbose:
            console.print(f"  [dim]{row['answer_snippet']}…[/dim]\n")

        # Rate-limit guard: Groq's free-tier TPM cap is 12k tokens/min.
        # Each synthesis call burns ~2-3k tokens; back-to-back queries hit the
        # cap around Q8 and corrupt the answer_ok denominator with error rows.
        time.sleep(5)


    n_total = len(rows)
    console.print()
    table = Table(title="Evaluation Summary (Strict Ground Truth)", show_header=True)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Score", justify="right")
    table.add_column("Detail")

    n_neg = sum(1 for r in rows if r.get("is_negative_test"))
    table.add_row(
        "Repo hit rate",
        f"{n_repo_hit}/{n_retrieval_total} ({100*n_repo_hit//n_retrieval_total if n_retrieval_total else 0}%)",
        f"Expected repo in retrieved chunks/citations ({n_neg} negative test(s) excluded)",
    )
    table.add_row(
        "File hit rate",
        f"{n_file_hit}/{n_retrieval_total} ({100*n_file_hit//n_retrieval_total if n_retrieval_total else 0}%)",
        f"Expected file substring in retrieved files/citations ({n_neg} negative test(s) excluded)",
    )
    table.add_row(
        "Answer quality",
        f"{n_answer_ok}/{n_total} ({100*n_answer_ok//n_total if n_total else 0}%)",
        "Non-empty grounded response (negative tests: correct refusal)",
    )
    if n_ambiguity_checked > 0:
        table.add_row(
            "Ambiguity detection",
            f"{n_ambiguity_correct}/{n_ambiguity_checked} ({100*n_ambiguity_correct//n_ambiguity_checked}%)",
            "Flag raised on true conflicting-implementation cross-repo queries only",
        )
    table.add_row(
        "Avg latency",
        f"{total_latency/n_total:.0f} ms" if n_total else "—",
        "End-to-end pipeline latency per query",
    )
    console.print(table)

    # ── File-hit miss summary ──────────────────────────────────────────────
    misses = [r for r in rows if r.get("file_hit") is False]
    if misses:
        console.print("\n[bold yellow]File-hit misses — retrieved vs. expected:[/bold yellow]")
        miss_table = Table(show_header=True, header_style="bold yellow")
        miss_table.add_column("Q#", style="dim")
        miss_table.add_column("Expected file")
        miss_table.add_column("Retrieved file names (top 6)")
        for r in misses:
            retrieved_names = [Path(f).name for f in r.get("retrieved_files", [])][:6]
            miss_table.add_row(
                str(r["id"]),
                r.get("expected_file") or "(none)",
                ", ".join(retrieved_names) or "(nothing retrieved)",
            )
        console.print(miss_table)
        console.print(
            "[dim]Tip: If expected file is absent entirely → coverage/chunking gap. "
            "If it appears lower down → tune k or BM25/dense fusion weights.[/dim]\n"
        )

    # ── Save to JSON ──────────────────────────────────────────────────────
    if output:
        output.write_text(json.dumps(rows, indent=2))
        console.print(f"\nResults saved → {output}")


if __name__ == "__main__":
    app()
