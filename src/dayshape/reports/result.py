"""Decoding of the columnar ``ReportResultMessageV2`` envelope (plan.md §4.5).

The wire response is columnar: ``rows`` is a 2-D array and ``dimensions`` maps
each ``dimensionId`` to its column index. We invert that index map once and zip
each positional row into a ``{dimension_id: cell}`` record — structurally
enforcing the documented best practice that *identifiers are stable, display
names are presentation*. Result metadata (record count, duration, oldest cache
age, display names keyed by id) is surfaced on :class:`ResultMeta`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

import httpx

from ..exceptions import ResponseFormatError

#: Response header carrying the age of the oldest backing cache entry (§3.2).
OLDEST_CACHE_AGE_HEADER = "Dayshape-Oldest-Cache-Age"


def _parse_http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class ResultMeta:
    """Metadata about a report execution, exposed on :pyattr:`ReportQuery.meta`."""

    record_count: int | None = None
    report_duration_ms: int | None = None
    report_display_name: str | None = None
    report_started: datetime | None = None
    oldest_cache_age: datetime | None = None
    #: Dimension id -> localized display name.
    dimension_display_names: dict[str, str] = field(default_factory=dict)
    #: Number of chunk windows fully consumed (chunked queries; §5.3).
    completed_windows: int = 0


@dataclass(slots=True)
class ReportResult:
    """A decoded report response: raw rows plus the dimension index map and meta."""

    rows: list[list[Any]]
    index: dict[str, int]
    meta: ResultMeta

    @classmethod
    def from_envelope(
        cls, data: Any, headers: Mapping[str, str] | httpx.Headers | None = None
    ) -> "ReportResult":
        if not isinstance(data, dict):
            raise ResponseFormatError(
                f"Expected a ReportResultMessageV2 object, got {type(data).__name__}."
            )
        rows = data.get("rows") or []
        index_raw = data.get("dimensions") or {}
        index: dict[str, int] = {str(k): int(v) for k, v in index_raw.items()}
        display_list = data.get("dimensionDisplayNames") or []
        display_by_id: dict[str, str] = {}
        for dim_id, idx in index.items():
            if 0 <= idx < len(display_list):
                display_by_id[dim_id] = display_list[idx]

        cache_age = None
        if headers is not None:
            cache_age = _parse_http_date(headers.get(OLDEST_CACHE_AGE_HEADER))

        meta = ResultMeta(
            record_count=data.get("recordCount"),
            report_duration_ms=data.get("reportDurationMs"),
            report_display_name=data.get("reportDisplayName"),
            report_started=_parse_iso_dt(data.get("reportStarted")),
            oldest_cache_age=cache_age,
            dimension_display_names=display_by_id,
        )
        return cls(rows=list(rows), index=index, meta=meta)

    def iter_records(self) -> Iterator[dict[str, Any]]:
        """Yield each row as a ``{dimension_id: cell}`` mapping."""
        items = list(self.index.items())
        for row in self.rows:
            record: dict[str, Any] = {}
            for dim_id, idx in items:
                if 0 <= idx < len(row):
                    record[dim_id] = row[idx]
            yield record


def _parse_iso_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


__all__ = ["ReportResult", "ResultMeta", "OLDEST_CACHE_AGE_HEADER"]
