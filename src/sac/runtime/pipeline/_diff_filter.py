"""
DiffChunkFilter — Streaming filter for progressive evolve.

Feeds raw LLM tokens and applies search/replace blocks to the current code
as they complete. Yields full code snapshots after each successful application,
so the frontend can render the incrementally-updated code.

Unlike TsxChunkFilter (which strips JSON envelope and passes TSX tokens),
this filter:
  1. Accumulates all raw tokens
  2. Watches for completed <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE blocks
  3. Applies each block to the running code state
  4. Yields the full updated code as a snapshot

If any block fails to apply, sets `failed = True` so the pipeline can
fall back to full-code evolve.
"""

from __future__ import annotations

from typing import Iterator

from sac.runtime.pipeline._diff import (
    DiffApplyError,
    SearchReplaceBlock,
    apply_diff,
    parse_diff_blocks,
)


class DiffChunkFilter:
    """Streaming diff applier.

    Usage:
        filt = DiffChunkFilter(current_code)
        async for token in llm.stream(...):
            for snapshot in filt.feed(token):
                yield PipelineSnapshotEvent(code=snapshot)
        for snapshot in filt.finalize():
            yield PipelineSnapshotEvent(code=snapshot)

        if filt.failed:
            # fall back to full-code evolve
    """

    def __init__(self, current_code: str) -> None:
        self._current_code = current_code
        self._raw_buffer = ""
        self._blocks_applied = 0
        self._failed = False
        self._error: str | None = None

    def feed(self, token: str) -> Iterator[str]:
        """Feed a raw LLM token. Yields full code snapshots when a new
        search/replace block is completed and successfully applied."""
        self._raw_buffer += token

        if self._failed:
            return

        # Check for newly completed blocks
        blocks = parse_diff_blocks(self._raw_buffer)
        while self._blocks_applied < len(blocks):
            block = blocks[self._blocks_applied]
            try:
                self._current_code = apply_diff(self._current_code, block)
                self._blocks_applied += 1
                yield self._current_code
            except DiffApplyError as e:
                self._failed = True
                self._error = str(e)
                return

    def finalize(self) -> Iterator[str]:
        """End of stream. Yields a final snapshot if there are any
        unapplied blocks that completed in the last token batch."""
        if self._failed:
            return

        blocks = parse_diff_blocks(self._raw_buffer)
        while self._blocks_applied < len(blocks):
            block = blocks[self._blocks_applied]
            try:
                self._current_code = apply_diff(self._current_code, block)
                self._blocks_applied += 1
                yield self._current_code
            except DiffApplyError as e:
                self._failed = True
                self._error = str(e)
                return

    @property
    def failed(self) -> bool:
        """True if a search/replace block could not be applied."""
        return self._failed

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def result_code(self) -> str:
        """Current code state after all successfully applied blocks."""
        return self._current_code

    @property
    def blocks_applied(self) -> int:
        return self._blocks_applied

    @property
    def raw_response(self) -> str:
        """Full raw LLM response (for parsing growth decision JSON)."""
        return self._raw_buffer
