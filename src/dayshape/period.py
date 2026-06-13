"""The :class:`Period` temporal-scope value object (plan.md §7.1).

The Reporting API's ``from``/``to`` is mandatory on every report run. Rather than
thread it through every signature, the SDK models it once as an immutable,
validated ``Period`` that can be bound to the client (``client.period(...)``) or
passed per call. ``start``/``end`` are used in the hand (no keyword-collision
underscore); serialisation maps them to the wire's ``from``/``to``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class Period:
    """A half-open-ish reporting window ``[start, end]``, tz-aware and ordered.

    Both bounds must be timezone-aware and ``start`` must be strictly before
    ``end``. Use the classmethod constructors for the common cases.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        for label, value in (("start", self.start), ("end", self.end)):
            if not isinstance(value, datetime):
                raise TypeError(f"Period.{label} must be a datetime, got {type(value)!r}")
            if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
                raise ValueError(
                    f"Period.{label} must be timezone-aware; got naive {value!r}. "
                    "Attach a tzinfo (e.g. datetime(..., tzinfo=timezone.utc))."
                )
        if self.start >= self.end:
            raise ValueError(f"Period.start ({self.start}) must be before end ({self.end})")

    # -- constructors ------------------------------------------------------- #
    @classmethod
    def between(cls, start: datetime, end: datetime) -> "Period":
        """An explicit ``[start, end]`` window."""
        return cls(start=start, end=end)

    @classmethod
    def year(cls, y: int, *, tz: timezone = timezone.utc) -> "Period":
        """The calendar year ``y`` (Jan 1 00:00:00 to Jan 1 of ``y+1``)."""
        return cls(
            start=datetime(y, 1, 1, tzinfo=tz),
            end=datetime(y + 1, 1, 1, tzinfo=tz),
        )

    @classmethod
    def fiscal_year(
        cls, y: int, *, start_month: int = 1, tz: timezone = timezone.utc
    ) -> "Period":
        """A 12-month fiscal year labelled ``y`` beginning on ``start_month``.

        With the default ``start_month=1`` this is the calendar year. A fiscal year
        starting in, say, April (``start_month=4``) runs from 1 Apr ``y`` to 1 Apr
        ``y+1``.
        """
        if not 1 <= start_month <= 12:
            raise ValueError("start_month must be in 1..12")
        start = datetime(y, start_month, 1, tzinfo=tz)
        end_year = y + 1
        return cls(start=start, end=datetime(end_year, start_month, 1, tzinfo=tz))

    @classmethod
    def last_days(cls, n: int, *, now: datetime | None = None) -> "Period":
        """The window from ``n`` days ago up to ``now`` (UTC by default).

        ``now`` may be supplied for deterministic testing; otherwise the current
        UTC time is used.
        """
        if n <= 0:
            raise ValueError("last_days(n) requires n > 0")
        end = now if now is not None else datetime.now(timezone.utc)
        if end.tzinfo is None:
            raise ValueError("`now` must be timezone-aware")
        return cls(start=end - timedelta(days=n), end=end)

    # -- derived ------------------------------------------------------------ #
    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def windows(self, size: timedelta) -> Iterator["Period"]:
        """Yield contiguous sub-windows of length ``size`` covering this period.

        Windows are half-open and back-to-back (``w[n].end == w[n+1].start``); the
        final window is truncated at ``self.end``. Used by the chunking layer
        (plan.md §5.3).
        """
        if size <= timedelta(0):
            raise ValueError("window size must be positive")
        cursor = self.start
        while cursor < self.end:
            nxt = min(cursor + size, self.end)
            yield Period(start=cursor, end=nxt)
            cursor = nxt

    # -- wire --------------------------------------------------------------- #
    def to_wire(self) -> dict[str, str]:
        """Map to the wire's ``{"from": ..., "to": ...}`` ISO-8601 pair."""
        return {"from": _iso(self.start), "to": _iso(self.end)}


def _iso(dt: datetime) -> str:
    """ISO-8601 with milliseconds and a trailing ``Z`` for UTC (matches examples)."""
    as_utc = dt.astimezone(timezone.utc)
    return as_utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{as_utc.microsecond // 1000:03d}Z"


__all__ = ["Period"]
