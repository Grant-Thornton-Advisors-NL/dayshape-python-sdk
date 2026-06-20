"""Tests for the resource layer (resources/base.py + reports/audit/timeseries).

Targets the ``ResourceClient`` ergonomics (``list``/``by_ids``/``search``/``get``),
the ``RawReportResource`` escape hatch (run/metadata/export/overview/status/saved),
and the ``audit`` / ``timeseries`` namespaces, all driven through a mocked client
and a stubbed HTTP layer. Nothing here touches the network.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from dayshape import Period, ReportMetadata
from dayshape.exceptions import QueryError
from dayshape.models.audit import AuditLogEntry
from dayshape.models.job_task_phase import JobTaskPhase
from dayshape.models.pivot import PivotRow

from conftest import build_client, envelope_from_request, make_jwt, MockBackend

YEAR = Period.year(2026)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _v2_body(request: httpx.Request) -> dict[str, Any]:
    """Decode the JSON body of a ``/v2`` request."""
    return json.loads(request.content)


def _v2_requests(backend: MockBackend) -> list[httpx.Request]:
    """The recorded requests that hit the ``/reporting/v2`` query endpoint."""
    return [r for r in backend.requests if r.url.path.endswith("/reporting/v2")]


def _last_v2_body(backend: MockBackend) -> dict[str, Any]:
    return _v2_body(_v2_requests(backend)[-1])


def _dim_ids(body: dict[str, Any]) -> list[str]:
    return [d["dimensionId"] for d in body.get("dimensions", [])]


# --------------------------------------------------------------------------- #
# list(): default dimensions, period resolution
# --------------------------------------------------------------------------- #
async def test_list_sends_default_dimensions_when_none_given() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.workers.list()
    assert rows  # echoed a row back
    body = _last_v2_body(backend)
    # Worker.default_dimensions, in order.
    assert _dim_ids(body) == [
        "WorkerId",
        "WorkerName",
        "WorkerFirstName",
        "WorkerLastName",
        "WorkerEmail",
    ]
    assert body["reportId"] == "WorkerListing"


async def test_list_honours_explicit_dimensions() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            await c.workers.list(dimensions=["WorkerId", "WorkerEmail"])
    assert _dim_ids(_last_v2_body(backend)) == ["WorkerId", "WorkerEmail"]


async def test_list_without_period_raises_query_error() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        # No scope and no per-call period -> QueryError on build.
        with pytest.raises(QueryError):
            await client.workers.list()


async def test_per_call_period_overrides_scope() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        # Unscoped client, but pass period= explicitly.
        await client.workers.list(period=YEAR, dimensions=["WorkerId"])
    body = _last_v2_body(backend)
    assert body["from"] == "2026-01-01T00:00:00.000Z"
    assert body["to"] == "2027-01-01T00:00:00.000Z"


# --------------------------------------------------------------------------- #
# by_ids(): id filter
# --------------------------------------------------------------------------- #
async def test_by_ids_adds_worker_id_filter() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            await c.workers.by_ids([5, 6, 7])
    body = _last_v2_body(backend)
    filters = body["filters"]
    assert filters == [{"filterId": "WorkerIdFilter", "parameters": {"ids": [5, 6, 7]}}]


async def test_by_ids_preserves_caller_filters_after_id_filter() -> None:
    from dayshape.filters import WorkerEmailFilter

    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            await c.workers.by_ids([5], filters=[WorkerEmailFilter("a@b.com")])
    filters = _last_v2_body(backend)["filters"]
    assert filters[0]["filterId"] == "WorkerIdFilter"
    assert filters[1]["filterId"] == "WorkerEmailFilter"


# --------------------------------------------------------------------------- #
# search(): text filter
# --------------------------------------------------------------------------- #
async def test_search_adds_worker_text_filter() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            await c.workers.search("alice")
    filters = _last_v2_body(backend)["filters"]
    assert filters == [{"filterId": "WorkerTextFilter", "parameters": {"text": "alice"}}]


# --------------------------------------------------------------------------- #
# get(): single model or None
# --------------------------------------------------------------------------- #
async def test_get_returns_single_model() -> None:
    backend = MockBackend()  # default backend echoes one row
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            worker = await c.workers.get(42)
    assert worker is not None
    assert worker.id == 100  # default_cell: WorkerId -> 100 + row(0)
    # get() adds the id filter for the requested entity id.
    filters = _last_v2_body(backend)["filters"]
    assert filters == [{"filterId": "WorkerIdFilter", "parameters": {"ids": [42]}}]


async def test_get_returns_none_when_no_rows() -> None:
    def v2(request: httpx.Request) -> httpx.Response:
        return envelope_from_request(request, n_rows=0)

    backend = MockBackend(v2=v2)
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            result = await c.workers.get(999)
    assert result is None


# --------------------------------------------------------------------------- #
# Resources WITHOUT an id filter (units) -> by_ids/get raise QueryError
# --------------------------------------------------------------------------- #
async def test_units_by_ids_raises_query_error() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            with pytest.raises(QueryError):
                await c.units.by_ids([1, 2])


async def test_units_get_raises_query_error() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            with pytest.raises(QueryError):
                await c.units.get(1)


async def test_units_search_raises_query_error() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            with pytest.raises(QueryError):
                await c.units.search("x")


# --------------------------------------------------------------------------- #
# chunk + sorted dimension -> QueryError; allow_unordered=True accepted
# --------------------------------------------------------------------------- #
async def test_chunk_with_sorted_dimension_raises_query_error() -> None:
    from dayshape.dims import WorkerDim

    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            with pytest.raises(QueryError):
                await c.workers.list(
                    dimensions=[WorkerDim.ID.asc()], chunk="auto"
                )


async def test_chunk_with_sorted_dimension_allowed_with_unordered() -> None:
    from dayshape.dims import WorkerDim

    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            # allow_unordered=True accepts the window-local ordering; consumption
            # succeeds and the sorted dimension is sent on the wire.
            rows = await c.workers.list(
                dimensions=[WorkerDim.ID.asc()],
                chunk="auto",
                allow_unordered=True,
            )
    assert isinstance(rows, list)
    body = _last_v2_body(backend)
    assert body["dimensions"][0] == {"dimensionId": "WorkerId", "sorted": "ascending"}


async def test_chunk_without_sort_is_accepted() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.workers.list(dimensions=["WorkerId"], chunk="auto")
    assert isinstance(rows, list)


# --------------------------------------------------------------------------- #
# Streaming consumption
# --------------------------------------------------------------------------- #
async def test_list_streams_rows() -> None:
    def v2(request: httpx.Request) -> httpx.Response:
        return envelope_from_request(request, n_rows=3)

    backend = MockBackend(v2=v2)
    seen = []
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            async for row in c.workers.list(dimensions=["WorkerId"]):
                seen.append(row)
    assert len(seen) == 3
    assert all(hasattr(r, "id") for r in seen)


# --------------------------------------------------------------------------- #
# RawReportResource.run
# --------------------------------------------------------------------------- #
async def test_reports_run_yields_dict_rows() -> None:
    def v2(request: httpx.Request) -> httpx.Response:
        return envelope_from_request(request, n_rows=2)

    backend = MockBackend(v2=v2)
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.reports.run("TaskListing", dimensions=["TaskId"])
    assert len(rows) == 2
    assert all(isinstance(r, dict) for r in rows)
    assert rows[0]["TaskId"] == 100
    assert _last_v2_body(backend)["reportId"] == "TaskListing"


async def test_reports_run_without_period_raises() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with pytest.raises(QueryError):
            await client.reports.run("TaskListing", dimensions=["TaskId"])


async def test_reports_run_chunk_sorted_raises() -> None:
    from dayshape.dims import TaskDim

    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            with pytest.raises(QueryError):
                await c.reports.run(
                    "TaskListing", dimensions=[TaskDim.ID.asc()], chunk="auto"
                )


# --------------------------------------------------------------------------- #
# RawReportResource.metadata
# --------------------------------------------------------------------------- #
async def test_reports_metadata_returns_report_metadata() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/reporting/token"):
            return httpx.Response(200, text=make_jwt())
        if path.endswith("/metadata"):
            captured["params"] = dict(request.url.params)
            return httpx.Response(
                200,
                json={
                    "dimensions": [
                        {"dimensionId": "TaskId", "displayName": "Booking"},
                        {"dimensionId": "TaskName", "displayName": "Name"},
                    ],
                    "filterGroupDefinitions": [],
                },
            )
        return httpx.Response(404, text="unhandled")

    async with build_client(handler) as client:
        md = await client.reports.metadata("TaskListing")
    assert isinstance(md, ReportMetadata)
    assert md.dimension_ids() == frozenset({"TaskId", "TaskName"})
    # reportId is sent as a query parameter on the GET.
    assert captured["params"]["reportId"] == "TaskListing"


async def test_reports_metadata_passes_sub_type() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/reporting/token"):
            return httpx.Response(200, text=make_jwt())
        if path.endswith("/metadata"):
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, json={"dimensions": [], "filterGroupDefinitions": []})
        return httpx.Response(404, text="unhandled")

    async with build_client(handler) as client:
        await client.reports.metadata("TaskListing", sub_type=3)
    assert captured["params"]["reportSubTypeId"] == "3"


# --------------------------------------------------------------------------- #
# RawReportResource.export
# --------------------------------------------------------------------------- #
def _export_handler(payload: bytes) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/reporting/token"):
            return httpx.Response(200, text=make_jwt())
        if path.endswith("/export"):
            return httpx.Response(200, content=payload)
        return httpx.Response(404, text="unhandled")

    return handler


async def test_reports_export_writes_to_dest_path(tmp_path: Any) -> None:
    payload = b"PK\x03\x04 fake xlsx bytes"
    dest = tmp_path / "x.xlsx"
    async with build_client(_export_handler(payload)) as client:
        result = await client.reports.export(
            "TaskListing", period=YEAR, dest=dest
        )
    assert result is None  # writing to a dest returns None
    assert dest.read_bytes() == payload


async def test_reports_export_returns_bytes_when_dest_none() -> None:
    payload = b"PK\x03\x04 inline xlsx"
    async with build_client(_export_handler(payload)) as client:
        result = await client.reports.export("TaskListing", period=YEAR, dest=None)
    assert result == payload


async def test_reports_export_writes_to_io_buffer() -> None:
    import io

    payload = b"buffer-bytes"
    buf = io.BytesIO()
    async with build_client(_export_handler(payload)) as client:
        result = await client.reports.export("TaskListing", period=YEAR, dest=buf)
    assert result is None
    assert buf.getvalue() == payload


# --------------------------------------------------------------------------- #
# RawReportResource.overview / status / saved
# --------------------------------------------------------------------------- #
async def test_reports_overview_hits_overview_path() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/reporting/token"):
            return httpx.Response(200, text=make_jwt())
        if request.url.path.endswith("/reportsOverview"):
            return httpx.Response(200, json={"reports": ["TaskListing"]})
        return httpx.Response(404, text="unhandled")

    async with build_client(handler) as client:
        overview = await client.reports.overview()
    assert overview == {"reports": ["TaskListing"]}
    assert any(p.endswith("/Info/reportsOverview") for p in paths)


async def test_reports_status_returns_true() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/reporting/token"):
            return httpx.Response(200, text=make_jwt())
        if request.url.path.endswith("/status"):
            return httpx.Response(200, text="ok")
        return httpx.Response(404, text="unhandled")

    async with build_client(handler) as client:
        ok = await client.reports.status()
    assert ok is True
    assert any(p.endswith("/status") for p in paths)


async def test_reports_saved_runs_saved_report() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/reporting/token"):
            return httpx.Response(200, text=make_jwt())
        if "/runSavedReport/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "recordCount": 1,
                    "reportDurationMs": 1,
                    "dimensions": {"TaskId": 0},
                    "dimensionDisplayNames": ["Booking"],
                    "rows": [[7]],
                },
            )
        return httpx.Response(404, text="unhandled")

    async with build_client(handler) as client:
        ref = client.reports.saved("deadbeef")
        assert ref.hash == "deadbeef"
        rows = await ref.run()
    assert rows == [{"TaskId": 7}]
    assert any("/runSavedReport/deadbeef" in p for p in paths)


# --------------------------------------------------------------------------- #
# Audit namespace
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("method", "report_id"),
    [
        ("jobs", "LogListingJob"),
        ("bookings", "LogListingTask"),
        ("workers", "LogListingWorker"),
        ("job_groups", "LogListingJobGroup"),
        ("traits", "LogListingTrait"),
        ("unavailabilities", "LogListingUnavailability"),
        ("users", "LogListingUser"),
        ("settings", "LogListingSetting"),
        ("workflow", "LogListingWorkflow"),
        ("grades", "LogListingGrade"),
        ("suggestions", "LogListingSuggestion"),
        ("custom_members", "LogListingCustomMember"),
    ],
)
async def test_audit_methods_run_matching_report(method: str, report_id: str) -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await getattr(c.audit, method)()
    assert rows  # echoed a row
    assert all(isinstance(r, AuditLogEntry) for r in rows)
    assert _last_v2_body(backend)["reportId"] == report_id


async def test_audit_uses_default_dimensions() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            await c.audit.jobs()
    assert _dim_ids(_last_v2_body(backend)) == [
        "LogJobId",
        "LogJobName",
        "LogActionTime",
        "LogOperation",
        "LogActor",
    ]


async def test_audit_row_exposes_typed_and_dynamic_fields() -> None:
    def v2(request: httpx.Request) -> httpx.Response:
        return envelope_from_request(
            request,
            n_rows=1,
            cell=lambda d, r: "2026-01-01T09:00:00.000Z"
            if d == "LogActionTime"
            else f"{d}-{r}",
        )

    backend = MockBackend(v2=v2)
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.audit.jobs()
    entry = rows[0]
    # LogActionTime is a date-ish cell -> parsed onto the declared field.
    assert entry.action_time is not None
    # LogJobName flows through model_extra (dynamic column).
    assert entry.field("LogJobName") == "LogJobName-0"


async def test_audit_accepts_explicit_dimensions() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            await c.audit.workers(dimensions=["LogWorkerId"])
    assert _dim_ids(_last_v2_body(backend)) == ["LogWorkerId"]


@pytest.mark.parametrize(
    ("method", "expected_dims"),
    [
        ("grades", ["LogGradeName", "LogActionTime", "LogOperation", "LogActor"]),
        (
            "suggestions",
            [
                "LogSuggestionId",
                "LogSuggestedWorkerName",
                "LogJobName",
                "LogActionTime",
                "LogOperation",
            ],
        ),
        (
            "custom_members",
            ["LogCustomMemberName", "LogActionTime", "LogOperation", "LogActor"],
        ),
    ],
)
async def test_audit_v26_3_methods_default_dimensions(
    method: str, expected_dims: list[str]
) -> None:
    # The new v26.3 audit trails request their live /v2/metadata dimensions.
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            await getattr(c.audit, method)()
    assert _dim_ids(_last_v2_body(backend)) == expected_dims


# --------------------------------------------------------------------------- #
# Job Task Phases resource (new in v26.3)
# --------------------------------------------------------------------------- #
def _phase_backend() -> MockBackend:
    """A backend that types ``JobTaskPhaseJobId`` as an int and the rest as text."""

    def v2(request: httpx.Request) -> httpx.Response:
        return envelope_from_request(
            request,
            n_rows=1,
            cell=lambda d, r: 4321 if d == "JobTaskPhaseJobId" else f"{d}-{r}",
        )

    return MockBackend(v2=v2)


async def test_job_task_phases_runs_matching_report() -> None:
    backend = _phase_backend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.job_task_phases.list()
    assert rows
    assert all(isinstance(r, JobTaskPhase) for r in rows)
    assert _last_v2_body(backend)["reportId"] == "JobTaskPhaseListing"


async def test_job_task_phases_default_dimensions() -> None:
    backend = _phase_backend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            await c.job_task_phases.list()
    assert _dim_ids(_last_v2_body(backend)) == [
        "TaskPhaseName",
        "TaskPhaseRemoteId",
        "JobTaskPhaseJobId",
        "JobName",
        "JobRequestNumber",
    ]


async def test_job_task_phases_decodes_typed_fields() -> None:
    backend = _phase_backend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.job_task_phases.list()
    phase = rows[0]
    assert phase.job_id == 4321
    assert phase.phase_name == "TaskPhaseName-0"
    assert phase.phase_remote_id == "TaskPhaseRemoteId-0"
    assert phase.job_request_number == "JobRequestNumber-0"


# --------------------------------------------------------------------------- #
# Timeseries namespace
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("method", "report_id"),
    [
        ("availability", "Availability"),
        ("availability_planning", "AvailabilityPlanning"),
        ("utilisation", "Utilisation"),
        ("booking_hours", "TaskHoursByTime"),
        ("unavailability_hours", "UnavailabilityHoursByTime"),
        ("clash_hours", "ClashHoursByTime"),
        ("conflict_hours", "ConflictHours"),
        ("worker_work_hours", "WorkerWorkHours"),
        ("revenue", "RevenueByTime"),
        ("comparative_revenue", "ComparativeRevenue"),
        ("schedule_export", "ScheduleExport"),
    ],
)
async def test_timeseries_methods_run_matching_report(
    method: str, report_id: str
) -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await getattr(c.timeseries, method)()
    assert rows
    assert all(isinstance(r, PivotRow) for r in rows)
    assert _last_v2_body(backend)["reportId"] == report_id


async def test_timeseries_report_by_name() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.timeseries.report("revenue")
    assert all(isinstance(r, PivotRow) for r in rows)
    assert _last_v2_body(backend)["reportId"] == "RevenueByTime"


async def test_timeseries_default_dimensions() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            await c.timeseries.revenue()
    assert _dim_ids(_last_v2_body(backend)) == ["TaskVActualJobName", "TaskVActualMonth"]


async def test_pivot_row_values_exposes_dynamic_columns() -> None:
    def v2(request: httpx.Request) -> httpx.Response:
        return envelope_from_request(request, n_rows=1)

    backend = MockBackend(v2=v2)
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.timeseries.revenue()
    values = rows[0].values()
    # Every requested dimension surfaces as a dynamic column on the pivot row.
    assert "TaskVActualJobName" in values
    assert "TaskVActualMonth" in values


# --------------------------------------------------------------------------- #
# Rate-limit gate is internal: a rate-limited report still works
# --------------------------------------------------------------------------- #
async def test_rate_limited_report_succeeds() -> None:
    # TaskListing is one of the per-user single-concurrency reports; the gate is
    # acquired internally and the call still completes.
    def v2(request: httpx.Request) -> httpx.Response:
        return envelope_from_request(request, n_rows=1)

    backend = MockBackend(v2=v2)
    async with build_client(backend, rate_limit_gate=True) as client:
        with client.period(YEAR) as c:
            rows = await c.reports.run("TaskListing", dimensions=["TaskId"])
    assert len(rows) == 1
    assert rows[0]["TaskId"] == 100


async def test_rate_limited_resource_list_succeeds() -> None:
    # bookings -> TaskListing (rate-limited) via the typed resource path.
    backend = MockBackend()
    async with build_client(backend, rate_limit_gate=True) as client:
        with client.period(YEAR) as c:
            rows = await c.bookings.list(dimensions=["TaskId"])
    assert rows
    assert _last_v2_body(backend)["reportId"] == "TaskListing"
