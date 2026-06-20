"""Explicit date-window chunking for large ranges (plan.md §5.3).

Chunking manages payload size and the server's 15-minute ceiling; it is *off by
default* because boundary duplicates and broken global ordering are correctness
hazards the caller must own (the rate-limit gate, §3.5, is the orthogonal
concern). ``chunk=`` accepts a :class:`~datetime.timedelta`, an ``int`` number of
days, or ``"auto"`` — which sizes windows from the range span (≈quarterly).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

from .exceptions import ChunkingError
from .period import Period

#: The ``"auto"`` heuristic target window length (one quarter).
_AUTO_TARGET = timedelta(days=92)


@dataclass(frozen=True, slots=True)
class ChunkSpec:
    """A resolved chunking specification. ``auto`` derives size from the period."""

    size: timedelta | None
    auto: bool

    @classmethod
    def parse(
        cls, value: "timedelta | int | str | ChunkSpec | None"
    ) -> "ChunkSpec | None":
        if value is None:
            return None
        if isinstance(value, ChunkSpec):
            return value
        if isinstance(value, str):
            if value == "auto":
                return cls(size=None, auto=True)
            raise ChunkingError(
                f"Unknown chunk spec {value!r}; use a timedelta, an int (days), or 'auto'."
            )
        if isinstance(value, bool):  # bool is an int subclass — reject explicitly
            raise ChunkingError("chunk must be a timedelta, int (days), or 'auto'.")
        if isinstance(value, int):
            if value <= 0:
                raise ChunkingError("chunk size in days must be positive.")
            return cls(size=timedelta(days=value), auto=False)
        if isinstance(value, timedelta):
            if value <= timedelta(0):
                raise ChunkingError("chunk size must be positive.")
            return cls(size=value, auto=False)
        raise ChunkingError(f"Cannot interpret {value!r} as a chunk spec.")

    def windows(self, period: Period) -> list[Period]:
        """The contiguous sub-periods this spec produces over ``period``."""
        size = self._auto_size(period) if self.auto else self.size
        assert size is not None  # parse() guarantees a concrete size unless auto
        return list(period.windows(size))

    @staticmethod
    def _auto_size(period: Period) -> timedelta:
        duration = period.duration
        if duration <= _AUTO_TARGET:
            return duration
        windows = max(1, math.ceil(duration / _AUTO_TARGET))
        return duration / windows


__all__ = ["ChunkSpec"]
