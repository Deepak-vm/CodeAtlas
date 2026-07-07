"""
ingestion/js_chunker.py

Chunking for JavaScript, TypeScript, and JSX/TSX files.

Strategy (in order of preference):
  1. tree-sitter AST — accurate symbol boundaries (function declarations,
     arrow functions, class declarations, React components)
  2. Regex fallback — used automatically if tree-sitter is unavailable or
     grammar compilation fails. Honest about which path was taken.

The regex fallback won't be as clean as AST boundaries (template literals
with nested braces can trip it) but is good enough to prove the architecture.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from config import (
    JS_FALLBACK_CHUNK_LINES,
    JS_FALLBACK_OVERLAP_LINES,
)


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
    # tree-sitter not installed or grammar not compiled — regex fallback kicks in
    pass


# Node types we want to extract via tree-sitter
_TS_SYMBOL_TYPES = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "class_declaration",
    "method_definition",
    "lexical_declaration",   # const MyComp = () => ...
    "variable_declaration",  # var/let MyComp = function() ...
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
        # If tree-sitter found nothing (e.g. pure config file), fall through

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
            start_line = node.start_point[0] + 1   # 0-indexed → 1-indexed
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
            # Don't recurse into matched nodes (avoids double-counting class methods)
            return
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return chunks


def _extract_symbol_name(node: Any, source: str) -> str | None:
    """Best-effort symbol name extraction from a tree-sitter node."""
    # Function/class declarations have a direct .name child
    for child in node.children:
        if child.type == "identifier":
            start = child.start_byte
            end = child.end_byte
            return source[start:end]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Regex fallback
# ─────────────────────────────────────────────────────────────────────────────

# Named function declarations:  function myFunc(
# Arrow functions assigned to const/let:  const myFunc = (...) =>
# Class declarations:  class MyClass
_TOP_LEVEL_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?"
    r"(?:"
    r"(?:async\s+)?function\s+(\w+)"         # function declaration
    r"|class\s+(\w+)"                         # class declaration
    r"|(?:const|let|var)\s+(\w+)\s*="        # const x = ...
    r")",
    re.MULTILINE,
)


def _chunk_with_regex(
    source: str,
    repo: str,
    file_path: str,
    language: str,
) -> list[dict]:
    """
    Regex-based chunking: find top-level declarations, chunk from one to the next.
    Falls back to sliding window if no declarations found.
    """
    lines = source.splitlines(keepends=True)
    total = len(lines)

    # Find all matches with their line numbers
    splits: list[tuple[int, str]] = []  # (1-indexed line, symbol name)
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
    window: int = JS_FALLBACK_CHUNK_LINES,
    overlap: int = JS_FALLBACK_OVERLAP_LINES,
) -> list[dict]:
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
