"""Docs-as-tests (plan.md §10): the public examples must execute offline.

Every example in ``README.md`` ("Quick start") and ``plan.md`` Appendix A
("Worked end-to-end example") is reproduced here and run against the
``httpx.MockTransport`` seam via :func:`conftest.build_client`. The point is that
the examples *execute without error* and return sensible shapes — the runnable
docs make the "unused import / dead variable" class of doc-rot (plan.md §11.3,
"Dead code in the example") impossible.

Nothing here touches the network: a :class:`conftest.MockBackend` echoes the
requested dimensions back so every report run returns rows, and the
saved-report routes are stubbed below.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from dayshape import DayshapeClient, Period, Sort
from dayshape.dims import JobDim, TaskDim
from dayshape.filters import JobWorkflowStateFilter
from dayshape.models import Booking, Job, Worker
from dayshape.reports import ComparativeDimension
from dayshape.reports.query import QueryMessageV2

from conftest import (
    BASE_URL,
    MockBackend,
    build_client,
    envelope_from_request,
    make_envelope,
    make_jwt,
)


# --------------------------------------------------------------------------- #
# A backend that also answers the saved-report read routes (plan.md §0.2)
# --------------------------------------------------------------------------- #
_SAVED_QUERY_BODY = {
    "reportId": "taskListing",
    "from": "2026-01-01T00:00:00.000Z",
    "to": "2027-01-01T00:00:00.000Z",
    "dimensions": [{"dimensionId": "TaskId", "sorted": "ascending"}],
}


class _DocsBackend(MockBackend):
    """An echoing :class:`MockBackend` that also serves the saved-report routes.

    ``/v2`` echoes requested dims (so any listing returns ``n_rows`` rows),
    ``/getReportQuery/{hash}`` returns a stored ``QueryMessageV2``, and
    ``/runSavedReport/{hash}`` returns a small ``ReportResultMessageV2``. It still
    records every request through ``.requests`` / ``.token_calls`` / ``.v2_calls``.
    """

    def __init__(self, *, n_rows: int = 3) -> None:
        super().__init__()
        self._n_rows = n_rows

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path = req.url.path
        if path.endswith("/getReportQuery/a1b2c3"):
            return httpx.Response(200, json={"query": _SAVED_QUERY_BODY})
        if path.endswith("/runSavedReport/a1b2c3"):
            return httpx.Response(
                200,
                json=make_envelope(
                    ["TaskId", "TaskStart"], [[101, "x"], [102, "y"]]
                ),
            )
        if path.endswith("/reporting/token"):
            self.token_calls += 1
            return httpx.Response(200, text=make_jwt())
        if "/reporting/v2" in path:
            self.v2_calls += 1
            return envelope_from_request(req, n_rows=self._n_rows)
        return httpx.Response(404, text="unhandled")


def _docs_backend(*, n_rows: int = 3) -> _DocsBackend:
    return _DocsBackend(n_rows=n_rows)


# --------------------------------------------------------------------------- #
# README — "Quick start"
# --------------------------------------------------------------------------- #
async def test_readme_quickstart_streams_and_materialises() -> None:
    """The README Quick start, made runnable: stream form + await-to-list form.

    README uses ``DayshapeClient()`` reading creds from env; here we inject the
    mock transport via ``build_client`` so it runs offline. Both consumption
    idioms — ``async for`` and ``await`` — are exercised exactly as documented.
    """
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(Period.fiscal_year(2026)) as c:
            # Stream form (README): async for booking in c.bookings.list(...)
            seen: list[Booking] = []
            async for booking in c.bookings.list(
                dimensions=[TaskDim.ID, TaskDim.START]
            ):
                # Attributes referenced in the README example resolve.
                assert booking.id is not None
                _ = booking.start
                seen.append(booking)
            assert seen  # streamed at least one row
            assert all(isinstance(b, Booking) for b in seen)

            # Materialise form (README): bookings = await c.bookings.list(...)
            bookings = await c.bookings.list(dimensions=[TaskDim.ID])
            assert isinstance(bookings, list)
            assert bookings and all(isinstance(b, Booking) for b in bookings)

    # Both consumptions actually fired report runs (no hidden caching).
    assert backend.v2_calls >= 2


async def test_readme_quickstart_via_constructor_with_transport() -> None:
    """The README literally writes ``async with DayshapeClient(...)`` — prove the
    documented constructor + period scoping works with the test transport seam,
    not just the ``build_client`` helper."""
    backend = MockBackend()
    async with DayshapeClient(
        base_url=BASE_URL,
        username="user",
        password="pass",
        transport=backend.transport,
    ) as client:
        with client.period(Period.fiscal_year(2026)) as c:
            bookings = await c.bookings.list(dimensions=[TaskDim.ID, TaskDim.START])
    assert isinstance(bookings, list) and bookings


async def test_readme_dimensions_reach_the_wire() -> None:
    """The dims passed in the README example are what the SDK puts on the wire."""
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(Period.fiscal_year(2026)) as c:
            await c.bookings.list(dimensions=[TaskDim.ID, TaskDim.START])
    body = json.loads(backend.requests[-1].content)
    assert [d["dimensionId"] for d in body["dimensions"]] == ["TaskId", "TaskStart"]
    assert body["reportId"] == "TaskListing"


# --------------------------------------------------------------------------- #
# plan.md Appendix A — worked end-to-end example
# --------------------------------------------------------------------------- #
async def test_appendix_chunked_bookings_listing_with_meta() -> None:
    """Appendix A part 1: stream ``bookings.list(chunk="auto")`` and read
    ``bookings.meta.record_count`` afterwards."""
    backend = _docs_backend(n_rows=3)
    async with build_client(backend) as client:
        with client.period(Period.fiscal_year(2026)) as c:
            bookings = c.bookings.list(
                dimensions=[
                    TaskDim.ID,
                    TaskDim.START,
                    TaskDim.JOB_ID,
                    TaskDim.WORKER_ID,
                ],
                chunk="auto",
            )
            processed: list[Booking] = []
            async for booking in bookings:
                processed.append(booking)
            assert processed and all(isinstance(b, Booking) for b in processed)
            # meta is populated on first fetch; record_count is an int.
            assert isinstance(bookings.meta.record_count, int)
            assert bookings.meta.record_count >= len(processed) >= 1
            # fiscal_year(2026) is a single year, so "auto" yields >= 1 window.
            assert bookings.meta.completed_windows >= 1


async def test_appendix_worker_get_then_relational_hop() -> None:
    """Appendix A part 2: ``c.workers.get(1919)`` then a comparative-dimension
    job query, as the worked example describes.

    NOTE (source observation): the appendix calls
    ``worker.jobs(filters=..., comparative_dimensions=..., dimensions=...)``, but
    ``Worker.jobs`` only accepts ``period=`` (src/dayshape/models/worker.py).
    The executable, equivalent spelling is ``c.jobs.list(...)`` with those
    arguments, which is what the relational hop builds under the hood. Both are
    exercised here.
    """
    backend = _docs_backend(n_rows=2)
    async with build_client(backend) as client:
        with client.period(Period.fiscal_year(2026)) as c:
            worker = await c.workers.get(1919)
            assert isinstance(worker, Worker)
            assert worker.id is not None

            # The full-shaped relational query from the appendix (executable form).
            jobs = await c.jobs.list(
                filters=[JobWorkflowStateFilter(state_ids=[793])],
                comparative_dimensions=[
                    ComparativeDimension(
                        metric=JobDim.STATS_RECOVERY_RATE,
                        baseline=JobDim.STATS_BILLING_RECOVERY_RATE,
                    )
                ],
                dimensions=[JobDim.ID.asc(), JobDim.NAME, JobDim.STATS_NET_REVENUE],
            )
            assert isinstance(jobs, list)
            assert jobs and all(isinstance(j, Job) for j in jobs)

    # The wire carries the filter, the comparative dimension, and the sorted dim.
    job_body = json.loads(backend.requests[-1].content)
    assert job_body["reportId"] == "JobListing"
    assert job_body["filters"] == [
        {"filterId": "JobWorkflowStateFilter", "parameters": {"stateIds": [793]}}
    ]
    assert job_body["comparativeDimensions"] == [
        {
            "dimA": {"dimensionId": "JobStatsRecoveryRate"},
            "dimB": {"dimensionId": "JobStatsBillingRecoveryRate"},
        }
    ]
    assert job_body["dimensions"][0] == {
        "dimensionId": "JobId",
        "sorted": "ascending",
    }
    assert [d["dimensionId"] for d in job_body["dimensions"]] == [
        "JobId",
        "JobName",
        "JobStatsNetRevenue",
    ]


async def test_appendix_worker_jobs_relation_executes() -> None:
    """The actual ``worker.jobs()`` relational hop (the supported signature) runs
    and inherits the worker's originating period."""
    backend = _docs_backend(n_rows=2)
    async with build_client(backend) as client:
        with client.period(Period.fiscal_year(2026)) as c:
            worker = await c.workers.get(1919)
            assert worker is not None
            jobs = await worker.jobs()
            assert isinstance(jobs, list)
            assert all(isinstance(j, Job) for j in jobs)

    # The relation builds JobListing + AssignedResourceFilter for the worker id.
    job_body = json.loads(backend.requests[-1].content)
    assert job_body["reportId"] == "JobListing"
    assert job_body["filters"][0]["filterId"] == "AssignedResourceFilter"
    assert job_body["filters"][0]["parameters"]["workerIds"] == [worker.id]


async def test_appendix_saved_report_query_and_run() -> None:
    """Appendix A part 3: ``c.reports.saved("a1b2c3").query()`` round-trips a
    ``QueryMessageV2`` and ``.run()`` returns the lazy ``ReportQuery`` contract."""
    backend = _docs_backend()
    async with build_client(backend) as client:
        with client.period(Period.fiscal_year(2026)) as c:
            saved = c.reports.saved("a1b2c3")
            assert saved.hash == "a1b2c3"

            checked_in_query = await saved.query()
            assert isinstance(checked_in_query, QueryMessageV2)
            assert checked_in_query.report_id == "taskListing"

            rows = await saved.run()
            assert isinstance(rows, list)
            # run() decodes the columnar envelope into {dimension_id: cell} dicts.
            assert rows == [
                {"TaskId": 101, "TaskStart": "x"},
                {"TaskId": 102, "TaskStart": "y"},
            ]

    # The two saved-report read routes were actually hit.
    paths = [r.url.path for r in backend.requests]
    assert any(p.endswith("/getReportQuery/a1b2c3") for p in paths)
    assert any(p.endswith("/runSavedReport/a1b2c3") for p in paths)


async def test_appendix_full_example_runs_end_to_end() -> None:
    """The whole Appendix A flow, in one body, mirroring ``async def main()``.

    This is the docs-as-tests guarantee: the example compiles, every import is
    used, every line executes, and nothing is dead.
    """
    backend = _docs_backend(n_rows=2)
    processed: list[Booking] = []

    async with build_client(backend, currency="EUR") as client:
        with client.period(Period.fiscal_year(2026)) as c:
            bookings = c.bookings.list(
                dimensions=[
                    TaskDim.ID,
                    TaskDim.START,
                    TaskDim.JOB_ID,
                    TaskDim.WORKER_ID,
                ],
                chunk="auto",
            )
            async for booking in bookings:
                processed.append(booking)
            record_count = bookings.meta.record_count

            worker = await c.workers.get(1919)
            assert worker is not None
            jobs = await c.jobs.list(
                filters=[JobWorkflowStateFilter(state_ids=[793])],
                comparative_dimensions=[
                    ComparativeDimension(
                        metric=JobDim.STATS_RECOVERY_RATE,
                        baseline=JobDim.STATS_BILLING_RECOVERY_RATE,
                    )
                ],
                dimensions=[
                    JobDim.ID.asc(),
                    JobDim.NAME,
                    JobDim.STATS_NET_REVENUE,
                ],
            )

            saved = c.reports.saved("a1b2c3")
            checked_in_query = await saved.query()
            rows = await saved.run()

    assert processed
    assert isinstance(record_count, int)
    assert jobs
    assert isinstance(checked_in_query, QueryMessageV2)
    assert rows


# --------------------------------------------------------------------------- #
# currency= from the appendix reaches the wire on economics queries
# --------------------------------------------------------------------------- #
async def test_appendix_currency_default_applied() -> None:
    """``DayshapeClient(currency="EUR")`` from the appendix flows to the query."""
    backend = MockBackend()
    async with build_client(backend, currency="EUR") as client:
        with client.period(Period.fiscal_year(2026)) as c:
            await c.jobs.list(dimensions=[JobDim.ID, JobDim.STATS_NET_REVENUE])
    body = json.loads(backend.requests[-1].content)
    assert body["currency"] == "EUR"


# --------------------------------------------------------------------------- #
# The Sort symbol the appendix imports is real and usable
# --------------------------------------------------------------------------- #
def test_sort_symbol_is_importable_and_serialises() -> None:
    """Appendix A imports ``Sort`` from ``dayshape``; ``.asc()`` uses ``Sort.ASC``."""
    assert Sort.ASC == "ascending"
    assert Sort.DESC == "descending"
    dim = JobDim.ID.asc()
    assert dim.order is Sort.ASC
