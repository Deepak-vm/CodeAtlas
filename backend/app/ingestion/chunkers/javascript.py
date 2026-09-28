"""
backend/app/ingestion/chunkers/javascript.py

Chunking for JavaScript, TypeScript, and JSX/TSX files.

Strategy (in order of preference):
  1. tree-sitter AST — accurate symbol boundaries (function declarations,
     arrow functions, class declarations, React components)
  2. Regex fallback — used automatically if tree-sitter is unavailable or
     grammar compilation fails.

Migrated from: ingestion/js_chunker.py
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from backend.app.core.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Try to import tree-sitter once at module load time
# ─────────────────────────────────────────────────────────────────────────────
_TREE_SITTER_AVAILABLE = False
_ts_parser = None
_ts_language = None

try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript as tsjava

    _ts_language = Language(tsjava.language())
    _ts_parser = Parser(_ts_language)
    _TREE_SITTER_AVAILABLE = True
except Exception:
    pass


# Node types we want to extract via tree-sitter
_TS_SYMBOL_TYPES = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "class_declaration",
    "method_definition",
    "lexical_declaration",
    "variable_declaration",
}

# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def chunk_js_file(
    file_path: Path,
    repo: str,
    repo_root: Path,
) -> list[dict[str, Any]]:
    """
    Parse a JS/TS/JSX/TSX file and return a list of chunk dicts.
    Uses tree-sitter if available, otherwise falls back to regex chunking.
    """
    rel_path = file_path.relative_to(repo_root).as_posix()

    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lang = _detect_language(file_path.suffix.lower())

    if _TREE_SITTER_AVAILABLE:
        chunks = _chunk_with_treesitter(source, repo, rel_path, lang)
        if chunks:
            return chunks

    return _chunk_with_regex(source, repo, rel_path, lang)


# ─────────────────────────────────────────────────────────────────────────────
# tree-sitter path
# ─────────────────────────────────────────────────────────────────────────────

def _chunk_with_treesitter(
    source: str,
    repo: str,
    file_path: str,
    language: str,
) -> list[dict]:
    assert _ts_parser is not None
    tree = _ts_parser.parse(source.encode("utf-8"))
    lines = source.splitlines(keepends=True)
    chunks: list[dict] = []

    def _walk(node: Any) -> None:
        if node.type in _TS_SYMBOL_TYPES:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            symbol = _extract_symbol_name(node, source)
            content = "".join(lines[start_line - 1 : end_line])
            header = f"// {file_path}\n// symbol: {symbol or 'anonymous'}\n\n"
            chunks.append(_make_chunk(
                repo=repo,
                file_path=file_path,
                content=header + content.strip(),
                symbol_name=symbol,
                language=language,
                start_line=start_line,
                end_line=end_line,
            ))
            return
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return chunks


def _extract_symbol_name(node: Any, source: str) -> str | None:
    for child in node.children:
        if child.type == "identifier":
            start = child.start_byte
            end = child.end_byte
            return source[start:end]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Regex fallback
# ─────────────────────────────────────────────────────────────────────────────

_TOP_LEVEL_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?"
    r"(?:"
    r"(?:async\s+)?function\s+(\w+)"
    r"|class\s+(\w+)"
    r"|(?:const|let|var)\s+(\w+)\s*="
    r")",
    re.MULTILINE,
)


def _chunk_with_regex(
    source: str,
    repo: str,
    file_path: str,
    language: str,
) -> list[dict]:
    lines = source.splitlines(keepends=True)
    total = len(lines)

    splits: list[tuple[int, str]] = []
    for m in _TOP_LEVEL_RE.finditer(source):
        line_no = source[: m.start()].count("\n") + 1
        name = m.group(1) or m.group(2) or m.group(3) or "anonymous"
        splits.append((line_no, name))

    if not splits:
        return _sliding_window(lines, repo, file_path, language)

    chunks: list[dict] = []
    for idx, (start_line, symbol) in enumerate(splits):
        end_line = splits[idx + 1][0] - 1 if idx + 1 < len(splits) else total
        content = "".join(lines[start_line - 1 : end_line]).strip()
        if content:
            header = f"// {file_path}\n// symbol: {symbol}\n\n"
            chunks.append(_make_chunk(
                repo=repo,
                file_path=file_path,
                content=header + content,
                symbol_name=symbol,
                language=language,
                start_line=start_line,
                end_line=end_line,
            ))

    return chunks


def _sliding_window(
    lines: list[str],
    repo: str,
    file_path: str,
    language: str,
    window: int | None = None,
    overlap: int | None = None,
) -> list[dict]:
    if window is None:
        window = settings.js_fallback_chunk_lines
    if overlap is None:
        overlap = settings.js_fallback_overlap_lines
    chunks = []
    step = window - overlap
    total = len(lines)
    start = 1
    while start <= total:
        end = min(start + window - 1, total)
        content = "".join(lines[start - 1 : end]).strip()
        if content:
            chunks.append(_make_chunk(
                repo=repo,
                file_path=file_path,
                content=content,
                symbol_name=None,
                language=language,
                start_line=start,
                end_line=end,
            ))
        start += step
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_chunk(
    repo: str,
    file_path: str,
    content: str,
    symbol_name: str | None,
    language: str,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "chunk_type": "code",
        "repo": repo,
        "file_path": file_path,
        "content": content,
        "symbol_name": symbol_name,
        "language": language,
        "start_line": start_line,
        "end_line": end_line,
        "commit_hash": None,
        "commit_message": None,
        "commit_date": None,
        "changed_files": [],
    }


def _detect_language(suffix: str) -> str:
    return {
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
    }.get(suffix, "javascript")


def is_treesitter_available() -> bool:
    """Utility for reporting / tests."""
    return _TREE_SITTER_AVAILABLE
