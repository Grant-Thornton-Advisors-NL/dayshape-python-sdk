"""Regression tests for the integration-feedback issues (#3–#10).

Each test maps to a GitHub issue and exercises the public SDK surface against the
``httpx.MockTransport`` seam (see ``conftest``). Nothing here touches the network.
"""

from __future__ import annotations

import json
import warnings
from typing import Any

import httpx
import pytest

import dayshape
from dayshape import (
    CatalogueReport,
    DayshapeClient,
    Period,
    ReportDrift,
    UnknownDimensionError,
    WorkerUtilisation,
)
from dayshape.dims import AvailabilityDim, TaskDim, WorkerDim
from dayshape.exceptions import QueryError
from dayshape.reports.metadata import ReportMetadata

from conftest import build_client, make_envelope, make_jwt

PERIOD = Period.fiscal_year(2026)


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
def _token_or(path: str) -> httpx.Response | None:
    if path.endswith("/reporting/token"):
        return httpx.Response(200, text=make_jwt())
    return None


def make_v2_handler(
    rows_for: Any,
    *,
    metadata_for: Any = None,
) -> Any:
    """A handler that echoes a custom row set for ``/v2`` and optional metadata.

    ``rows_for(requested_dims)`` returns the ``(dims, rows)`` to put in the
    envelope; ``metadata_for(report_id)`` (optional) returns a metadata dict.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        tok = _token_or(path)
        if tok is not None:
            return tok
        if path.endswith("/metadata"):
            if metadata_for is None:
                return httpx.Response(
                    200, json={"dimensions": [], "filterGroupDefinitions": []}
                )
            report_id = request.url.params.get("reportId")
            doc = metadata_for(report_id)
            if isinstance(doc, httpx.Response):
                return doc
            return httpx.Response(
                200, json=doc, headers={"Api-Supported-Versions": "2.0"}
            )
        if "/reporting/v2" in path:
            body = json.loads(request.content)
            requested = [d["dimensionId"] for d in body.get("dimensions", [])]
            dims, rows = rows_for(requested)
            return httpx.Response(200, json=make_envelope(dims, rows))
        return httpx.Response(404, text="unhandled")

    return handler


def _md_doc(dimension_ids: list[str]) -> dict[str, Any]:
    return {
        "dimensions": [{"dimensionId": d} for d in dimension_ids],
        "filterGroupDefinitions": [],
    }


def _cell(dim: str, row: int = 0) -> Any:
    """A well-typed cell per dimension, mirroring ``conftest.default_cell``.

    Returning the right wire type (int ids, ISO dates, float hours) keeps the
    entity models from emitting their own best-effort decode warnings, so a test
    can assert specifically about *dimension* warnings.
    """
    if dim.endswith(("Id", "Rank")):
        return 100 + row
    if "Date" in dim or "Start" in dim or "End" in dim:
        return "2026-01-10T09:00:00.000Z"
    if dim.endswith(("Hours", "Duration")):
        return 1.5
    return f"{dim}-{row}"


# --------------------------------------------------------------------------- #
# Issue #3 — unknown/unsupported dimensions no longer return None silently
# --------------------------------------------------------------------------- #
def _drop(drop: set[str]) -> Any:
    def rows_for(requested: list[str]) -> tuple[list[str], list[list[Any]]]:
        kept = [d for d in requested if d not in drop]
        return kept, [[_cell(d) for d in kept]]

    return rows_for


async def test_missing_dimension_warns_by_default() -> None:
    handler = make_v2_handler(_drop({"WorkerEmail"}))
    async with build_client(handler) as client:
        with client.period(PERIOD) as c:
            query = c.workers.list(
                dimensions=[WorkerDim.ID, WorkerDim.NAME, WorkerDim.EMAIL]
            )
            with pytest.warns(UserWarning, match="WorkerEmail"):
                rows = await query
    assert rows  # rows still decode (best-effort), the warning is the signal


async def test_missing_dimension_errors_in_error_mode() -> None:
    handler = make_v2_handler(_drop({"WorkerEmail"}))
    async with build_client(handler, validate_dimensions="error") as client:
        with client.period(PERIOD) as c:
            query = c.workers.list(
                dimensions=[WorkerDim.ID, WorkerDim.EMAIL]
            )
            with pytest.raises(UnknownDimensionError) as excinfo:
                await query
    err = excinfo.value
    assert isinstance(err, QueryError)  # subclass, so except QueryError still works
    assert err.report_id == "WorkerListing"
    assert "WorkerEmail" in err.dimensions


async def test_missing_dimension_silent_when_off() -> None:
    handler = make_v2_handler(_drop({"WorkerEmail"}))
    async with build_client(handler, validate_dimensions="off") as client:
        with client.period(PERIOD) as c:
            with warnings.catch_warnings():
                warnings.simplefilter("error")  # any warning would fail
                rows = await c.workers.list(
                    dimensions=[WorkerDim.ID, WorkerDim.EMAIL]
                )
    assert rows


async def test_no_warning_when_all_dimensions_returned() -> None:
    handler = make_v2_handler(_drop(set()))  # drops nothing
    async with build_client(handler) as client:
        with client.period(PERIOD) as c:
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                rows = await c.workers.list(dimensions=[WorkerDim.ID, WorkerDim.NAME])
    assert rows


async def test_empty_index_does_not_warn() -> None:
    # A zero-column envelope is ambiguous (no data vs unknown report) — no guess.
    def rows_for(requested: list[str]) -> tuple[list[str], list[list[Any]]]:
        return [], []

    async with build_client(make_v2_handler(rows_for)) as client:
        with client.period(PERIOD) as c:
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                rows = await c.workers.list(dimensions=[WorkerDim.ID])
    assert rows == []


async def test_raw_reports_run_validates_dimensions() -> None:
    handler = make_v2_handler(_drop({"TaskBogus"}))
    async with build_client(handler, validate_dimensions="error") as client:
        with client.period(PERIOD) as c:
            query = c.reports.run("TaskListing", dimensions=[TaskDim.ID, "TaskBogus"])
            with pytest.raises(UnknownDimensionError):
                await query


# --------------------------------------------------------------------------- #
# Issue #4 — validate_catalogue() diffs the catalogue against the live server
# --------------------------------------------------------------------------- #
async def test_validate_catalogue_detects_drift_and_unavailable() -> None:
    def metadata_for(report_id: str) -> Any:
        if report_id == "WorkerListing":
            # Drop WorkerEmail from the live server → drift.
            return _md_doc(
                ["WorkerId", "WorkerName", "WorkerFirstName", "WorkerLastName"]
            )
        if report_id == "Availability":
            return _md_doc(["AvailabilityWorkerName", "AvailabilityWorkerGrade"])
        if report_id == "ClientListing":
            return httpx.Response(403, text="permission denied")
        return _md_doc([])

    handler = make_v2_handler(_drop(set()), metadata_for=metadata_for)
    async with build_client(handler) as client:
        report = await client.validate_catalogue(
            report_ids=["WorkerListing", "Availability", "ClientListing"]
        )

    assert isinstance(report, CatalogueReport)
    assert report.ok is False
    by_id = {r.report_id: r for r in report.reports}

    drift = by_id["WorkerListing"]
    assert isinstance(drift, ReportDrift)
    assert drift.available is True
    assert drift.missing_dimensions == frozenset({"WorkerEmail"})
    assert drift.ok is False

    ok = by_id["Availability"]
    assert ok.missing_dimensions == frozenset()
    assert ok.ok is True

    unavailable = by_id["ClientListing"]
    assert unavailable.available is False
    assert "403" in (unavailable.error or "")

    assert {r.report_id for r in report.drifted} == {"WorkerListing"}
    assert {r.report_id for r in report.unavailable} == {"ClientListing"}
    assert report.spec_version == dict(dayshape.SPEC_VERSION)
    assert "DRIFT WorkerListing" in report.summary()


async def test_validate_catalogue_defaults_to_known_reports() -> None:
    seen: list[str] = []

    def metadata_for(report_id: str) -> Any:
        seen.append(report_id)
        return _md_doc([])  # everything "missing" — we only assert coverage here

    handler = make_v2_handler(_drop(set()), metadata_for=metadata_for)
    async with build_client(handler) as client:
        report = await client.validate_catalogue()

    # The default sweep covers the entity façades and the timeseries pivots.
    assert "WorkerListing" in seen
    assert "Availability" in seen
    assert len(report.reports) >= 10


# --------------------------------------------------------------------------- #
# Issue #6 — dedupe_on / chunk reach the timeseries façades
# --------------------------------------------------------------------------- #
async def test_timeseries_forwards_dedupe_on() -> None:
    def rows_for(requested: list[str]) -> tuple[list[str], list[list[Any]]]:
        # Three rows, one worker repeated across "days".
        rows = [
            ["Alice", "2026-01-01"],
            ["Alice", "2026-01-02"],
            ["Alice", "2026-01-03"],
        ]
        return requested, rows

    async with build_client(make_v2_handler(rows_for)) as client:
        with client.period(PERIOD) as c:
            dims = [AvailabilityDim.WORKER_NAME, AvailabilityDim.DATE]
            full = await c.timeseries.availability(dimensions=dims)
            collapsed = await c.timeseries.availability(
                dimensions=dims, dedupe_on=AvailabilityDim.WORKER_NAME
            )
    assert len(full) == 3
    assert len(collapsed) == 1


async def test_timeseries_report_threads_chunk() -> None:
    windows: list[tuple[str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        tok = _token_or(path)
        if tok is not None:
            return tok
        if "/reporting/v2" in path:
            body = json.loads(request.content)
            windows.append((body.get("from"), body.get("to")))
            dims = [d["dimensionId"] for d in body.get("dimensions", [])]
            return httpx.Response(200, json=make_envelope(dims, [[_cell(d) for d in dims]]))
        return httpx.Response(404, text="unhandled")

    async with build_client(handler) as client:
        with client.period(PERIOD) as c:
            await c.timeseries.availability(
                dimensions=[AvailabilityDim.WORKER_NAME], chunk=30
            )
    # A year split into 30-day windows is many requests, not one.
    assert len(windows) > 1


# --------------------------------------------------------------------------- #
# Issue #7 — utilisation_rate() computes a real figure from Availability hours
# --------------------------------------------------------------------------- #
def test_as_float_coerces_tolerantly() -> None:
    from dayshape.resources.timeseries import _as_float

    assert _as_float(8) == 8.0
    assert _as_float(1.5) == 1.5
    assert _as_float("2.5") == 2.5
    assert _as_float("not-a-number") == 0.0
    assert _as_float(None) == 0.0
    assert _as_float(True) == 0.0  # bools are not hours


async def test_utilisation_rate_handles_string_and_null_hours() -> None:
    records = [
        {
            "AvailabilityWorkerName": "Carol",
            "AvailabilityScheduledTaskHours": "4",  # stringy hours
            "AvailabilityWorkHours": "8",
        },
        {
            "AvailabilityWorkerName": "Carol",
            "AvailabilityScheduledTaskHours": None,  # missing cell
            "AvailabilityWorkHours": None,
        },
    ]

    def rows_for(requested: list[str]) -> tuple[list[str], list[list[Any]]]:
        return requested, [[rec.get(d) for d in requested] for rec in records]

    async with build_client(make_v2_handler(rows_for)) as client:
        with client.period(PERIOD) as c:
            result = await c.timeseries.utilisation_rate()
    assert len(result) == 1
    assert result[0].scheduled_hours == 4.0
    assert result[0].work_hours == 8.0
    assert result[0].utilisation == pytest.approx(0.5)


async def test_utilisation_rate_computes_from_availability_hours() -> None:
    records = [
        {
            "AvailabilityWorkerName": "Alice",
            "AvailabilityScheduledTaskHours": 2.0,
            "AvailabilityWorkHours": 8.0,
        },
        {
            "AvailabilityWorkerName": "Alice",
            "AvailabilityScheduledTaskHours": 3.0,
            "AvailabilityWorkHours": 8.0,
        },
        {
            "AvailabilityWorkerName": "Bob",
            "AvailabilityScheduledTaskHours": 0.0,
            "AvailabilityWorkHours": 0.0,
        },
    ]

    def rows_for(requested: list[str]) -> tuple[list[str], list[list[Any]]]:
        rows = [[rec.get(d) for d in requested] for rec in records]
        return requested, rows

    async with build_client(make_v2_handler(rows_for)) as client:
        with client.period(PERIOD) as c:
            result = await c.timeseries.utilisation_rate()

    assert [r.worker for r in result] == ["Alice", "Bob"]
    alice = result[0]
    assert isinstance(alice, WorkerUtilisation)
    assert alice.scheduled_hours == 5.0
    assert alice.work_hours == 16.0
    assert alice.available_hours == 11.0  # work - scheduled (free time)
    assert alice.utilisation == pytest.approx(5.0 / 16.0)
    bob = result[1]
    assert bob.work_hours == 0.0
    assert bob.utilisation is None  # no work hours → undefined, not >100%


# --------------------------------------------------------------------------- #
# Issue #9 — Dim accessors and dimension_ids property
# --------------------------------------------------------------------------- #
def test_dim_id_name_value() -> None:
    assert TaskDim.ID.id == "TaskId"
    assert TaskDim.ID.name == "TaskId"
    assert TaskDim.ID.value == "TaskId"
    # Still a plain str, so it remains usable as a raw id everywhere.
    assert TaskDim.ID == "TaskId"
    assert isinstance(TaskDim.ID.id, str)


def test_dimension_ids_is_property() -> None:
    md = ReportMetadata.model_validate(
        {"dimensions": [{"dimensionId": "TaskId"}, {"dimensionId": "TaskName"}]}
    )
    # Reads like a property — iterable directly, no call.
    assert set(md.dimension_ids) == {"TaskId", "TaskName"}
    assert "TaskId" in md.dimension_ids


# --------------------------------------------------------------------------- #
# Issue #8 — version bump and new public exports
# --------------------------------------------------------------------------- #
def test_version_bumped() -> None:
    assert dayshape.__version__ == "0.2.0"


def test_new_public_exports() -> None:
    for name in (
        "UnknownDimensionError",
        "CatalogueReport",
        "ReportDrift",
        "WorkerUtilisation",
    ):
        assert name in dayshape.__all__
        assert hasattr(dayshape, name)
    assert issubclass(UnknownDimensionError, QueryError)


def test_invalid_validate_dimensions_rejected() -> None:
    with pytest.raises(ValueError, match="validate_dimensions"):
        DayshapeClient(
            base_url="https://x.dayshape.app",
            username="u",
            password="p",
            validate_dimensions="loud",  # type: ignore[arg-type]
        )
