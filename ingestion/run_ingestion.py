#!/usr/bin/env python3
"""
ingestion/run_ingestion.py

CLI entry point.

Usage:
  # From repos.json (path or GitHub URL entries)
  python -m ingestion.run_ingestion

  # Override repos file location
  python -m ingestion.run_ingestion --repos-config ./my_repos.json

  # Quick test: single local path
  python -m ingestion.run_ingestion --local-path /path/to/repo --repo-name my-repo

Output: data/chunks/{code,commit,readme}_chunks.jsonl
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table

# Allow running as `python -m ingestion.run_ingestion` from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from ingestion.repo_walker import collect_code_files, collect_doc_files, relative_path
from ingestion.python_chunker import chunk_python_file
from ingestion.js_chunker import chunk_js_file, is_treesitter_available
from ingestion.commit_ingester import ingest_commits
from ingestion.readme_ingester import chunk_readme_file

app = typer.Typer(add_completion=False, pretty_exceptions_short=True)
console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_repos_config(repos_config: Path) -> list[dict]:
    """Load repos.json — list of {name, path?  url?} dicts."""
    if not repos_config.exists():
        console.print(
            f"[red]✗ repos.json not found at {repos_config}[/red]\n"
            "Create it or pass --local-path / --repo-name for a quick run.",
            highlight=False,
        )
        raise SystemExit(1)
    with open(repos_config) as f:
        return json.load(f)


def _resolve_repo_path(entry: dict) -> Path:
    """
    Resolve a repo entry to a local path.
    If 'url' is present and 'path' is absent, clone into config.REPOS_DIR.
    """
    if "path" in entry:
        p = Path(entry["path"]).expanduser().resolve()
        if not p.is_dir():
            console.print(f"[red]✗ path does not exist: {p}[/red]")
            raise SystemExit(1)
        return p

    if "url" in entry:
        name = entry.get("name") or entry["url"].rstrip("/").split("/")[-1].removesuffix(".git")
        dest = config.REPOS_DIR / name
        if dest.exists():
            console.print(f"  [dim]already cloned → {dest}[/dim]")
        else:
            console.print(f"  [cyan]cloning {entry['url']} → {dest}[/cyan]")
            config.REPOS_DIR.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", "--depth", "500", entry["url"], str(dest)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                console.print(f"[red]✗ git clone failed:\n{result.stderr}[/red]")
                raise SystemExit(1)
        return dest

    console.print(f"[red]✗ repo entry must have 'path' or 'url': {entry}[/red]")
    raise SystemExit(1)


def _write_jsonl(path: Path, chunks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, chunks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Per-repo ingestion
# ─────────────────────────────────────────────────────────────────────────────

def ingest_repo(
    repo_name: str,
    repo_path: Path,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Ingest one repo → (code_chunks, commit_chunks, readme_chunks).
    """
    console.rule(f"[bold cyan]Ingesting: {repo_name}[/bold cyan]")

    # ── Code chunks ────────────────────────────────────────────────────────
    code_files = collect_code_files(repo_path)
    console.print(f"  [dim]{len(code_files)} code files found[/dim]")

    code_chunks: list[dict] = []
    py_files = [f for f in code_files if f.suffix == ".py"]
    js_files = [f for f in code_files if f.suffix in {".js", ".jsx", ".ts", ".tsx"}]

    for f in track(py_files, description=f"  [green]Python[/green] ({repo_name})", console=console):
        code_chunks.extend(chunk_python_file(f, repo_name, repo_path))

    ts_label = "tree-sitter" if is_treesitter_available() else "regex-fallback"
    for f in track(js_files, description=f"  [yellow]JS/TS[/yellow] ({ts_label})", console=console):
        code_chunks.extend(chunk_js_file(f, repo_name, repo_path))

    console.print(f"  ✓ [bold]{len(code_chunks)}[/bold] code chunks")

    # ── Commit chunks ──────────────────────────────────────────────────────
    commit_chunks = ingest_commits(repo_path, repo_name)
    console.print(f"  ✓ [bold]{len(commit_chunks)}[/bold] commit chunks")

    # ── README / doc chunks ────────────────────────────────────────────────
    doc_files = collect_doc_files(repo_path)
    readme_chunks: list[dict] = []
    for f in doc_files:
        readme_chunks.extend(chunk_readme_file(f, repo_name, repo_path))
    console.print(f"  ✓ [bold]{len(readme_chunks)}[/bold] readme/doc chunks")

    return code_chunks, commit_chunks, readme_chunks


# ─────────────────────────────────────────────────────────────────────────────
# Sanity print
# ─────────────────────────────────────────────────────────────────────────────

def _sanity_print(
    label: str,
    chunks: list[dict],
    n: int = 3,
) -> None:
    import random
    console.rule(f"[bold magenta]Sanity check: {label}[/bold magenta]")
    sample = random.sample(chunks, min(n, len(chunks)))
    for c in sample:
        console.print(
            f"  [cyan]{c['repo']}[/cyan] | "
            f"[green]{c['file_path']}[/green]"
            f"[dim]:{c.get('start_line', '?')}-{c.get('end_line', '?')}[/dim] | "
            f"symbol=[yellow]{c.get('symbol_name', '—')}[/yellow]"
        )
        snippet = c["content"][:200].replace("\n", " ")
        console.print(f"  [dim]{snippet}…[/dim]\n")


def _remove_repo_from_jsonl(jsonl_path: Path, repo_name: str) -> None:
    if not jsonl_path.exists():
        return
    lines_to_keep = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    if data.get("repo", "").lower() != repo_name.lower():
                        lines_to_keep.append(line)
                except Exception:
                    lines_to_keep.append(line)
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.writelines(lines_to_keep)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def main(
    repos_config: Path = typer.Option(
        config.REPOS_CONFIG_FILE,
        "--repos-config",
        help="Path to repos.json",
    ),
    local_path: Path = typer.Option(
        None,
        "--local-path",
        help="Quick single-repo mode: path to a local repo directory",
    ),
    repo_name: str = typer.Option(
        None,
        "--repo-name",
        help="Name for the repo (used with --local-path)",
    ),
    only_repo: str = typer.Option(
        None,
        "--only-repo",
        help="Ingest only the specified repository name from repos.json",
    ),
    output_dir: Path = typer.Option(
        config.CHUNKS_DIR,
        "--output-dir",
        help="Directory to write JSONL chunk files",
    ),
    fresh: bool = typer.Option(
        False,
        "--fresh",
        help="Delete existing chunk files before ingesting",
    ),
) -> None:
    """
    Ingest repositories → produce code/commit/readme JSONL chunks.

    run this, then inspect the output files.
    """
    console.print(
        "\n[bold green]🔍 Knowledge Base Agent — Ingestion `[/bold green]\n"
    )

    # Resolve repo list
    if local_path is not None:
        if repo_name is None:
            repo_name = local_path.name
        repos = [{"name": repo_name, "path": str(local_path)}]
    else:
        repos = _load_repos_config(repos_config)
        if only_repo:
            repos = [r for r in repos if r["name"].lower() == only_repo.lower()]
            if not repos:
                console.print(f"[red]✗ Repository '{only_repo}' not found in {repos_config}[/red]")
                raise SystemExit(1)

    console.print(f"Repos to ingest: {[r['name'] for r in repos]}")

    # tree-sitter status
    if is_treesitter_available():
        console.print("[green]tree-sitter[/green]: ✓ available (JS/TS AST chunking)")
    else:
        console.print("[yellow]tree-sitter[/yellow]: ✗ not available → using regex fallback for JS/TS")

    # Optionally clear existing outputs
    if fresh:
        for p in [config.CODE_CHUNKS_FILE, config.COMMIT_CHUNKS_FILE, config.README_CHUNKS_FILE]:
            p.unlink(missing_ok=True)
        console.print("[dim]Cleared existing chunk files.[/dim]")

    # Ingest each repo
    total_code = total_commits = total_readme = 0

    for entry in repos:
        name = entry["name"]
        path = _resolve_repo_path(entry)

        code_chunks, commit_chunks, readme_chunks = ingest_repo(name, path)

        # Remove any prior chunks for this specific repo to avoid duplicates
        _remove_repo_from_jsonl(output_dir / "code_chunks.jsonl", name)
        _remove_repo_from_jsonl(output_dir / "commit_chunks.jsonl", name)
        _remove_repo_from_jsonl(output_dir / "readme_chunks.jsonl", name)

        _append_jsonl(output_dir / "code_chunks.jsonl", code_chunks)
        _append_jsonl(output_dir / "commit_chunks.jsonl", commit_chunks)
        _append_jsonl(output_dir / "readme_chunks.jsonl", readme_chunks)

        total_code += len(code_chunks)
        total_commits += len(commit_chunks)
        total_readme += len(readme_chunks)

        # Sanity check: 3 random samples per type
        if code_chunks:
            _sanity_print(f"code ({name})", code_chunks, n=2)
        if commit_chunks:
            _sanity_print(f"commits ({name})", commit_chunks, n=1)

    # Summary table
    table = Table(title="\n📦 Ingestion Complete", show_header=True)
    table.add_column("Type", style="bold cyan")
    table.add_column("Total Chunks", justify="right", style="bold green")
    table.add_column("Output File")
    table.add_row("code", str(total_code), str(output_dir / "code_chunks.jsonl"))
    table.add_row("commits", str(total_commits), str(output_dir / "commit_chunks.jsonl"))
    table.add_row("readme/docs", str(total_readme), str(output_dir / "readme_chunks.jsonl"))
    console.print(table)
    console.print("\n[bold]Next step:[/bold] python -m indexing.build_indexes\n")


if __name__ == "__main__":
    app()
