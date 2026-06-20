"""Tests for ``dayshape.filters`` — typed filter builders.

Each typed builder fixes a wire ``filterId`` and maps friendly snake_case
keyword arguments to the camelCase ``parameters`` dict the API expects. These
tests assert both ``filter_id`` and the exact wire ``parameters`` (via
``.parameters`` and ``.model_dump(by_alias=True)``), that omitted optionals are
dropped (``None`` never serialised), and that a typed filter round-trips through
``QueryMessageV2(...).to_wire()``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dayshape.filters import (
    AssignedResourceFilter,
    CustomFieldFilter,
    JobCreationDateFilter,
    JobIdFilter,
    JobLeaderFilter,
    JobTextFilter,
    RawFilter,
    TaskIdFilter,
    TaskWorkflowStateFilter,
    UserIdFilter,
    WorkerIdFilter,
)
from dayshape.period import Period
from dayshape.reports.query import Filter, QueryMessageV2


# --------------------------------------------------------------------------- #
# Representative typed filters: filter_id + exact wire parameters
# --------------------------------------------------------------------------- #
def test_task_id_filter() -> None:
    f = TaskIdFilter(task_ids=[1, 2])
    assert f.filter_id == "TaskIdFilter"
    assert f.parameters == {"taskIds": [1, 2]}
    assert f.model_dump(by_alias=True) == {
        "filterId": "TaskIdFilter",
        "parameters": {"taskIds": [1, 2]},
    }


def test_task_workflow_state_filter_with_inclusive() -> None:
    f = TaskWorkflowStateFilter(state_ids=[1], is_inclusive=True)
    assert f.filter_id == "TaskWorkflowStateFilter"
    assert f.parameters == {"stateIds": [1], "isInclusive": True}


def test_assigned_resource_filter() -> None:
    f = AssignedResourceFilter([5])
    assert f.filter_id == "AssignedResourceFilter"
    assert f.parameters == {"workerIds": [5]}


def test_job_id_filter() -> None:
    f = JobIdFilter([3])
    assert f.filter_id == "JobIdFilter"
    assert f.parameters == {"ids": [3]}


def test_job_text_filter() -> None:
    f = JobTextFilter("x")
    assert f.filter_id == "JobTextFilter"
    assert f.parameters == {"text": "x"}


def test_worker_id_filter() -> None:
    f = WorkerIdFilter([9])
    assert f.filter_id == "WorkerIdFilter"
    assert f.parameters == {"ids": [9]}


def test_user_id_filter() -> None:
    f = UserIdFilter([7])
    assert f.filter_id == "UserIdFilter"
    assert f.parameters == {"userIds": [7]}


def test_job_leader_filter_drops_none_optionals() -> None:
    f = JobLeaderFilter([1], include_partners=True)
    # Only the supplied workerIds + includePartners survive; the four other
    # optional flags (None) are dropped, so the dict has exactly two keys.
    assert f.filter_id == "JobLeaderFilter"
    assert f.parameters == {"workerIds": [1], "includePartners": True}
    assert set(f.parameters) == {"workerIds", "includePartners"}


def test_job_creation_date_filter_iso_from_only() -> None:
    dt = datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc)
    f = JobCreationDateFilter(start=dt)
    assert f.filter_id == "JobCreationDateFilter"
    # ``start`` maps to wire key ``from`` as millisecond ISO-8601 with a Z; the
    # un-supplied ``to`` (None) is dropped.
    assert f.parameters == {"from": "2026-06-01T09:30:00.000Z"}
    assert "to" not in f.parameters


# --------------------------------------------------------------------------- #
# Omitted optionals are dropped (None never serialised)
# --------------------------------------------------------------------------- #
def test_optional_inclusive_omitted_is_dropped() -> None:
    f = TaskWorkflowStateFilter(state_ids=[1])
    assert f.parameters == {"stateIds": [1]}
    assert "isInclusive" not in f.parameters


def test_job_id_filter_without_inclusive() -> None:
    f = JobIdFilter([3])
    assert f.parameters == {"ids": [3]}
    assert "isInclusive" not in f.parameters


def test_job_creation_date_filter_no_bounds_yields_no_parameters() -> None:
    f = JobCreationDateFilter()
    # _drop returns None when every value is None.
    assert f.parameters is None
    assert f.model_dump(by_alias=True, exclude_none=True) == {
        "filterId": "JobCreationDateFilter"
    }


def test_job_creation_date_filter_both_bounds() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    f = JobCreationDateFilter(start=start, end=end)
    assert f.parameters == {
        "from": "2026-01-01T00:00:00.000Z",
        "to": "2026-12-31T23:59:59.000Z",
    }


def test_job_leader_filter_all_optionals_supplied() -> None:
    f = JobLeaderFilter(
        [4],
        include_partners=False,
        include_managers=True,
        include_alt_partners=False,
        include_alt_managers=True,
        is_inclusive=False,
    )
    # ``False`` is a real value (not None) so every flag survives.
    assert f.parameters == {
        "workerIds": [4],
        "includePartners": False,
        "includeManagers": True,
        "includeAltPartners": False,
        "includeAltManagers": True,
        "isInclusive": False,
    }


# --------------------------------------------------------------------------- #
# Escape hatches: RawFilter / CustomFieldFilter
# --------------------------------------------------------------------------- #
def test_raw_filter_round_trips() -> None:
    f = RawFilter("CustomThing", {"a": 1})
    assert f.filter_id == "CustomThing"
    assert f.parameters == {"a": 1}
    assert f.model_dump(by_alias=True) == {
        "filterId": "CustomThing",
        "parameters": {"a": 1},
    }


def test_raw_filter_without_parameters() -> None:
    f = RawFilter("Bare")
    assert f.filter_id == "Bare"
    assert f.parameters is None
    assert f.model_dump(by_alias=True, exclude_none=True) == {"filterId": "Bare"}


def test_custom_field_filter_builds_parameters() -> None:
    f = CustomFieldFilter("cf123", selected_ids=[1], text="t")
    assert f.filter_id == "cf123"
    assert f.parameters == {"selectedIds": [1], "text": "t"}


def test_custom_field_filter_extra_kwargs_merge() -> None:
    f = CustomFieldFilter("cf123", selected_ids=[2], extra="boom")
    assert f.parameters == {"extra": "boom", "selectedIds": [2]}
    assert "text" not in f.parameters


def test_custom_field_filter_empty_yields_no_parameters() -> None:
    f = CustomFieldFilter("cf999")
    assert f.filter_id == "cf999"
    assert f.parameters is None


# --------------------------------------------------------------------------- #
# Subclass identity and base-model behavior
# --------------------------------------------------------------------------- #
def test_typed_filters_are_filter_instances() -> None:
    assert isinstance(TaskIdFilter([1]), Filter)
    assert isinstance(RawFilter("X"), Filter)
    assert isinstance(CustomFieldFilter("cf"), Filter)


def test_filter_forbids_extra_fields() -> None:
    # The base Filter model forbids unknown fields on validation.
    with pytest.raises(Exception):
        Filter.model_validate(
            {"filterId": "X", "parameters": {"a": 1}, "bogus": 1}
        )


# --------------------------------------------------------------------------- #
# Round-trip through QueryMessageV2.to_wire()
# --------------------------------------------------------------------------- #
def test_typed_filter_accepted_by_query_to_wire() -> None:
    period = Period.year(2026)
    q = QueryMessageV2(
        report_id="TaskListing",
        from_=period.start,
        to=period.end,
        dimensions=["TaskId"],
        filters=[TaskIdFilter([1, 2])],
    )
    wire = q.to_wire()
    assert wire["filters"] == [
        {"filterId": "TaskIdFilter", "parameters": {"taskIds": [1, 2]}}
    ]


def test_multiple_typed_filters_round_trip() -> None:
    period = Period.year(2026)
    q = QueryMessageV2(
        report_id="TaskListing",
        from_=period.start,
        to=period.end,
        dimensions=["TaskId"],
        filters=[
            TaskWorkflowStateFilter([1], is_inclusive=True),
            JobLeaderFilter([2], include_partners=True),
            RawFilter("CustomThing", {"a": 1}),
        ],
    )
    wire = q.to_wire()
    assert wire["filters"] == [
        {
            "filterId": "TaskWorkflowStateFilter",
            "parameters": {"stateIds": [1], "isInclusive": True},
        },
        {
            "filterId": "JobLeaderFilter",
            "parameters": {"workerIds": [2], "includePartners": True},
        },
        {"filterId": "CustomThing", "parameters": {"a": 1}},
    ]


def test_empty_filters_dropped_from_wire() -> None:
    period = Period.year(2026)
    q = QueryMessageV2(
        report_id="TaskListing",
        from_=period.start,
        to=period.end,
        dimensions=["TaskId"],
    )
    assert "filters" not in q.to_wire()


def test_sequence_inputs_are_materialised_to_lists() -> None:
    # Constructors call ``list(...)`` so tuple/range inputs become JSON lists.
    assert TaskIdFilter(task_ids=(1, 2, 3)).parameters == {"taskIds": [1, 2, 3]}
    assert WorkerIdFilter(range(3)).parameters == {"ids": [0, 1, 2]}
