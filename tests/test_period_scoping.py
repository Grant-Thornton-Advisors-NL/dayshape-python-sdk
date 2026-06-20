"""Tests for :class:`dayshape.Period` and client period scoping (plan.md §7.1).

Two areas:

1. ``Period`` value object — constructors, validation, ``duration``, ``windows``,
   and ``to_wire`` mapping to the wire's ``from``/``to``.
2. Period resolution precedence through the client: per-call ``period=`` over a
   scoped ``client.period(...)``, nested scopes, the "no period anywhere" error
   raised before any I/O, shared transport/auth across scoped queries, and
   relational period inheritance through a fetched model.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from dayshape import Period, QueryError

from conftest import MockBackend, build_client

UTC = timezone.utc


# --------------------------------------------------------------------------- #
# Period constructors
# --------------------------------------------------------------------------- #
def test_between_sets_bounds() -> None:
    start = datetime(2026, 3, 1, tzinfo=UTC)
    end = datetime(2026, 4, 1, tzinfo=UTC)
    p = Period.between(start, end)
    assert p.start == start
    assert p.end == end


def test_year_spans_calendar_year() -> None:
    p = Period.year(2026)
    assert p.start == datetime(2026, 1, 1, tzinfo=UTC)
    assert p.end == datetime(2027, 1, 1, tzinfo=UTC)
    assert p.duration == timedelta(days=365)


def test_fiscal_year_default_is_calendar_year() -> None:
    assert Period.fiscal_year(2026) == Period.year(2026)


def test_fiscal_year_april_start() -> None:
    p = Period.fiscal_year(2026, start_month=4)
    assert p.start == datetime(2026, 4, 1, tzinfo=UTC)
    assert p.end == datetime(2027, 4, 1, tzinfo=UTC)


def test_last_days_with_explicit_now() -> None:
    now = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    p = Period.last_days(7, now=now)
    assert p.end == now
    assert p.start == now - timedelta(days=7)
    assert p.duration == timedelta(days=7)


def test_last_days_default_now_is_recent_and_aware() -> None:
    before = datetime.now(UTC)
    p = Period.last_days(1)
    after = datetime.now(UTC)
    assert p.end.tzinfo is not None
    # The default now() lands between the two samples taken around the call.
    assert before <= p.end <= after
    assert p.duration == timedelta(days=1)


def test_year_accepts_custom_tz() -> None:
    tz = timezone(timedelta(hours=2))
    p = Period.year(2026, tz=tz)
    assert p.start == datetime(2026, 1, 1, tzinfo=tz)


# --------------------------------------------------------------------------- #
# Period validation errors
# --------------------------------------------------------------------------- #
def test_naive_start_raises_value_error() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Period(start=datetime(2026, 1, 1), end=datetime(2026, 2, 1, tzinfo=UTC))


def test_naive_end_raises_value_error() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Period(start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 2, 1))


def test_non_datetime_bound_raises_type_error() -> None:
    with pytest.raises(TypeError):
        Period(start="2026-01-01", end=datetime(2026, 2, 1, tzinfo=UTC))  # type: ignore[arg-type]


def test_start_equal_to_end_raises_value_error() -> None:
    moment = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="must be before end"):
        Period(start=moment, end=moment)


def test_start_after_end_raises_value_error() -> None:
    with pytest.raises(ValueError, match="must be before end"):
        Period(
            start=datetime(2026, 2, 1, tzinfo=UTC),
            end=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_last_days_zero_raises_value_error() -> None:
    with pytest.raises(ValueError, match="n > 0"):
        Period.last_days(0)


def test_last_days_negative_raises_value_error() -> None:
    with pytest.raises(ValueError, match="n > 0"):
        Period.last_days(-5)


def test_last_days_naive_now_raises_value_error() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Period.last_days(3, now=datetime(2026, 6, 20, 12, 0, 0))


def test_fiscal_year_start_month_too_low_raises() -> None:
    with pytest.raises(ValueError, match="1..12"):
        Period.fiscal_year(2026, start_month=0)


def test_fiscal_year_start_month_too_high_raises() -> None:
    with pytest.raises(ValueError, match="1..12"):
        Period.fiscal_year(2026, start_month=13)


# --------------------------------------------------------------------------- #
# Period.windows
# --------------------------------------------------------------------------- #
def test_windows_are_contiguous_and_cover_period() -> None:
    p = Period.between(
        datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 11, tzinfo=UTC)
    )
    windows = list(p.windows(timedelta(days=3)))
    # First starts at the period start, last ends at the period end.
    assert windows[0].start == p.start
    assert windows[-1].end == p.end
    # Back-to-back: each window's end is the next window's start.
    for earlier, later in zip(windows, windows[1:]):
        assert earlier.end == later.start


def test_windows_final_window_is_truncated() -> None:
    p = Period.between(
        datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 11, tzinfo=UTC)
    )
    windows = list(p.windows(timedelta(days=4)))
    # 10 days / 4 → windows of 4, 4, 2 days.
    assert [w.duration for w in windows] == [
        timedelta(days=4),
        timedelta(days=4),
        timedelta(days=2),
    ]


def test_windows_size_larger_than_period_yields_single_window() -> None:
    p = Period.year(2026)
    windows = list(p.windows(timedelta(days=1000)))
    assert len(windows) == 1
    assert windows[0].start == p.start
    assert windows[0].end == p.end


def test_windows_zero_size_raises_value_error() -> None:
    p = Period.year(2026)
    with pytest.raises(ValueError, match="positive"):
        list(p.windows(timedelta(0)))


def test_windows_negative_size_raises_value_error() -> None:
    p = Period.year(2026)
    with pytest.raises(ValueError, match="positive"):
        list(p.windows(timedelta(days=-1)))


# --------------------------------------------------------------------------- #
# Period.to_wire
# --------------------------------------------------------------------------- #
def test_to_wire_maps_start_end_to_from_to_with_trailing_z() -> None:
    p = Period.year(2026)
    wire = p.to_wire()
    assert set(wire) == {"from", "to"}
    assert wire["from"] == "2026-01-01T00:00:00.000Z"
    assert wire["to"] == "2027-01-01T00:00:00.000Z"


def test_to_wire_includes_milliseconds() -> None:
    start = datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)
    end = datetime(2026, 1, 3, tzinfo=UTC)
    wire = Period.between(start, end).to_wire()
    assert wire["from"] == "2026-01-02T03:04:05.678Z"


def test_to_wire_converts_non_utc_to_utc_z() -> None:
    tz = timezone(timedelta(hours=2))
    # 02:00 +02:00 is midnight UTC.
    start = datetime(2026, 1, 1, 2, 0, 0, tzinfo=tz)
    end = datetime(2026, 1, 2, tzinfo=UTC)
    wire = Period.between(start, end).to_wire()
    assert wire["from"] == "2026-01-01T00:00:00.000Z"


def test_period_is_frozen() -> None:
    p = Period.year(2026)
    with pytest.raises(Exception):
        p.start = datetime(2025, 1, 1, tzinfo=UTC)  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Scoping: period resolution precedence through the client
# --------------------------------------------------------------------------- #
def _from_to(request) -> tuple[str, str]:
    body = json.loads(request.content)
    return body["from"], body["to"]


def _v2_requests(backend: MockBackend) -> list:
    return [r for r in backend.requests if "/reporting/v2" in r.url.path]


async def test_no_period_anywhere_raises_query_error_before_io() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with pytest.raises(QueryError, match="reporting period"):
            client.bookings.list(dimensions=["TaskId"])
    # The error is raised during query construction, before any v2 request.
    assert backend.v2_calls == 0
    assert _v2_requests(backend) == []


async def test_scoped_client_supplies_the_period() -> None:
    backend = MockBackend()
    scope = Period.year(2026)
    async with build_client(backend) as client:
        with client.period(scope) as c:
            await c.bookings.list(dimensions=["TaskId"])
    reqs = _v2_requests(backend)
    assert len(reqs) == 1
    assert _from_to(reqs[0]) == ("2026-01-01T00:00:00.000Z", "2027-01-01T00:00:00.000Z")


async def test_per_call_period_overrides_scope() -> None:
    backend = MockBackend()
    scope = Period.year(2026)
    override = Period.year(2030)
    async with build_client(backend) as client:
        with client.period(scope) as c:
            await c.bookings.list(dimensions=["TaskId"], period=override)
    reqs = _v2_requests(backend)
    assert len(reqs) == 1
    # The per-call period wins over the scoped one.
    assert _from_to(reqs[0]) == ("2030-01-01T00:00:00.000Z", "2031-01-01T00:00:00.000Z")


async def test_per_call_period_works_without_any_scope() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        await client.bookings.list(dimensions=["TaskId"], period=Period.year(2028))
    reqs = _v2_requests(backend)
    assert len(reqs) == 1
    assert _from_to(reqs[0]) == ("2028-01-01T00:00:00.000Z", "2029-01-01T00:00:00.000Z")


async def test_nested_scope_inner_wins() -> None:
    backend = MockBackend()
    outer = Period.year(2026)
    inner = Period.year(2040)
    async with build_client(backend) as client:
        with client.period(outer) as c1:
            with c1.period(inner) as c2:
                await c2.bookings.list(dimensions=["TaskId"])
    reqs = _v2_requests(backend)
    assert len(reqs) == 1
    assert _from_to(reqs[0]) == ("2040-01-01T00:00:00.000Z", "2041-01-01T00:00:00.000Z")


async def test_period_start_end_keywords_build_scope() -> None:
    backend = MockBackend()
    start = datetime(2026, 5, 1, tzinfo=UTC)
    end = datetime(2026, 6, 1, tzinfo=UTC)
    async with build_client(backend) as client:
        with client.period(start=start, end=end) as c:
            await c.bookings.list(dimensions=["TaskId"])
    reqs = _v2_requests(backend)
    assert _from_to(reqs[0]) == (
        "2026-05-01T00:00:00.000Z",
        "2026-06-01T00:00:00.000Z",
    )


def test_period_requires_a_period_or_start_end() -> None:
    backend = MockBackend()
    client = build_client(backend)
    with pytest.raises(ValueError, match="requires a Period"):
        client.period()


async def test_scoped_client_shares_one_token_call() -> None:
    backend = MockBackend()
    scope = Period.year(2026)
    async with build_client(backend) as client:
        with client.period(scope) as c:
            await c.bookings.list(dimensions=["TaskId"])
            await c.bookings.list(dimensions=["TaskId"])
            await c.workers.list(dimensions=["WorkerId"])
    # Several scoped queries share one transport/auth → exactly one token call.
    assert backend.token_calls == 1
    assert backend.v2_calls == 3


async def test_outer_and_inner_scope_share_one_token_call() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(Period.year(2026)) as c1:
            await c1.bookings.list(dimensions=["TaskId"])
            with c1.period(Period.year(2027)) as c2:
                await c2.bookings.list(dimensions=["TaskId"])
    assert backend.token_calls == 1
    assert backend.v2_calls == 2


# --------------------------------------------------------------------------- #
# Relational period inheritance
# --------------------------------------------------------------------------- #
async def test_relation_inherits_scoped_period() -> None:
    backend = MockBackend()
    scope = Period.between(
        datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC)
    )
    async with build_client(backend) as client:
        with client.period(scope) as c:
            workers = await c.workers.list(dimensions=["WorkerId"])
            worker = workers[0]
            assert worker.id is not None
            # No period passed: the hop inherits the period that produced the worker.
            jobs = await worker.jobs()
    assert jobs is not None
    # Two v2 calls: the worker listing, then the jobs relation.
    reqs = _v2_requests(backend)
    assert len(reqs) == 2
    # The relation's outgoing query carries the inherited period.
    assert _from_to(reqs[1]) == (
        "2026-07-01T00:00:00.000Z",
        "2026-08-01T00:00:00.000Z",
    )


async def test_relation_explicit_period_overrides_inherited() -> None:
    backend = MockBackend()
    scope = Period.year(2026)
    async with build_client(backend) as client:
        with client.period(scope) as c:
            worker = (await c.workers.list(dimensions=["WorkerId"]))[0]
            await worker.jobs(period=Period.year(2031))
    reqs = _v2_requests(backend)
    assert _from_to(reqs[1]) == (
        "2031-01-01T00:00:00.000Z",
        "2032-01-01T00:00:00.000Z",
    )
