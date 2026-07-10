#!/usr/bin/env python3
"""
indexing/build_indexes.py

CLI entry point.

Reads JSONL chunk files produced by run_ingestion.py and builds:
  - data/indexes/code.faiss  + .meta  (+ bm25_code.pkl)
  - data/indexes/commits.faiss + .meta
  - data/indexes/readme.faiss  + .meta

Usage:
  python -m indexing.build_indexes
  python -m indexing.build_indexes --chunks-dir ./data/chunks --output-dir ./data/indexes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from indexing.embedder import Embedder
from indexing.faiss_store import FaissStore
from indexing.bm25_store import BM25Store

app = typer.Typer(add_completion=False, pretty_exceptions_short=True)
console = Console()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        console.print(f"[yellow]⚠ {path} not found — skipping[/yellow]")
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _build_and_save(
    chunks: list[dict],
    embedder: Embedder,
    faiss_path: Path,
    bm25_path: Path | None = None,
    label: str = "",
) -> None:
    if not chunks:
        console.print(f"  [yellow]No chunks for {label} — skipping[/yellow]")
        return

    console.print(f"\n[bold cyan]Building {label} index[/bold cyan] ({len(chunks)} chunks)")

    # Embed
    texts = [c["content"] for c in chunks]
    vecs = embedder.encode_documents(texts, show_progress=True)

    # FAISS
    store = FaissStore(dim=embedder.dim)
    store.add(vecs, chunks)
    store.save(faiss_path)

    # BM25 (code only)
    if bm25_path is not None:
        bm25 = BM25Store(chunks)
        bm25.save(bm25_path)


@app.command()
def main(
    chunks_dir: Path = typer.Option(config.CHUNKS_DIR, "--chunks-dir"),
    output_dir: Path = typer.Option(config.INDEXES_DIR, "--output-dir"),
) -> None:
    """
    Embed chunks and build FAISS + BM25 indexes.
    
    """
    console.print("\n[bold green]🔢 Knowledge Base Agent — Indexing [/bold green]\n")

    embedder = Embedder.get()

    code_chunks = _read_jsonl(chunks_dir / "code_chunks.jsonl")
    commit_chunks = _read_jsonl(chunks_dir / "commit_chunks.jsonl")
    readme_chunks = _read_jsonl(chunks_dir / "readme_chunks.jsonl")

    _build_and_save(
        code_chunks, embedder,
        faiss_path=output_dir / "code.faiss",
        bm25_path=output_dir / "bm25_code.pkl",
        label="code",
    )
    _build_and_save(
        commit_chunks, embedder,
        faiss_path=output_dir / "commits.faiss",
        label="commits",
    )
    _build_and_save(
        readme_chunks, embedder,
        faiss_path=output_dir / "readme.faiss",
        label="readme",
    )

    # Summary
    table = Table(title="\n✅ Index Build Complete", show_header=True)
    table.add_column("Index", style="bold cyan")
    table.add_column("Chunks", justify="right")
    table.add_column("Path")
    table.add_row("code (FAISS)", str(len(code_chunks)), str(output_dir / "code.faiss"))
    table.add_row("code (BM25)", str(len(code_chunks)), str(output_dir / "bm25_code.pkl"))
    table.add_row("commits (FAISS)", str(len(commit_chunks)), str(output_dir / "commits.faiss"))
    table.add_row("readme (FAISS)", str(len(readme_chunks)), str(output_dir / "readme.faiss"))
    console.print(table)
    console.print("\n[bold]Next step:[/bold] python -m agents.graph\n")


if __name__ == "__main__":
    app()
