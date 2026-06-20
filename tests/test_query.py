"""Tests for ``ReportQuery`` — targets 100% branch coverage of ``_query.py``."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from dayshape._chunking import ChunkSpec
from dayshape._query import ReportQuery
from dayshape.exceptions import QueryError
from dayshape.period import Period
from dayshape.reports.query import Dimension, QueryMessageV2, Sort
from dayshape.reports.result import ReportResult, ResultMeta

YEAR = Period.year(2026)


def query(dims: tuple[str, ...] = ("TaskId",)) -> QueryMessageV2:
    return QueryMessageV2(
        report_id="TaskListing",
        from_=YEAR.start,
        to=YEAR.end,
        dimensions=[Dimension(d) for d in dims],
    )


def result(rows: list[list[Any]], **meta: Any) -> ReportResult:
    return ReportResult(rows=rows, index={"TaskId": 0}, meta=ResultMeta(**meta))


class FakeRunner:
    def __init__(self, make: Any = None, results: list[ReportResult] | None = None) -> None:
        self.runs: list[QueryMessageV2] = []
        self.saved_runs = 0
        self._make = make
        self._results = results
        self._i = 0

    async def run(self, q: QueryMessageV2) -> ReportResult:
        self.runs.append(q)
        if self._make is not None:
            return self._make(q, len(self.runs) - 1)
        assert self._results is not None
        r = self._results[min(self._i, len(self._results) - 1)]
        self._i += 1
        return r

    async def run_saved(self, report_hash: str) -> ReportResult:
        self.saved_runs += 1
        assert self._results is not None
        return self._results[0]


def make_query(runner: Any, **kw: Any) -> ReportQuery[int]:
    kw.setdefault("query", query())
    kw.setdefault("period", YEAR)
    return ReportQuery(runner=runner, decode=lambda rec: rec["TaskId"], **kw)


# --------------------------------------------------------------------------- #
async def test_await_equals_all_equals_list() -> None:
    runner = FakeRunner(results=[result([[1], [2], [3]], record_count=3)])
    q = make_query(runner)
    assert await q == [1, 2, 3]
    assert await q.all() == [1, 2, 3]
    assert len(runner.runs) == 2  # two consumptions → two executions


async def test_async_for_streams_and_break_stops_fetching() -> None:
    runner = FakeRunner(make=lambda _q, i: result([[100 + i]], record_count=1))
    q = make_query(runner, chunk=ChunkSpec.parse("auto"))
    out = []
    async for row in q:
        out.append(row)
        break
    assert out == [100]
    assert len(runner.runs) == 1  # broke before fetching later windows


async def test_double_consumption_reruns() -> None:
    runner = FakeRunner(results=[result([[1]], record_count=1)])
    q = make_query(runner)
    await q
    await q
    assert len(runner.runs) == 2


async def test_first_and_empty_first() -> None:
    runner = FakeRunner(results=[result([[7]], record_count=1)])
    assert await make_query(runner).first() == 7
    empty = FakeRunner(results=[result([], record_count=0)])
    assert await make_query(empty).first() is None


async def test_all_respects_max_rows() -> None:
    runner = FakeRunner(results=[result([[1], [2], [3], [4]], record_count=4)])
    assert await make_query(runner).all(max_rows=2) == [1, 2]


async def test_count_uses_identity_dimension() -> None:
    runner = FakeRunner(results=[result([], record_count=99)])
    q = make_query(runner, identity_dimension="TaskId")
    assert await q.count() == 99
    assert [d.dimension_id for d in runner.runs[0].dimensions] == ["TaskId"]


async def test_count_falls_back_to_first_dimension() -> None:
    runner = FakeRunner(results=[result([], record_count=5)])
    q = make_query(runner, query=query(("TaskId", "TaskStart")))
    assert await q.count() == 5


async def test_count_without_dimension_raises() -> None:
    runner = FakeRunner(results=[result([], record_count=0)])
    q = make_query(runner, query=query(()))
    with pytest.raises(QueryError):
        await q.count()


async def test_count_on_saved_report() -> None:
    runner = FakeRunner(results=[result([], record_count=12)])
    q = ReportQuery(runner=runner, decode=lambda r: r, saved_hash="abc")
    assert await q.count() == 12
    assert runner.saved_runs == 1


async def test_to_records_returns_dicts() -> None:
    runner = FakeRunner(results=[result([[1]], record_count=1)])
    rows = await make_query(runner).to_records()
    assert rows == [{"TaskId": 1}]


async def test_with_refiners_are_immutable() -> None:
    runner = FakeRunner(make=lambda _q, i: result([[i]], record_count=1))
    base = make_query(runner)
    chunked = base.with_chunk(120)
    assert base._chunk is None and chunked._chunk is not None
    other = Period.year(2025)
    assert base.with_period(other)._period == other and base._period == YEAR
    assert base.with_dedupe("TaskId")._dedupe_on == "TaskId"


async def test_meta_dedupe_and_cache_age_across_windows() -> None:
    older = datetime(2026, 1, 1, 7, tzinfo=timezone.utc)
    mid = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    rowsets = [[[1], [2]], [[2], [3]], [[3], [4]], [[4], [5]]]
    metas = [
        ResultMeta(record_count=2, oldest_cache_age=mid, report_display_name="R",
                   report_started=older, dimension_display_names={"TaskId": "Task"}),
        ResultMeta(record_count=2, oldest_cache_age=older, report_display_name="R"),  # smaller → updates
        ResultMeta(record_count=2, oldest_cache_age=newer),  # larger → skipped
        ResultMeta(record_count=None, oldest_cache_age=None),  # None → outer skip
    ]

    def make(_q: Any, i: int) -> ReportResult:
        return ReportResult(rows=rowsets[i], index={"TaskId": 0}, meta=metas[i])

    runner = FakeRunner(make=make)
    q = make_query(runner, chunk=ChunkSpec.parse(100), dedupe_on="TaskId")
    rows = await q
    assert rows == [1, 2, 3, 4, 5]  # duplicates across window boundaries dropped
    assert q.meta.record_count == 6  # summed (None window skipped)
    assert q.meta.completed_windows == 4
    assert q.meta.oldest_cache_age == older  # the earliest across windows
    assert q.meta.report_display_name == "R"
    assert q.meta.dimension_display_names == {"TaskId": "Task"}


def _sorted_query() -> QueryMessageV2:
    return QueryMessageV2(
        report_id="TaskListing",
        from_=YEAR.start,
        to=YEAR.end,
        dimensions=[Dimension("TaskId", order=Sort.ASC)],
    )


async def test_with_chunk_rejects_sorted_query() -> None:
    runner = FakeRunner(results=[result([[1]])])
    q = make_query(runner, query=_sorted_query())
    with pytest.raises(QueryError):
        q.with_chunk("auto")


async def test_with_chunk_allows_sorted_when_unordered() -> None:
    runner = FakeRunner(results=[result([[1]])])
    q = make_query(runner, query=_sorted_query(), allow_unordered=True)
    assert q.with_chunk("auto")._chunk is not None  # no QueryError


async def test_with_chunk_none_is_noop() -> None:
    runner = FakeRunner(results=[result([[1]])])
    assert make_query(runner).with_chunk(None)._chunk is None


async def test_with_chunk_on_saved_query_is_allowed() -> None:
    runner = FakeRunner(results=[result([[1]])])
    q: ReportQuery[dict[str, Any]] = ReportQuery(
        runner=runner, decode=lambda r: r, saved_hash="h"
    )
    assert q.with_chunk("auto")._chunk is not None  # query is None → no guard


async def test_saved_query_consumption() -> None:
    runner = FakeRunner(results=[result([[1], [2]], record_count=2)])
    q: ReportQuery[dict[str, Any]] = ReportQuery(
        runner=runner, decode=lambda rec: rec, saved_hash="hash-123"
    )
    rows = await q
    assert rows == [{"TaskId": 1}, {"TaskId": 2}]
    assert runner.saved_runs == 1


async def test_period_none_runs_query_as_is() -> None:
    runner = FakeRunner(results=[result([[1]], record_count=1)])
    q = make_query(runner, period=None)
    assert await q == [1]
    assert len(runner.runs) == 1


async def test_missing_query_raises_on_consume() -> None:
    runner = FakeRunner(results=[result([[1]])])
    q = ReportQuery(runner=runner, decode=lambda r: r, query=None, period=YEAR)
    with pytest.raises(QueryError):
        await q
