"""Tests for entity models, tolerant cell parsers, and ``decode_row`` (§4.1–§4.4).

Covers ``models/base.py`` (parsers, ``DayshapeModel`` machinery), the entity
models (``Booking``/``Worker``/``Job``/``Unavailability``) including relational
hops, and ``decode_row`` in ``resources/base.py`` (strict vs best-effort).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import httpx
import pytest

from dayshape import (
    Booking,
    DetachedModelError,
    Job,
    Percentage,
    QueryError,
    ResponseValidationError,
    Unavailability,
    Worker,
)
from dayshape.models.base import (
    DayshapeModel,
    _parse_percentage,
    parse_date,
    parse_datetime,
    parse_guid,
)
from dayshape.period import Period

from conftest import MockBackend, build_client, envelope_from_request, make_envelope

YEAR = Period.year(2026)


# --------------------------------------------------------------------------- #
# parse_datetime
# --------------------------------------------------------------------------- #
def test_parse_datetime_trailing_z() -> None:
    out = parse_datetime("2026-01-10T09:00:00.000Z")
    assert isinstance(out, datetime)
    assert out.tzinfo is not None
    assert out.utcoffset() == timezone.utc.utcoffset(None)


def test_parse_datetime_seven_fractional_digits() -> None:
    # The API emits 7 fractional digits; fromisoformat only accepts 3 or 6.
    out = parse_datetime("2026-01-10T09:00:00.1234567Z")
    assert isinstance(out, datetime)
    assert out.microsecond == 123456  # truncated to 6 digits


def test_parse_datetime_passthrough_datetime() -> None:
    dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_datetime(dt) is dt


def test_parse_datetime_none_passthrough() -> None:
    assert parse_datetime(None) is None


def test_parse_datetime_junk_passthrough() -> None:
    # Unparseable text is returned verbatim for the field type to reject.
    assert parse_datetime("not-a-date") == "not-a-date"


def test_parse_datetime_empty_string_becomes_none() -> None:
    assert parse_datetime("   ") is None


def test_parse_datetime_non_string_passthrough() -> None:
    assert parse_datetime(12345) == 12345


# --------------------------------------------------------------------------- #
# parse_date
# --------------------------------------------------------------------------- #
def test_parse_date_from_iso_string() -> None:
    out = parse_date("2026-03-15T09:00:00Z")
    assert out == date(2026, 3, 15)
    assert isinstance(out, date) and not isinstance(out, datetime)


def test_parse_date_passthrough_date() -> None:
    d = date(2026, 5, 1)
    assert parse_date(d) is d


def test_parse_date_from_datetime_takes_date() -> None:
    dt = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
    assert parse_date(dt) == date(2026, 7, 4)


def test_parse_date_none_passthrough() -> None:
    assert parse_date(None) is None


def test_parse_date_junk_passthrough() -> None:
    assert parse_date("garbage") == "garbage"


def test_parse_date_plain_iso_date() -> None:
    assert parse_date("2026-12-25") == date(2026, 12, 25)


# --------------------------------------------------------------------------- #
# parse_guid
# --------------------------------------------------------------------------- #
def test_parse_guid_valid_uuid() -> None:
    text = "12345678-1234-5678-1234-567812345678"
    out = parse_guid(text)
    assert isinstance(out, UUID)
    assert str(out) == text


def test_parse_guid_non_uuid_string_passthrough() -> None:
    # The spec's own samples include "M1" as a mapping id.
    assert parse_guid("M1") == "M1"


def test_parse_guid_passthrough_uuid() -> None:
    u = UUID("12345678-1234-5678-1234-567812345678")
    assert parse_guid(u) is u


def test_parse_guid_none_passthrough() -> None:
    assert parse_guid(None) is None


def test_parse_guid_non_string_passthrough() -> None:
    assert parse_guid(42) == 42


# --------------------------------------------------------------------------- #
# Percentage / _parse_percentage
# --------------------------------------------------------------------------- #
def test_percentage_is_float_subclass() -> None:
    assert issubclass(Percentage, float)
    assert Percentage(0.9) == 0.9


def test_parse_percentage_float_stays() -> None:
    out = _parse_percentage(0.9)
    assert isinstance(out, Percentage)
    assert out == 0.9


def test_parse_percentage_int() -> None:
    out = _parse_percentage(1)
    assert isinstance(out, Percentage)
    assert out == 1.0


def test_parse_percentage_string() -> None:
    out = _parse_percentage("0.9")
    assert isinstance(out, Percentage)
    assert out == 0.9


def test_parse_percentage_already_percentage() -> None:
    p = Percentage(0.5)
    assert _parse_percentage(p) is p


def test_parse_percentage_none() -> None:
    assert _parse_percentage(None) is None


def test_parse_percentage_bad_string_passthrough() -> None:
    assert _parse_percentage("not-a-number") == "not-a-number"


def test_parse_percentage_empty_string_passthrough() -> None:
    assert _parse_percentage("   ") == "   "


# --------------------------------------------------------------------------- #
# DayshapeModel: populate_by_name + extra="allow"
# --------------------------------------------------------------------------- #
def test_populate_by_name_accepts_alias() -> None:
    b = Booking.model_validate({"TaskId": 7})
    assert b.id == 7


def test_populate_by_name_accepts_python_name() -> None:
    b = Booking.model_validate({"id": 9})
    assert b.id == 9


def test_extra_allow_collects_unknown_into_custom_fields() -> None:
    b = Booking.model_validate({"TaskId": 1, "Tenant_CustomCol": "value"})
    assert b.custom_fields == {"Tenant_CustomCol": "value"}


def test_custom_fields_empty_when_no_extra() -> None:
    b = Booking.model_validate({"TaskId": 1})
    assert b.custom_fields == {}


# --------------------------------------------------------------------------- #
# DayshapeModel.field(): declared-or-extra lookup
# --------------------------------------------------------------------------- #
def test_field_reads_declared_by_alias() -> None:
    b = Booking.model_validate({"TaskId": 1, "TaskState": "Confirmed"})
    assert b.field("TaskState") == "Confirmed"


def test_field_reads_declared_by_python_name() -> None:
    b = Booking.model_validate({"TaskId": 5})
    assert b.field("id") == 5


def test_field_reads_extra_dimension() -> None:
    b = Booking.model_validate({"TaskId": 1, "SomeComparativeCol": 3.0})
    assert b.field("SomeComparativeCol") == 3.0


def test_field_missing_returns_none() -> None:
    b = Booking.model_validate({"TaskId": 1})
    assert b.field("DoesNotExist") is None


# --------------------------------------------------------------------------- #
# DayshapeModel.was_requested()
# --------------------------------------------------------------------------- #
def test_was_requested_true_and_false() -> None:
    b = Booking.model_validate(
        {"TaskId": 1, "requested_dimensions": frozenset({"TaskId", "TaskStart"})}
    )
    assert b.was_requested("TaskId") is True
    assert b.was_requested("TaskStart") is True
    assert b.was_requested("TaskEnd") is False


def test_requested_dimensions_excluded_from_dump() -> None:
    b = Booking.model_validate(
        {"TaskId": 1, "requested_dimensions": frozenset({"TaskId"})}
    )
    assert "requested_dimensions" not in b.model_dump()


# --------------------------------------------------------------------------- #
# DayshapeModel._split helper
# --------------------------------------------------------------------------- #
def test_split_none_returns_empty() -> None:
    assert DayshapeModel._split(None) == []


def test_split_empty_string_returns_empty() -> None:
    assert DayshapeModel._split("") == []


def test_split_comma_string_strips_parts() -> None:
    assert DayshapeModel._split("a, b ,c") == ["a", "b", "c"]


def test_split_drops_blank_parts() -> None:
    assert DayshapeModel._split("a,,b, ,c") == ["a", "b", "c"]


def test_traits_list_uses_split() -> None:
    b = Booking.model_validate({"TaskId": 1, "TaskTraits": "Python, SQL"})
    assert b.traits_list == ["Python", "SQL"]


def test_worker_traits_list_none_is_empty() -> None:
    w = Worker.model_validate({"WorkerId": 1})
    assert w.traits_list == []


# --------------------------------------------------------------------------- #
# Entity decoding through a mocked client
# --------------------------------------------------------------------------- #
async def test_booking_decoded_from_wire_aliases() -> None:
    def cell(dim: str, row: int) -> Any:
        return {
            "TaskId": 42,
            "TaskStart": "2026-01-10T09:00:00.0000000Z",
            "TaskJobId": 7,
            "TaskWorkerId": 99,
        }.get(dim, f"{dim}-{row}")

    def v2(req: httpx.Request) -> httpx.Response:
        return envelope_from_request(req, cell=cell)

    backend = MockBackend(v2=v2)
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.bookings.list(
                dimensions=["TaskId", "TaskStart", "TaskJobId", "TaskWorkerId"]
            )
    assert len(rows) == 1
    booking = rows[0]
    assert isinstance(booking, Booking)
    assert booking.id == 42
    assert isinstance(booking.start, datetime)
    assert booking.start.year == 2026 and booking.start.month == 1
    assert booking.job_id == 7
    assert booking.worker_id == 99


async def test_custom_tenant_column_flows_to_custom_fields() -> None:
    def v2(req: httpx.Request) -> httpx.Response:
        # Echo the requested dims, but our requested set includes a tenant column.
        body = json.loads(req.content)
        dims = [d["dimensionId"] for d in body["dimensions"]]
        row = [101 if d == "TaskId" else f"{d}-val" for d in dims]
        return httpx.Response(200, json=make_envelope(dims, [row]))

    backend = MockBackend(v2=v2)
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.bookings.list(dimensions=["TaskId", "Tenant_Region"])
    booking = rows[0]
    assert booking.id == 101
    assert booking.custom_fields == {"Tenant_Region": "Tenant_Region-val"}
    assert booking.field("Tenant_Region") == "Tenant_Region-val"
    assert booking.was_requested("Tenant_Region") is True


async def test_decoded_row_records_requested_dimensions() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.bookings.list(dimensions=["TaskId", "TaskState"])
    booking = rows[0]
    assert booking.was_requested("TaskId") is True
    assert booking.was_requested("TaskState") is True
    assert booking.was_requested("TaskJobId") is False


# --------------------------------------------------------------------------- #
# Relational hops issue the right filtered requests
# --------------------------------------------------------------------------- #
def _capturing_backend() -> tuple[MockBackend, list[dict[str, Any]]]:
    bodies: list[dict[str, Any]] = []

    def v2(req: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(req.content))
        return envelope_from_request(req)

    return MockBackend(v2=v2), bodies


def _filters(body: dict[str, Any]) -> list[dict[str, Any]]:
    return body.get("filters", [])


async def test_booking_job_hop_issues_jobidfilter() -> None:
    backend, bodies = _capturing_backend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.bookings.list(dimensions=["TaskId", "TaskJobId"])
            booking = rows[0]
            assert booking.job_id is not None
            job_query = booking.job()
            jobs = await job_query
    assert isinstance(jobs[0], Job)
    last = bodies[-1]
    assert last["reportId"] == "JobListing"
    assert _filters(last) == [
        {"filterId": "JobIdFilter", "parameters": {"ids": [booking.job_id]}}
    ]


async def test_booking_worker_hop_issues_workeridfilter() -> None:
    backend, bodies = _capturing_backend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.bookings.list(dimensions=["TaskId", "TaskWorkerId"])
            booking = rows[0]
            workers = await booking.worker()
    assert isinstance(workers[0], Worker)
    last = bodies[-1]
    assert last["reportId"] == "WorkerListing"
    assert _filters(last) == [
        {"filterId": "WorkerIdFilter", "parameters": {"ids": [booking.worker_id]}}
    ]


async def test_booking_job_hop_missing_id_raises_queryerror() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            # Do not request TaskJobId → job_id is None.
            rows = await c.bookings.list(dimensions=["TaskId"])
            booking = rows[0]
            assert booking.job_id is None
            with pytest.raises(QueryError):
                booking.job()


async def test_booking_worker_hop_missing_id_raises_queryerror() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.bookings.list(dimensions=["TaskId"])
            booking = rows[0]
            with pytest.raises(QueryError):
                booking.worker()


async def test_worker_jobs_hop_issues_assignedresourcefilter() -> None:
    backend, bodies = _capturing_backend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.workers.list(dimensions=["WorkerId"])
            worker = rows[0]
            jobs = await worker.jobs()
    assert isinstance(jobs[0], Job)
    last = bodies[-1]
    assert last["reportId"] == "JobListing"
    assert _filters(last) == [
        {"filterId": "AssignedResourceFilter", "parameters": {"workerIds": [worker.id]}}
    ]


async def test_worker_bookings_hop_issues_assignedresourcefilter() -> None:
    backend, bodies = _capturing_backend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.workers.list(dimensions=["WorkerId"])
            worker = rows[0]
            bookings = await worker.bookings()
    assert isinstance(bookings[0], Booking)
    last = bodies[-1]
    assert last["reportId"] == "TaskListing"
    assert _filters(last) == [
        {"filterId": "AssignedResourceFilter", "parameters": {"workerIds": [worker.id]}}
    ]


async def test_worker_hop_missing_id_raises_queryerror() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.workers.list(dimensions=["WorkerName"])
            worker = rows[0]
            assert worker.id is None
            with pytest.raises(QueryError):
                worker.jobs()
            with pytest.raises(QueryError):
                worker.bookings()


async def test_job_bookings_hop_issues_jobidfilter() -> None:
    backend, bodies = _capturing_backend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.jobs.list(dimensions=["JobId"])
            job = rows[0]
            bookings = await job.bookings()
    assert isinstance(bookings[0], Booking)
    last = bodies[-1]
    assert last["reportId"] == "TaskListing"
    assert _filters(last) == [
        {"filterId": "JobIdFilter", "parameters": {"ids": [job.id]}}
    ]


async def test_job_bookings_hop_missing_id_raises_queryerror() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await c.jobs.list(dimensions=["JobName"])
            job = rows[0]
            assert job.id is None
            with pytest.raises(QueryError):
                job.bookings()


async def test_unavailability_worker_hop_issues_workeridfilter() -> None:
    backend, bodies = _capturing_backend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            rows = await _unavailability_list(c)
            unavail = rows[0]
            assert unavail.worker_id is not None
            workers = await unavail.worker()
    assert isinstance(workers[0], Worker)
    last = bodies[-1]
    assert last["reportId"] == "WorkerListing"
    assert _filters(last) == [
        {"filterId": "WorkerIdFilter", "parameters": {"ids": [unavail.worker_id]}}
    ]


async def _unavailability_list(scoped: Any) -> list[Unavailability]:
    """Run an Unavailability listing via a directly-built ResourceClient."""
    from dayshape.resources.base import ResourceClient

    resource: ResourceClient[Unavailability] = ResourceClient(
        scoped,
        report_id="UnavailabilityListing",
        model=Unavailability,
    )
    return await resource.list(
        dimensions=["UnavailabilityName", "UnavailabilityWorkerId"]
    )


async def test_unavailability_worker_hop_missing_id_raises_queryerror() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(YEAR) as c:
            from dayshape.resources.base import ResourceClient

            resource: ResourceClient[Unavailability] = ResourceClient(
                c, report_id="UnavailabilityListing", model=Unavailability
            )
            rows = await resource.list(dimensions=["UnavailabilityName"])
            unavail = rows[0]
            assert unavail.worker_id is None
            with pytest.raises(QueryError):
                unavail.worker()


# --------------------------------------------------------------------------- #
# DetachedModelError: a directly-constructed model has no client binding
# --------------------------------------------------------------------------- #
def test_detached_model_job_hop_raises() -> None:
    booking = Booking.model_validate({"TaskId": 1, "TaskJobId": 5})
    assert booking.job_id == 5
    with pytest.raises(DetachedModelError):
        booking.job()


def test_detached_model_worker_hop_raises() -> None:
    booking = Booking.model_validate({"TaskId": 1, "TaskWorkerId": 9})
    with pytest.raises(DetachedModelError):
        booking.worker()


def test_detached_worker_jobs_hop_raises() -> None:
    worker = Worker.model_validate({"WorkerId": 3})
    with pytest.raises(DetachedModelError):
        worker.jobs()


# --------------------------------------------------------------------------- #
# strict_models: ResponseValidationError vs best-effort warning
# --------------------------------------------------------------------------- #
def _bad_taskid_v2(req: httpx.Request) -> httpx.Response:
    # TaskId is declared int | None; a non-numeric string fails validation.
    body = json.loads(req.content)
    dims = [d["dimensionId"] for d in body["dimensions"]]
    row = ["not-an-int" if d == "TaskId" else f"{d}-0" for d in dims]
    return httpx.Response(200, json=make_envelope(dims, [row]))


async def test_strict_models_raises_response_validation_error() -> None:
    backend = MockBackend(v2=_bad_taskid_v2)
    async with build_client(backend, strict_models=True) as client:
        with client.period(YEAR) as c:
            with pytest.raises(ResponseValidationError):
                await c.bookings.list(dimensions=["TaskId"])


async def test_non_strict_models_warns_and_returns_best_effort() -> None:
    backend = MockBackend(v2=_bad_taskid_v2)
    async with build_client(backend, strict_models=False) as client:
        with client.period(YEAR) as c:
            with pytest.warns(UserWarning):
                rows = await c.bookings.list(dimensions=["TaskId"])
    assert len(rows) == 1
    assert isinstance(rows[0], Booking)
    # Best-effort: the raw (invalid) value survives via model_construct.
    assert rows[0].id == "not-an-int"


async def test_strict_models_validation_error_carries_row() -> None:
    backend = MockBackend(v2=_bad_taskid_v2)
    async with build_client(backend, strict_models=True) as client:
        with client.period(YEAR) as c:
            with pytest.raises(ResponseValidationError) as exc_info:
                await c.bookings.list(dimensions=["TaskId"])
    err = exc_info.value
    assert err.row is not None
    assert err.row.get("TaskId") == "not-an-int"
