"""
Pipeline Event Emitter

Utility for tracking and emitting pipeline stage events.
"""

from __future__ import annotations

import time

from sac.types import StageSnapshot, StageStatus


class PipelineEmitter:
    """Tracks pipeline stages with timing."""

    def __init__(self) -> None:
        self.stages: list[StageSnapshot] = []
        self._start_times: dict[str, float] = {}

    def start(self, name: str) -> None:
        """Mark a stage as running."""
        self._start_times[name] = time.monotonic()
        self.stages.append(StageSnapshot(name=name, status=StageStatus.RUNNING))

    def complete(self, name: str) -> None:
        """Mark a stage as completed with duration."""
        start = self._start_times.pop(name, None)
        duration = (time.monotonic() - start) if start else None
        for stage in self.stages:
            if stage.name == name:
                stage.status = StageStatus.COMPLETED
                stage.duration = duration
                break

    def error(self, name: str) -> None:
        """Mark a stage as errored."""
        start = self._start_times.pop(name, None)
        duration = (time.monotonic() - start) if start else None
        for stage in self.stages:
            if stage.name == name:
                stage.status = StageStatus.ERROR
                stage.duration = duration
                break
