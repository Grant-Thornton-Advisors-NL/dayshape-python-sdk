"""Tests for response decoding: ``reports/result.py``, ``reports/metadata.py``,
and ``reports/saved.py`` (the columnar envelope, runtime metadata models, and the
saved-report handle).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from dayshape.exceptions import ResponseFormatError
from dayshape.reports.metadata import FilterType, ReportMetadata
from dayshape.reports.query import QueryMessageV2
from dayshape.reports.result import (
    OLDEST_CACHE_AGE_HEADER,
    ReportResult,
    ResultMeta,
)

from conftest import BASE_URL, make_jwt


# --------------------------------------------------------------------------- #
# ReportResult.from_envelope — columnar decode
# --------------------------------------------------------------------------- #
def test_from_envelope_shuffled_index_pairs_cells() -> None:
    # Dimensions index map is deliberately NOT in column order: the cell for each
    # id must follow its declared column index, not its position in the map.
    index = {"TaskId": 2, "TaskStart": 0, "TaskEnd": 1}
    # row laid out positionally: [TaskStart, TaskEnd, TaskId]
    rows = [["2026-01-01T09:00:00Z", "2026-01-01T17:00:00Z", 100]]
    envelope = {
        "recordCount": 1,
        "reportDurationMs": 42,
        "reportDisplayName": "Shuffled Report",
        "reportStarted": "2026-01-01T00:00:00.000Z",
        "dimensions": index,
        "dimensionDisplayNames": ["Start (d)", "End (d)", "Id (d)"],
        "rows": rows,
    }

    result = ReportResult.from_envelope(envelope)
    records = list(result.iter_records())
    assert len(records) == 1
    rec = records[0]
    assert rec["TaskId"] == 100
    assert rec["TaskStart"] == "2026-01-01T09:00:00Z"
    assert rec["TaskEnd"] == "2026-01-01T17:00:00Z"


def test_from_envelope_populates_meta() -> None:
    index = {"TaskId": 0, "TaskStart": 1}
    envelope = {
        "recordCount": 7,
        "reportDurationMs": 1234,
        "reportDisplayName": "My Report",
        "reportStarted": "2026-02-03T04:05:06.000Z",
        "dimensions": index,
        "dimensionDisplayNames": ["Task Id", "Task Start"],
        "rows": [[1, "2026-01-01T00:00:00Z"]],
    }
    result = ReportResult.from_envelope(envelope)
    meta = result.meta
    assert meta.record_count == 7
    assert meta.report_duration_ms == 1234
    assert meta.report_display_name == "My Report"
    # dimension_display_names maps id -> localized display name.
    assert meta.dimension_display_names == {
        "TaskId": "Task Id",
        "TaskStart": "Task Start",
    }
    # reportStarted parsed from millisecond ISO with a Z suffix.
    assert meta.report_started == datetime(
        2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc
    )


def test_from_envelope_oldest_cache_age_from_http_date_header() -> None:
    # An RFC 2822 / HTTP-date in the Dayshape-Oldest-Cache-Age header parses to a
    # tz-aware datetime.
    headers = httpx.Headers(
        {OLDEST_CACHE_AGE_HEADER: "Wed, 21 Oct 2026 07:28:00 GMT"}
    )
    result = ReportResult.from_envelope({"rows": [], "dimensions": {}}, headers)
    assert result.meta.oldest_cache_age == datetime(
        2026, 10, 21, 7, 28, 0, tzinfo=timezone.utc
    )


def test_from_envelope_oldest_cache_age_absent_is_none() -> None:
    # No header at all → None.
    result = ReportResult.from_envelope(
        {"rows": [], "dimensions": {}}, httpx.Headers({})
    )
    assert result.meta.oldest_cache_age is None
    # And when headers is omitted entirely.
    result2 = ReportResult.from_envelope({"rows": [], "dimensions": {}})
    assert result2.meta.oldest_cache_age is None


def test_from_envelope_oldest_cache_age_garbage_is_none() -> None:
    headers = httpx.Headers({OLDEST_CACHE_AGE_HEADER: "not-a-date-at-all"})
    result = ReportResult.from_envelope({"rows": [], "dimensions": {}}, headers)
    assert result.meta.oldest_cache_age is None


def test_from_envelope_rows_none_tolerated() -> None:
    # rows missing/None → empty result, no iteration.
    result = ReportResult.from_envelope(
        {"rows": None, "dimensions": {"TaskId": 0}}
    )
    assert result.rows == []
    assert list(result.iter_records()) == []


def test_from_envelope_dimensions_none_tolerated() -> None:
    # dimensions missing/None → empty index; records are empty dicts per row.
    result = ReportResult.from_envelope({"rows": [[1, 2]], "dimensions": None})
    assert result.index == {}
    assert list(result.iter_records()) == [{}]


def test_from_envelope_empty_dict() -> None:
    # A wholly empty object is tolerated: no rows, no index, default meta.
    result = ReportResult.from_envelope({})
    assert result.rows == []
    assert result.index == {}
    assert result.meta.record_count is None
    assert result.meta.report_started is None


def test_from_envelope_non_dict_raises_response_format_error() -> None:
    with pytest.raises(ResponseFormatError):
        ReportResult.from_envelope(["not", "a", "dict"])
    with pytest.raises(ResponseFormatError):
        ReportResult.from_envelope(None)
    with pytest.raises(ResponseFormatError):
        ReportResult.from_envelope("a string")


def test_from_envelope_index_coerces_keys_and_values() -> None:
    # Keys stringified and values int-coerced from the wire form.
    envelope = {"rows": [[5]], "dimensions": {"TaskId": "0"}}
    result = ReportResult.from_envelope(envelope)
    assert result.index == {"TaskId": 0}
    assert list(result.iter_records()) == [{"TaskId": 5}]


def test_iter_records_skips_out_of_range_index() -> None:
    # A column index that exceeds the row width is skipped, not an error.
    result = ReportResult(
        rows=[[1]], index={"TaskId": 0, "Missing": 5}, meta=ResultMeta()
    )
    assert list(result.iter_records()) == [{"TaskId": 1}]


def test_from_envelope_short_display_list_omits_missing() -> None:
    # Display names list shorter than index → only in-range ids get a display.
    envelope = {
        "rows": [[1, 2]],
        "dimensions": {"TaskId": 0, "TaskStart": 1},
        "dimensionDisplayNames": ["Task Id"],  # only index 0 covered
    }
    result = ReportResult.from_envelope(envelope)
    assert result.meta.dimension_display_names == {"TaskId": "Task Id"}


def test_from_envelope_report_started_garbage_is_none() -> None:
    result = ReportResult.from_envelope(
        {"rows": [], "dimensions": {}, "reportStarted": "not-a-datetime"}
    )
    assert result.meta.report_started is None


# --------------------------------------------------------------------------- #
# ReportMetadata — runtime discovery model
# --------------------------------------------------------------------------- #
def test_report_metadata_model_validate_and_dimension_ids() -> None:
    wire = {
        "dimensions": [
            {"dimensionId": "TaskId", "displayName": "Task Id"},
            {"dimensionId": "TaskStart", "displayName": "Task Start"},
            {"displayName": "No Id Here"},  # missing dimensionId
        ],
        "filterGroupDefinitions": [
            {
                "displayName": "Job filters",
                "title": "Jobs",
                "filterTypes": [
                    {
                        "name": "jobLeader",
                        "displayName": "Job Leader",
                        "type": "jobLeader",
                        "dataRequired": True,
                        "parameterNames": ["leaderId"],
                    },
                    {
                        "name": "picker",
                        "type": "picker",
                    },
                ],
            }
        ],
    }
    meta = ReportMetadata.model_validate(wire)
    # dimension_ids() collects only ids that are present (None dropped).
    assert meta.dimension_ids() == frozenset({"TaskId", "TaskStart"})
    assert isinstance(meta.dimension_ids(), frozenset)

    # FilterType enum parses from the wire string value.
    group = meta.filter_groups[0]
    assert group.display_name == "Job filters"
    assert group.title == "Jobs"
    leader = group.filter_types[0]
    assert leader.type is FilterType.JOB_LEADER
    assert leader.type == "jobLeader"  # StrEnum compares to wire value
    assert leader.data_required is True
    assert leader.parameter_names == ["leaderId"]

    picker = group.filter_types[1]
    assert picker.type is FilterType.PICKER
    assert picker.data_required is False  # default
    assert picker.parameter_names == []  # default


def test_report_metadata_defaults_empty() -> None:
    meta = ReportMetadata.model_validate({})
    assert meta.dimensions == []
    assert meta.filter_groups == []
    assert meta.dimension_ids() == frozenset()


def test_report_metadata_extra_fields_ignored() -> None:
    # extra="ignore" → unknown wire keys do not raise.
    meta = ReportMetadata.model_validate(
        {"dimensions": [{"dimensionId": "X", "unknownKey": 1}], "spuriousTop": 9}
    )
    assert meta.dimension_ids() == frozenset({"X"})


def test_filter_type_enum_values() -> None:
    # A representative spread of the wire aliases.
    assert FilterType("selector") is FilterType.SELECTOR
    assert FilterType("inOutPicker") is FilterType.IN_OUT_PICKER
    assert FilterType("currencyPicker") is FilterType.CURRENCY_PICKER
    assert FilterType.JOB_ECONOMICS.value == "jobEconomics"


# --------------------------------------------------------------------------- #
# SavedReportRef — run() and query() via a mocked client
# --------------------------------------------------------------------------- #
class SavedBackend:
    """A recording handler for the saved-report endpoints (and token)."""

    def __init__(
        self,
        *,
        run_response: httpx.Response | None = None,
        query_body: Any = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self._run_response = run_response
        self._query_body = query_body

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/reporting/token"):
            return httpx.Response(200, text=make_jwt())
        if "/runSavedReport/" in path:
            if self._run_response is not None:
                return self._run_response
            # A minimal valid columnar envelope echoing one row.
            return httpx.Response(
                200,
                json={
                    "recordCount": 1,
                    "dimensions": {"TaskId": 0},
                    "dimensionDisplayNames": ["Task Id"],
                    "rows": [[100]],
                },
            )
        if "/getReportQuery/" in path:
            return httpx.Response(200, json=self._query_body)
        return httpx.Response(404, text="unhandled")

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


async def test_saved_run_hits_run_saved_endpoint() -> None:
    backend = SavedBackend()
    from dayshape import DayshapeClient

    async with DayshapeClient(
        transport=backend.transport,
        base_url=BASE_URL,
        username="user",
        password="pass",
    ) as client:
        saved = client.reports.saved("myhash")
        assert saved.hash == "myhash"
        query = saved.run()
        rows = await query  # awaiting a ReportQuery materialises the list
    assert rows == [{"TaskId": 100}]
    # The run hit GET /runSavedReport/{hash}.
    run_paths = [p for p in backend.paths() if "/runSavedReport/" in p]
    assert run_paths and run_paths[0].endswith("/runSavedReport/myhash")
    run_req = next(r for r in backend.requests if "/runSavedReport/" in r.url.path)
    assert run_req.method == "GET"


async def test_saved_query_with_wrapper_envelope() -> None:
    # Response wraps the QueryMessageV2 under a "query" key
    # (SavedReportQueryMessageV2 wrapper).
    wrapper = {
        "query": {
            "reportId": "TaskListing",
            "subType": 3,
            "dimensions": [
                {"dimensionId": "TaskId"},
                {"dimensionId": "TaskStart", "sorted": "ascending"},
            ],
        },
        "extraMetadataKey": "ignored",
    }
    backend = SavedBackend(query_body=wrapper)
    from dayshape import DayshapeClient

    async with DayshapeClient(
        transport=backend.transport,
        base_url=BASE_URL,
        username="user",
        password="pass",
    ) as client:
        result = await client.reports.saved("h-1").query()

    assert isinstance(result, QueryMessageV2)
    assert result.report_id == "TaskListing"
    assert result.sub_type == 3
    assert [d.dimension_id for d in result.dimensions] == ["TaskId", "TaskStart"]
    assert result.dimensions[1].order is not None

    # The query hit GET /getReportQuery/{hash}.
    query_req = next(
        r for r in backend.requests if "/getReportQuery/" in r.url.path
    )
    assert query_req.method == "GET"
    assert query_req.url.path.endswith("/getReportQuery/h-1")


async def test_saved_query_with_bare_body() -> None:
    # Response is a bare QueryMessageV2 (no "query" wrapper key).
    bare = {
        "reportId": "ResourceListing",
        "dimensions": [{"dimensionId": "ResourceId"}],
    }
    backend = SavedBackend(query_body=bare)
    from dayshape import DayshapeClient

    async with DayshapeClient(
        transport=backend.transport,
        base_url=BASE_URL,
        username="user",
        password="pass",
    ) as client:
        result = await client.reports.saved("bare").query()

    assert isinstance(result, QueryMessageV2)
    assert result.report_id == "ResourceListing"
    assert [d.dimension_id for d in result.dimensions] == ["ResourceId"]
    assert any("/getReportQuery/bare" in p for p in backend.paths())
