"""
Search/Replace Diff Parser and Applier

Parses LLM-emitted search/replace blocks and applies them to existing code.
Used by the progressive evolve pipeline to modify code incrementally instead
of regenerating the entire file.

Format:
    <<<<<<< SEARCH
    exact existing code to find
    =======
    replacement code
    >>>>>>> REPLACE
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class DiffApplyError(Exception):
    """Raised when a search/replace block cannot be applied."""

    def __init__(self, message: str, block_index: int = -1, search: str = "") -> None:
        super().__init__(message)
        self.block_index = block_index
        self.search = search


@dataclass
class SearchReplaceBlock:
    search: str
    replace: str


# ─── Parsing ─────────────────────────────────────────────────────────


# Pattern matches complete S/R blocks.
# Accepts minor LLM format deviations: optional trailing text after markers,
# any amount of whitespace around separator lines.
_SR_PATTERN = re.compile(
    r"<{6,7}\s*SEARCH\s*\n"   # <<<<<<< SEARCH
    r"(.*?)\n"                  # search body
    r"={6,7}\s*\n"             # =======
    r"(.*?)\n"                  # replace body
    r">{6,7}\s*REPLACE",       # >>>>>>> REPLACE
    re.DOTALL,
)


def parse_diff_blocks(text: str) -> list[SearchReplaceBlock]:
    """Extract all complete search/replace blocks from raw LLM output."""
    blocks: list[SearchReplaceBlock] = []
    for m in _SR_PATTERN.finditer(text):
        search = m.group(1)
        replace = m.group(2)
        blocks.append(SearchReplaceBlock(search=search, replace=replace))
    return blocks


# ─── Application ─────────────────────────────────────────────────────


def _normalize_whitespace(text: str) -> str:
    """Normalize trailing whitespace per line for fuzzy matching."""
    return "\n".join(line.rstrip() for line in text.split("\n"))


def apply_diff(current_code: str, block: SearchReplaceBlock) -> str:
    """Apply a single search/replace block. Returns updated code.

    Tries exact match first, then falls back to whitespace-normalized match.
    Raises DiffApplyError if neither works.
    """
    search = block.search
    replace = block.replace

    # Exact match
    if search in current_code:
        return current_code.replace(search, replace, 1)

    # Fuzzy: normalize trailing whitespace per line
    norm_code = _normalize_whitespace(current_code)
    norm_search = _normalize_whitespace(search)
    if norm_search in norm_code:
        # Find the position in normalized space, then apply to original
        idx = norm_code.index(norm_search)
        # Map normalized index back to original: count characters in original
        # lines up to the same line/col position.
        norm_lines_before = norm_code[:idx].count("\n")
        orig_lines = current_code.split("\n")

        # Find start of the matching region in original
        orig_start = sum(len(orig_lines[i]) + 1 for i in range(norm_lines_before))
        # Adjust for position within the line
        norm_line_start = norm_code.rfind("\n", 0, idx) + 1
        col = idx - norm_line_start
        orig_line_start = current_code.rfind("\n", 0, orig_start) + 1 if norm_lines_before > 0 else 0
        orig_start = orig_line_start + col

        # Find end: count lines in the search text
        search_line_count = norm_search.count("\n")
        end_line = norm_lines_before + search_line_count
        if end_line < len(orig_lines):
            orig_end = sum(len(orig_lines[i]) + 1 for i in range(end_line))
            last_line_len = len(norm_search.split("\n")[-1])
            orig_end = orig_end + last_line_len
        else:
            orig_end = len(current_code)

        return current_code[:orig_start] + replace + current_code[orig_end:]

    raise DiffApplyError(
        f"Search text not found in current code (first 80 chars): {search[:80]!r}",
        search=search,
    )


def apply_diffs(current_code: str, blocks: list[SearchReplaceBlock]) -> str:
    """Apply multiple search/replace blocks sequentially.

    Each block operates on the result of the previous one.
    Raises DiffApplyError on first failure.
    """
    code = current_code
    for i, block in enumerate(blocks):
        try:
            code = apply_diff(code, block)
        except DiffApplyError as e:
            e.block_index = i
            raise
    return code
