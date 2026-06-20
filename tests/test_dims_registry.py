"""Tests for ``dayshape.dims``, ``dayshape.reports.registry`` and
``dayshape.reports.query`` — typed dimension constants, the report registry, and
the query/wire models.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import dayshape
import dayshape.dims as dims_module
import dayshape.reports as reports_pkg
from dayshape.dims import Dim, TaskDim
from dayshape.reports import query as query_module
from dayshape.reports import registry as registry_module
from dayshape.reports.query import (
    ComparativeDimension,
    DateTimeFormattingOptions,
    Dimension,
    Filter,
    LoginModel,
    QueryMessageV2,
    ReportFormattingOptions,
    Sort,
    default_formatting,
)
from dayshape.reports.registry import (
    ReportId,
    ReportMeta,
    ReportType,
    get_meta,
    is_rate_limited,
    resolve_report_id,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# dayshape.dims — typed dimension constants
# --------------------------------------------------------------------------- #
def test_task_dim_id_equals_str() -> None:
    assert TaskDim.ID == "TaskId"
    assert "TaskId" == TaskDim.ID


def test_dim_is_str_subclass() -> None:
    assert isinstance(TaskDim.ID, Dim)
    assert isinstance(TaskDim.ID, str)
    assert issubclass(Dim, str)


def test_dim_usable_as_dict_key() -> None:
    # Dim hashes/compares as the underlying str, so a Dim key is reachable by str.
    mapping = {TaskDim.ID: 42}
    assert mapping["TaskId"] == 42
    assert mapping[TaskDim.ID] == 42


def test_dim_str_substitution() -> None:
    assert f"{TaskDim.ID}" == "TaskId"
    assert str(TaskDim.ID) == "TaskId"
    assert TaskDim.ID.upper() == "TASKID"


def test_dim_asc_returns_ascending_dimension() -> None:
    dim = TaskDim.ID.asc()
    assert isinstance(dim, Dimension)
    assert dim.dimension_id == "TaskId"
    assert dim.order is Sort.ASC


def test_dim_desc_returns_descending_dimension() -> None:
    dim = TaskDim.ID.desc()
    assert isinstance(dim, Dimension)
    assert dim.dimension_id == "TaskId"
    assert dim.order is Sort.DESC


def test_dim_asc_serialises_to_wire() -> None:
    assert TaskDim.ID.asc().model_dump(by_alias=True) == {
        "dimensionId": "TaskId",
        "sorted": Sort.ASC,
    }


def test_dims_all_namespaces_exist() -> None:
    # __all__ lists Dim plus every *Dim namespace class.
    assert "Dim" in dims_module.__all__
    assert "TaskDim" in dims_module.__all__
    for name in dims_module.__all__:
        assert hasattr(dims_module, name), name


def test_dims_namespaces_carry_dim_constants() -> None:
    # Every *Dim class is a namespace whose public attrs are Dim instances.
    namespace_names = [n for n in dims_module.__all__ if n != "Dim"]
    assert namespace_names  # there is at least one namespace
    for name in namespace_names:
        cls = getattr(dims_module, name)
        consts = [
            getattr(cls, attr)
            for attr in vars(cls)
            if not attr.startswith("_")
        ]
        assert consts, name
        assert all(isinstance(c, Dim) for c in consts)


def test_dims_importable_from_dayshape() -> None:
    # The submodule is re-exported on the top-level package.
    assert dayshape.dims is dims_module
    assert dayshape.dims.TaskDim.ID == "TaskId"


# --------------------------------------------------------------------------- #
# Codegen drift — committed dims.py/_catalogue.py are in sync with the workbook
# --------------------------------------------------------------------------- #
def test_codegen_no_drift() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/generate_dims.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"generate_dims.py --check failed\nstdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )


# --------------------------------------------------------------------------- #
# dayshape.reports.registry — ReportId, ReportMeta and lookups
# --------------------------------------------------------------------------- #
def test_report_id_dynamic_members() -> None:
    # ReportId is a dynamic StrEnum; members are accessed via the value.
    assert ReportId("TaskListing") == "TaskListing"
    assert ReportId("ClientListing") == "ClientListing"
    assert isinstance(ReportId("TaskListing"), ReportId)


def test_report_id_unknown_raises() -> None:
    with pytest.raises(ValueError):
        ReportId("NotAReport")


def test_report_type_enum() -> None:
    assert ReportType.LISTING == "Listing"
    assert ReportType.PIVOT == "Pivot"


def test_get_meta_case_insensitive() -> None:
    meta = get_meta("tasklisting")
    assert meta is not None
    assert meta.report_id == "TaskListing"
    assert meta.rate_limited is True
    # Mixed/upper case resolve to the same metadata object.
    assert get_meta("TASKLISTING") is meta
    assert get_meta("TaskListing") is meta


def test_get_meta_unknown_returns_none() -> None:
    assert get_meta("NoSuchReport") is None


def test_is_rate_limited() -> None:
    assert is_rate_limited("TaskListing") is True
    assert is_rate_limited("ClientListing") is False
    # Case-insensitive, like the rest of the registry.
    assert is_rate_limited("tasklisting") is True
    # Unknown ids are not rate limited.
    assert is_rate_limited("NoSuchReport") is False


def test_resolve_report_id_canonicalises_case() -> None:
    assert resolve_report_id("tasklisting") == "TaskListing"
    assert resolve_report_id("CLIENTLISTING") == "ClientListing"
    assert resolve_report_id("TaskListing") == "TaskListing"


def test_resolve_report_id_passes_through_unknown() -> None:
    # Unknown ids are returned unchanged (tenant/custom reports, fwd compat).
    assert resolve_report_id("MyCustomReport") == "MyCustomReport"
    assert resolve_report_id("weirdcasing") == "weirdcasing"


def test_report_meta_is_pivot_and_is_listing() -> None:
    listing = get_meta("ClientListing")
    assert listing is not None
    assert listing.is_listing is True
    assert listing.is_pivot is False
    assert listing.type is ReportType.LISTING

    pivot = get_meta("Availability")
    assert pivot is not None
    assert pivot.is_pivot is True
    assert pivot.is_listing is False
    assert pivot.type is ReportType.PIVOT


def test_report_meta_fields() -> None:
    meta = get_meta("TaskListing")
    assert meta is not None
    assert isinstance(meta, ReportMeta)
    assert meta.display_name == "Booking Listing"
    assert isinstance(meta.permissions, str) and meta.permissions
    assert meta.rate_limited is True


def test_registry_exports_from_reports_package() -> None:
    # ReportId/ReportType/get_meta/resolve_report_id re-exported on the subpackage.
    assert reports_pkg.ReportId is ReportId
    assert reports_pkg.ReportType is ReportType
    assert reports_pkg.get_meta is get_meta
    assert reports_pkg.resolve_report_id is resolve_report_id
    # And ReportId/ReportType on the top-level package.
    assert dayshape.ReportId is ReportId
    assert dayshape.ReportType is ReportType


# --------------------------------------------------------------------------- #
# dayshape.reports.query — Dimension
# --------------------------------------------------------------------------- #
def test_dimension_positional_and_order() -> None:
    dim = Dimension("TaskId", order=Sort.ASC)
    assert dim.dimension_id == "TaskId"
    assert dim.order is Sort.ASC


def test_dimension_order_from_string() -> None:
    # order accepts the raw wire value too.
    dim = Dimension("TaskId", order="descending")
    assert dim.order is Sort.DESC


def test_dimension_default_order_none() -> None:
    dim = Dimension("TaskId")
    assert dim.order is None
    assert dim.model_dump(by_alias=True, exclude_none=True) == {"dimensionId": "TaskId"}


def test_dimension_coerce_str() -> None:
    dim = Dimension.coerce("TaskId")
    assert isinstance(dim, Dimension)
    assert dim.dimension_id == "TaskId"
    assert dim.order is None


def test_dimension_coerce_dim_constant() -> None:
    dim = Dimension.coerce(TaskDim.ID)
    assert dim.dimension_id == "TaskId"


def test_dimension_coerce_dimension_passthrough() -> None:
    original = Dimension("TaskId", order=Sort.ASC)
    assert Dimension.coerce(original) is original


def test_dimension_coerce_dict() -> None:
    dim = Dimension.coerce({"dimensionId": "TaskId", "sorted": "ascending"})
    assert dim.dimension_id == "TaskId"
    assert dim.order is Sort.ASC


def test_dimension_coerce_bad_type_raises() -> None:
    with pytest.raises(TypeError):
        Dimension.coerce(123)
    with pytest.raises(TypeError):
        Dimension.coerce(None)


def test_dimension_extra_forbidden() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Dimension.model_validate({"dimensionId": "TaskId", "bogus": 1})


# --------------------------------------------------------------------------- #
# dayshape.reports.query — ComparativeDimension
# --------------------------------------------------------------------------- #
def test_comparative_dimension_result_id() -> None:
    cd = ComparativeDimension(metric="RevenueActual", baseline="RevenueBudget")
    assert cd.result_id == "RevenueActualVsRevenueBudget"


def test_comparative_dimension_coerces_metric_and_baseline() -> None:
    cd = ComparativeDimension(metric="TaskId", baseline=Dimension("JobId"))
    assert isinstance(cd.metric, Dimension)
    assert isinstance(cd.baseline, Dimension)
    assert cd.metric.dimension_id == "TaskId"
    assert cd.baseline.dimension_id == "JobId"
    assert cd.result_id == "TaskIdVsJobId"


def test_comparative_dimension_accepts_dim_constants() -> None:
    cd = ComparativeDimension(metric=TaskDim.ID, baseline=TaskDim.JOB_ID)
    assert cd.result_id == "TaskIdVsTaskJobId"


def test_comparative_dimension_wire_aliases() -> None:
    cd = ComparativeDimension(metric="A", baseline="B")
    wire = cd.model_dump(by_alias=True, exclude_none=True)
    assert wire == {"dimA": {"dimensionId": "A"}, "dimB": {"dimensionId": "B"}}


# --------------------------------------------------------------------------- #
# dayshape.reports.query — Filter
# --------------------------------------------------------------------------- #
def test_filter_coerce_filter_passthrough() -> None:
    f = Filter(filter_id="ClientId")
    assert Filter.coerce(f) is f


def test_filter_coerce_dict() -> None:
    f = Filter.coerce({"filterId": "ClientId", "parameters": {"ids": [1, 2]}})
    assert isinstance(f, Filter)
    assert f.filter_id == "ClientId"
    assert f.parameters == {"ids": [1, 2]}


def test_filter_coerce_bad_type_raises() -> None:
    with pytest.raises(TypeError):
        Filter.coerce("ClientId")
    with pytest.raises(TypeError):
        Filter.coerce(42)


# --------------------------------------------------------------------------- #
# dayshape.reports.query — QueryMessageV2.to_wire()
# --------------------------------------------------------------------------- #
def _from() -> datetime:
    return datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _to() -> datetime:
    return datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)


def test_to_wire_camel_case_and_iso_z() -> None:
    q = QueryMessageV2(
        report_id="TaskListing",
        from_=_from(),
        to=_to(),
        dimensions=["TaskId"],
    )
    wire = q.to_wire()
    assert wire["reportId"] == "TaskListing"
    assert "report_id" not in wire and "from_" not in wire
    assert wire["from"] == "2026-01-01T00:00:00.000Z"
    assert wire["to"] == "2026-12-31T23:59:59.000Z"
    assert wire["dimensions"] == [{"dimensionId": "TaskId"}]


def test_to_wire_keeps_empty_collections() -> None:
    # The live Reporting Service 500s when ``filters`` is omitted, so the
    # collection keys are always emitted (empty arrays), not dropped.
    q = QueryMessageV2(report_id="TaskListing")
    wire = q.to_wire()
    assert wire == {
        "reportId": "TaskListing",
        "dimensions": [],
        "comparativeDimensions": [],
        "filters": [],
    }


def test_to_wire_exclude_none() -> None:
    # None-valued optional fields (subType, currency, instanceId, ...) are dropped.
    q = QueryMessageV2(report_id="TaskListing")
    wire = q.to_wire()
    for key in ("subType", "currency", "instanceId", "from", "to", "hash",
                "hideReportUrl", "reportFormattingOptions"):
        assert key not in wire


def test_to_wire_includes_populated_collections() -> None:
    q = QueryMessageV2(
        report_id="TaskListing",
        dimensions=["TaskId", Dimension("TaskStart", order=Sort.DESC)],
        comparative_dimensions=[ComparativeDimension(metric="A", baseline="B")],
        filters=[{"filterId": "ClientId"}],
    )
    wire = q.to_wire()
    assert wire["dimensions"] == [
        {"dimensionId": "TaskId"},
        {"dimensionId": "TaskStart", "sorted": "descending"},
    ]
    assert wire["comparativeDimensions"] == [
        {"dimA": {"dimensionId": "A"}, "dimB": {"dimensionId": "B"}}
    ]
    assert wire["filters"] == [{"filterId": "ClientId"}]


def test_query_dimensions_coerced_from_mixed_types() -> None:
    q = QueryMessageV2(
        report_id="TaskListing",
        dimensions=["TaskId", TaskDim.JOB_ID, {"dimensionId": "TaskStart"}],
    )
    assert [d.dimension_id for d in q.dimensions] == ["TaskId", "TaskJobId", "TaskStart"]
    assert all(isinstance(d, Dimension) for d in q.dimensions)


def test_query_optional_scalars_to_wire() -> None:
    q = QueryMessageV2(
        report_id="TaskListing",
        sub_type=3,
        currency="GBP",
        instance_id=7,
        hide_report_url=True,
    )
    wire = q.to_wire()
    assert wire["subType"] == 3
    assert wire["currency"] == "GBP"
    assert wire["instanceId"] == 7
    assert wire["hideReportUrl"] is True


# --------------------------------------------------------------------------- #
# dayshape.reports.query — default_formatting / ReportFormattingOptions
# --------------------------------------------------------------------------- #
def test_default_formatting_pins_deterministic_defaults() -> None:
    fmt = default_formatting()
    assert isinstance(fmt, ReportFormattingOptions)
    assert fmt.format_numbers is False
    assert fmt.timezone == "Etc/UTC"
    assert fmt.locale is None
    assert fmt.null_format_string is None
    assert isinstance(fmt.date_time_formatting_options, DateTimeFormattingOptions)
    assert fmt.date_time_formatting_options.date_format == "YYYY-MM-DD"
    assert fmt.date_time_formatting_options.time_format == "24 Hour"


def test_default_formatting_wire() -> None:
    wire = default_formatting().model_dump(by_alias=True, exclude_none=True)
    assert wire == {
        "timezone": "Etc/UTC",
        "dateTimeFormattingOptions": {
            "dateFormat": "YYYY-MM-DD",
            "timeFormat": "24 Hour",
        },
        "formatNumbers": False,
    }


def test_report_formatting_options_default_format_numbers_false() -> None:
    # The bare model still defaults formatNumbers to False.
    assert ReportFormattingOptions().format_numbers is False


# --------------------------------------------------------------------------- #
# dayshape.reports.query — LoginModel
# --------------------------------------------------------------------------- #
def test_login_model() -> None:
    login = LoginModel(username="api-user", password="s3cret")
    assert login.username == "api-user"
    assert login.password == "s3cret"
    assert login.model_dump() == {"username": "api-user", "password": "s3cret"}


def test_login_model_extra_forbidden() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LoginModel.model_validate({"username": "u", "password": "p", "extra": 1})


# --------------------------------------------------------------------------- #
# Sort enum / module exports
# --------------------------------------------------------------------------- #
def test_sort_enum_wire_values() -> None:
    assert Sort.ASC == "ascending"
    assert Sort.DESC == "descending"
    assert Sort("ascending") is Sort.ASC


def test_query_module_all_exports_present() -> None:
    for name in query_module.__all__:
        assert hasattr(query_module, name), name


def test_registry_module_all_exports_present() -> None:
    for name in registry_module.__all__:
        assert hasattr(registry_module, name), name


def test_query_models_importable_from_dayshape() -> None:
    assert dayshape.Dimension is Dimension
    assert dayshape.ComparativeDimension is ComparativeDimension
    assert dayshape.Filter is Filter
    assert dayshape.Sort is Sort
    assert dayshape.default_formatting is default_formatting
    assert dayshape.ReportFormattingOptions is ReportFormattingOptions
