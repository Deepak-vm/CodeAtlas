"""
ingestion/python_chunker.py

AST-aware chunking for Python files.

Strategy:
  1. Parse the file with `ast.parse()`.
  2. Walk top-level FunctionDef, AsyncFunctionDef, ClassDef nodes.
  3. For ClassDef, also emit each method as a sub-chunk.
  4. Fallback: if no symbols found, slide a fixed-size window over the lines.

Each chunk is a dict matching the canonical schema defined in config.py docstring.
"""

from __future__ import annotations

import ast
import textwrap
import uuid
from pathlib import Path
from typing import Any

from config import (
    PYTHON_FALLBACK_CHUNK_LINES,
    PYTHON_FALLBACK_OVERLAP_LINES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_chunk(
    repo: str,
    file_path: str,
    content: str,
    symbol_name: str | None,
    language: str,
    start_line: int,
    end_line: int,
    chunk_type: str = "code",
    extra: dict | None = None,
) -> dict[str, Any]:
    chunk = {
        "id": str(uuid.uuid4()),
        "chunk_type": chunk_type,
        "repo": repo,
        "file_path": file_path,
        "content": content.strip(),
        "symbol_name": symbol_name,
        "language": language,
        "start_line": start_line,
        "end_line": end_line,
        "commit_hash": None,
        "commit_message": None,
        "commit_date": None,
        "changed_files": [],
    }
    if extra:
        chunk.update(extra)
    return chunk


def _get_docstring(node: ast.AST) -> str | None:
    """Extract the docstring from a function/class node, or None."""
    try:
        return ast.get_docstring(node)
    except Exception:
        return None


def _extract_source_lines(lines: list[str], start: int, end: int) -> str:
    """
    Extract source lines (1-indexed, inclusive) and dedent.
    `lines` is the raw splitlines of the file.
    """
    extracted = lines[start - 1 : end]
    return textwrap.dedent("".join(extracted))


# ─────────────────────────────────────────────────────────────────────────────
# Fallback: sliding window
# ─────────────────────────────────────────────────────────────────────────────

def _sliding_window_chunks(
    lines: list[str],
    repo: str,
    file_path: str,
    language: str,
    window: int = PYTHON_FALLBACK_CHUNK_LINES,
    overlap: int = PYTHON_FALLBACK_OVERLAP_LINES,
) -> list[dict]:
    chunks = []
    step = window - overlap
    total = len(lines)
    start = 1
    while start <= total:
        end = min(start + window - 1, total)
        content = "".join(lines[start - 1 : end])
        if content.strip():
            chunks.append(
                _make_chunk(
                    repo=repo,
                    file_path=file_path,
                    content=content,
                    symbol_name=None,
                    language=language,
                    start_line=start,
                    end_line=end,
                )
            )
        start += step
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# AST visitor
# ─────────────────────────────────────────────────────────────────────────────

class _ChunkVisitor(ast.NodeVisitor):
    """
    Visits top-level functions and classes.
    For classes, also visits each method as a sub-chunk.
    """

    def __init__(self, lines: list[str], repo: str, file_path: str, language: str):
        self.lines = lines
        self.repo = repo
        self.file_path = file_path
        self.language = language
        self.chunks: list[dict] = []
        self._inside_class: str | None = None

    def _emit(self, node: ast.AST, symbol: str) -> None:
        start = node.lineno                       # type: ignore[attr-defined]
        end = node.end_lineno                     # type: ignore[attr-defined]
        content = _extract_source_lines(self.lines, start, end)
        docstring = _get_docstring(node)

        # Prefix content with a brief header for better embedding signal
        header_parts = [f"# {self.file_path}"]
        if self._inside_class:
            header_parts.append(f"# class: {self._inside_class}")
        header_parts.append(f"# symbol: {symbol}")
        if docstring:
            header_parts.append(f'# docstring: """{docstring[:200]}"""')
        header = "\n".join(header_parts) + "\n\n"

        self.chunks.append(
            _make_chunk(
                repo=self.repo,
                file_path=self.file_path,
                content=header + content,
                symbol_name=symbol,
                language=self.language,
                start_line=start,
                end_line=end,
                extra={"parent_class": self._inside_class},
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._emit(node, node.name)
        # Don't recurse further — nested functions captured with parent

    # Treat async the same as sync
    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Emit the class as a whole chunk (includes all methods)
        self._emit(node, node.name)

        # Also emit each method separately for fine-grained retrieval
        prev_class = self._inside_class
        self._inside_class = node.name
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child is not node:  # skip the class node itself
                    self._emit(child, f"{node.name}.{child.name}")
        self._inside_class = prev_class


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def chunk_python_file(
    file_path: Path,
    repo: str,
    repo_root: Path,
) -> list[dict]:
    """
    Parse a .py file and return a list of chunk dicts.

    Falls back to sliding-window chunking if:
      - the file has syntax errors
      - the file has no top-level symbols
    """
    rel_path = file_path.relative_to(repo_root).as_posix()

    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = source.splitlines(keepends=True)

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        # Fallback for files that can't be parsed (e.g. Python 2, generated code)
        return _sliding_window_chunks(lines, repo, rel_path, "python")

    visitor = _ChunkVisitor(lines, repo, rel_path, "python")
    # Only visit top-level nodes — ClassDef handles its own methods internally
    for node in ast.iter_child_nodes(tree):
        visitor.visit(node)

    if not visitor.chunks:
        # File has no functions/classes (e.g. pure script, __init__.py with only imports)
        return _sliding_window_chunks(lines, repo, rel_path, "python")

    return visitor.chunks
