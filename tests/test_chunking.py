"""Tests for ``ChunkSpec`` — the date-window chunking layer (``_chunking.py``).

Covers ``ChunkSpec.parse`` (every accepted form and every rejected form) and
``ChunkSpec.windows`` (auto sizing, fixed timedelta/int sizing, contiguity, and
full coverage of the period). Mirrors the structure/assertion style of
``test_query.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dayshape import ChunkingError, Period
from dayshape._chunking import ChunkSpec

# The "auto" heuristic target (one quarter); kept local so tests don't import a
# private constant but still pin the documented behaviour.
QUARTER = timedelta(days=92)


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# ChunkSpec.parse — accepted forms
# --------------------------------------------------------------------------- #
def test_parse_none_returns_none() -> None:
    assert ChunkSpec.parse(None) is None


def test_parse_existing_chunkspec_is_returned_unchanged() -> None:
    spec = ChunkSpec(size=timedelta(days=7), auto=False)
    assert ChunkSpec.parse(spec) is spec


def test_parse_auto() -> None:
    spec = ChunkSpec.parse("auto")
    assert spec == ChunkSpec(size=None, auto=True)
    assert spec is not None
    assert spec.auto is True
    assert spec.size is None


def test_parse_int_days_positive() -> None:
    spec = ChunkSpec.parse(30)
    assert spec == ChunkSpec(size=timedelta(days=30), auto=False)
    assert spec is not None
    assert spec.auto is False
    assert spec.size == timedelta(days=30)


def test_parse_timedelta_positive() -> None:
    td = timedelta(days=10, hours=6)
    spec = ChunkSpec.parse(td)
    assert spec == ChunkSpec(size=td, auto=False)
    assert spec is not None
    assert spec.size == td
    assert spec.auto is False


# --------------------------------------------------------------------------- #
# ChunkSpec.parse — rejected forms (all raise ChunkingError)
# --------------------------------------------------------------------------- #
def test_parse_unknown_string_raises() -> None:
    with pytest.raises(ChunkingError, match="Unknown chunk spec"):
        ChunkSpec.parse("weekly")


def test_parse_bool_raises_even_though_bool_is_int() -> None:
    # bool is an int subclass; the impl rejects it explicitly before the int path.
    with pytest.raises(ChunkingError, match="timedelta, int"):
        ChunkSpec.parse(True)
    with pytest.raises(ChunkingError):
        ChunkSpec.parse(False)


def test_parse_int_zero_raises() -> None:
    with pytest.raises(ChunkingError, match="must be positive"):
        ChunkSpec.parse(0)


def test_parse_int_negative_raises() -> None:
    with pytest.raises(ChunkingError, match="days must be positive"):
        ChunkSpec.parse(-5)


def test_parse_timedelta_zero_raises() -> None:
    with pytest.raises(ChunkingError, match="must be positive"):
        ChunkSpec.parse(timedelta(0))


def test_parse_timedelta_negative_raises() -> None:
    with pytest.raises(ChunkingError, match="must be positive"):
        ChunkSpec.parse(timedelta(days=-1))


def test_parse_unsupported_type_raises() -> None:
    with pytest.raises(ChunkingError, match="Cannot interpret"):
        ChunkSpec.parse(3.5)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Helpers for windows() assertions
# --------------------------------------------------------------------------- #
def _assert_contiguous_and_covers(windows: list[Period], period: Period) -> None:
    assert windows, "expected at least one window"
    # Covers exactly [start, end].
    assert windows[0].start == period.start
    assert windows[-1].end == period.end
    # Back-to-back: w[n].end == w[n+1].start, strictly increasing, non-empty.
    for w in windows:
        assert w.start < w.end
    for a, b in zip(windows, windows[1:]):
        assert a.end == b.start


# --------------------------------------------------------------------------- #
# ChunkSpec.windows — auto sizing
# --------------------------------------------------------------------------- #
def test_windows_auto_short_period_is_single_window() -> None:
    # A 30-day period is shorter than the ~quarter target → one window == the period.
    period = Period.between(_utc(2026, 1, 1), _utc(2026, 1, 31))
    windows = ChunkSpec.parse("auto").windows(period)  # type: ignore[union-attr]
    assert len(windows) == 1
    assert windows[0] == period
    _assert_contiguous_and_covers(windows, period)


def test_windows_auto_period_equal_to_quarter_is_single_window() -> None:
    # Exactly the target length stays a single window (duration <= target).
    period = Period.between(_utc(2026, 1, 1), _utc(2026, 1, 1) + QUARTER)
    windows = ChunkSpec.parse("auto").windows(period)  # type: ignore[union-attr]
    assert len(windows) == 1
    assert windows[0] == period


def test_windows_auto_long_period_splits_into_quarterly_windows() -> None:
    # A full calendar year (~365d) → 4 windows of ~91 days each, contiguous.
    year = Period.year(2026)
    windows = ChunkSpec.parse("auto").windows(year)  # type: ignore[union-attr]
    assert len(windows) == 4
    _assert_contiguous_and_covers(windows, year)
    # Each window should be close to a quarter (year / 4), never exceeding target.
    for w in windows:
        assert w.duration <= QUARTER
    # The auto size divides the duration evenly; only the last may be truncated.
    sizes = [w.duration for w in windows]
    # First n-1 windows share the same nominal size.
    assert len(set(sizes[:-1])) == 1
    assert sizes[-1] <= sizes[0]


def test_windows_auto_two_year_period_more_windows() -> None:
    period = Period.between(_utc(2026, 1, 1), _utc(2028, 1, 1))  # ~730 days
    windows = ChunkSpec.parse("auto").windows(period)  # type: ignore[union-attr]
    # ceil(730 / 92) == 8 windows.
    assert len(windows) == 8
    _assert_contiguous_and_covers(windows, period)
    for w in windows:
        assert w.duration <= QUARTER


# --------------------------------------------------------------------------- #
# ChunkSpec.windows — fixed sizing
# --------------------------------------------------------------------------- #
def test_windows_fixed_int_days() -> None:
    year = Period.year(2026)  # 365 days
    windows = ChunkSpec.parse(100).windows(year)  # type: ignore[union-attr]
    # 365 / 100 → 4 windows: 100, 100, 100, 65.
    assert len(windows) == 4
    _assert_contiguous_and_covers(windows, year)
    assert [w.duration for w in windows[:3]] == [timedelta(days=100)] * 3
    assert windows[-1].duration == timedelta(days=65)


def test_windows_fixed_timedelta() -> None:
    period = Period.between(_utc(2026, 1, 1), _utc(2026, 1, 11))  # 10 days
    windows = ChunkSpec.parse(timedelta(days=3)).windows(period)  # type: ignore[union-attr]
    # 10 / 3 → 4 windows: 3, 3, 3, 1 (last truncated at end).
    assert len(windows) == 4
    _assert_contiguous_and_covers(windows, period)
    assert [w.duration for w in windows] == [
        timedelta(days=3),
        timedelta(days=3),
        timedelta(days=3),
        timedelta(days=1),
    ]


def test_windows_fixed_size_larger_than_period_is_single_window() -> None:
    period = Period.between(_utc(2026, 1, 1), _utc(2026, 1, 5))  # 4 days
    windows = ChunkSpec.parse(timedelta(days=30)).windows(period)  # type: ignore[union-attr]
    assert len(windows) == 1
    assert windows[0] == period


def test_windows_fixed_size_divides_evenly() -> None:
    period = Period.between(_utc(2026, 1, 1), _utc(2026, 1, 10))  # 9 days
    windows = ChunkSpec.parse(3).windows(period)  # type: ignore[union-attr]
    assert len(windows) == 3
    _assert_contiguous_and_covers(windows, period)
    assert all(w.duration == timedelta(days=3) for w in windows)
