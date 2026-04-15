"""
TSX chunk filter for streaming pipelines.

Filters raw LLM tokens so that only the TSX code-block contents are forwarded
as `PipelineChunkEvent`s. This exists because different prompts wrap their
output differently — e.g. the `growth` prompt asks the model to emit a JSON
decision block followed by a TSX code block, while the `generate` prompt
asks for TSX only. Downstream consumers (the preview renderer) should only
see TSX tokens, regardless of which pipeline produced them.

Contract:
    - `feed(token)` is called for every raw LLM token. It yields zero or
      more string chunks that are safe to forward as `chunk` events.
    - `finalize()` is called once the LLM stream ends. It yields a fallback
      chunk if no TSX marker was ever seen (so pipelines that stream plain
      code without fences still surface *something* to the UI).
    - The filter never inspects the JSON block or the trailing close fence —
      those are dropped / left to the final response parser (which re-scans
      the full buffered response anyway).
"""

from __future__ import annotations

from typing import Iterator


# Markers the filter considers as the start of a TSX code block. We accept a
# small family of synonyms because LLMs occasionally use `jsx` or `react`
# instead of `tsx` even when the prompt asks for `tsx`. Order matters:
# the longest / most specific marker is checked first so we don't mistake
# `jsx` inside `tsx` for a separate marker.
_OPEN_MARKERS: tuple[str, ...] = ("```tsx", "```jsx", "```react")


class TsxChunkFilter:
    """Stateful filter that converts a raw LLM token stream into TSX chunks."""

    def __init__(self) -> None:
        # Everything we've seen so far but haven't yet decided what to do with.
        # Cleared as soon as the opening fence is consumed.
        self._buffer: str = ""
        # True once we've seen an opening ```tsx / ```jsx / ```react + newline.
        # After this flips, every subsequent token is forwarded verbatim.
        self._opened: bool = False
        # True once at least one chunk has been yielded. Used by `finalize()`
        # to decide whether to emit a fallback chunk when no fence was ever
        # seen (protects us from LLMs that skip the fence entirely).
        self._any_emitted: bool = False

    def feed(self, token: str) -> Iterator[str]:
        """Feed a single raw LLM token. Yields zero or more TSX string chunks.

        Once the opening fence has been consumed, this is effectively a
        pass-through — every token (including eventual close-fence garbage and
        any trailing prose) is yielded as-is. The frontend's silent-streaming
        renderer already knows how to ignore an incomplete / garbled tail,
        and the final `complete` event replaces the streaming buffer with a
        properly parsed `app.code` anyway, so no cleanup is needed here.
        """
        if self._opened:
            self._any_emitted = True
            yield token
            return

        # Still looking for the opening fence. Accumulate and scan.
        self._buffer += token

        earliest_idx = -1
        earliest_marker_len = 0
        for marker in _OPEN_MARKERS:
            idx = self._buffer.find(marker)
            if idx == -1:
                continue
            if earliest_idx == -1 or idx < earliest_idx:
                earliest_idx = idx
                earliest_marker_len = len(marker)

        if earliest_idx == -1:
            # No fence yet — keep buffering silently.
            return

        # Find the newline terminating the opener line. The language tag may
        # have trailing whitespace or extra characters (rare), so we consume
        # up to and including the first `\n` after the marker.
        nl = self._buffer.find("\n", earliest_idx + earliest_marker_len)
        if nl == -1:
            # Opener seen but its line hasn't finished yet (e.g. token stopped
            # mid-way through "```tsx"). Wait for more tokens so we don't leak
            # the language tag as code.
            return

        tail = self._buffer[nl + 1 :]
        self._opened = True
        self._buffer = ""  # drop prelude (JSON envelope, prose, fence line)
        if tail:
            self._any_emitted = True
            yield tail

    def finalize(self) -> Iterator[str]:
        """Flush remaining state at end of stream.

        If we never found a TSX opening fence, emit whatever we've buffered
        as a single fallback chunk so the frontend still receives *something*
        to try rendering. This protects us from LLMs that ignore the prompt
        and emit raw TSX without a code fence.
        """
        if self._any_emitted:
            return
        tail = self._buffer.strip()
        if tail:
            self._any_emitted = True
            yield self._buffer
