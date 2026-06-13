"""Wire models for the query envelope (plan.md §0.3, §7.2, §4.6).

These mirror the v2 OpenAPI schemas verbatim on the wire while presenting typed,
Pythonic constructors in the hand. ``model_dump(by_alias=True, exclude_none=True)``
produces a request body byte-compatible with the official examples.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..period import _iso


class Sort(StrEnum):
    """Per-dimension sort order. ``StrEnum`` so it serialises to the wire value."""

    ASC = "ascending"
    DESC = "descending"


DimensionLike = "str | Dim | Dimension"


class Dimension(BaseModel):
    """A requested dimension, optionally sorted (wire: ``DimensionMessageV2``)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    dimension_id: str = Field(alias="dimensionId")
    order: Sort | None = Field(default=None, alias="sorted")

    def __init__(
        self,
        dimension_id: Any = None,
        /,
        *,
        order: Sort | str | None = None,
        **data: Any,
    ) -> None:
        # Support the ergonomic ``Dimension(TaskDim.ID, order=Sort.ASC)`` form as
        # well as keyword/alias construction used during validation.
        if dimension_id is not None:
            data.setdefault("dimension_id", str(dimension_id))
        if order is not None:
            data.setdefault("order", Sort(order))
        super().__init__(**data)

    @classmethod
    def coerce(cls, value: Any) -> "Dimension":
        """Coerce a ``str`` / ``Dim`` / ``Dimension`` / mapping into a ``Dimension``."""
        if isinstance(value, Dimension):
            return value
        if isinstance(value, str):
            return cls(value)
        if isinstance(value, dict):
            return cls.model_validate(value)
        raise TypeError(f"Cannot interpret {value!r} as a dimension")


class ComparativeDimension(BaseModel):
    """A server-computed relative-variance dimension (wire: ``ComparativeDimensionMessageV2``).

    The wire formula is ``{dimA}Vs{dimB} = dimB != 0 ? (dimA / dimB) - 1 : 0``.
    The keyword names make the roles explicit: ``metric`` is the numerator, the
    value being measured; ``baseline`` is the denominator it is measured against.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    metric: Dimension = Field(alias="dimA")
    baseline: Dimension = Field(alias="dimB")

    def __init__(
        self,
        *,
        metric: Any = None,
        baseline: Any = None,
        **data: Any,
    ) -> None:
        if metric is not None:
            data.setdefault("metric", Dimension.coerce(metric))
        if baseline is not None:
            data.setdefault("baseline", Dimension.coerce(baseline))
        super().__init__(**data)

    @property
    def result_id(self) -> str:
        """The derived result column id, ``{DimA}Vs{DimB}`` (plan.md §4.5, R-4)."""
        return f"{self.metric.dimension_id}Vs{self.baseline.dimension_id}"


class Filter(BaseModel):
    """A filter to apply (wire: ``FilterMessageV2``).

    Typed builders in :mod:`dayshape.filters` subclass this, fixing ``filter_id``
    and mapping friendly keyword arguments to ``parameters``. All filters are
    ANDed server-side (plan.md §6).
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    filter_id: str = Field(alias="filterId")
    parameters: dict[str, Any] | None = None

    @classmethod
    def coerce(cls, value: Any) -> "Filter":
        if isinstance(value, Filter):
            return value
        if isinstance(value, dict):
            return cls.model_validate(value)
        raise TypeError(f"Cannot interpret {value!r} as a filter")


class DateTimeFormattingOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    date_format: str | None = Field(default=None, alias="dateFormat")
    time_format: str | None = Field(default=None, alias="timeFormat")


class ReportFormattingOptions(BaseModel):
    """Formatting controls (plan.md §4.6). SDK pins deterministic defaults."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    timezone: str | None = None
    locale: str | None = None
    date_time_formatting_options: DateTimeFormattingOptions | None = Field(
        default=None, alias="dateTimeFormattingOptions"
    )
    format_numbers: bool = Field(default=False, alias="formatNumbers")
    null_format_string: str | None = Field(default=None, alias="nullFormatString")


def default_formatting() -> ReportFormattingOptions:
    """The SDK's deterministic formatting defaults (plan.md §4.6).

    ``formatNumbers=false`` (percentages arrive as decimal fractions), ISO date,
    24-hour time, UTC, no locale, no null-substitution.
    """
    return ReportFormattingOptions(
        timezone="Etc/UTC",
        date_time_formatting_options=DateTimeFormattingOptions(
            date_format="YYYY-MM-DD", time_format="24 Hour"
        ),
        format_numbers=False,
    )


class QueryMessageV2(BaseModel):
    """A V2 reporting query (wire: ``QueryMessageV2``).

    The deprecated ``currentInstance`` field is never emitted (plan.md R-J); only
    ``instanceId`` is used. ``from``/``to`` carry the resolved :class:`Period`.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    report_id: str = Field(alias="reportId")
    sub_type: int | None = Field(default=None, alias="subType")
    currency: str | None = None
    instance_id: int | None = Field(default=None, alias="instanceId")
    report_formatting_options: ReportFormattingOptions | None = Field(
        default=None, alias="reportFormattingOptions"
    )
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    dimensions: list[Dimension] = Field(default_factory=list)
    comparative_dimensions: list[ComparativeDimension] = Field(
        default_factory=list, alias="comparativeDimensions"
    )
    filters: list[Filter] = Field(default_factory=list)
    hash: str | None = None
    hide_report_url: bool | None = Field(default=None, alias="hideReportUrl")

    @field_validator("dimensions", mode="before")
    @classmethod
    def _coerce_dims(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [Dimension.coerce(v) for v in value]
        return value

    @field_validator("comparative_dimensions", mode="before")
    @classmethod
    def _coerce_comp(cls, value: Any) -> Any:
        if value is None:
            return []
        return value

    @field_validator("filters", mode="before")
    @classmethod
    def _coerce_filters(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [Filter.coerce(v) for v in value]
        return value

    def to_wire(self) -> dict[str, Any]:
        """Serialise to a request body matching the official examples.

        ``from``/``to`` are emitted as millisecond ISO-8601 with a ``Z`` suffix to
        match the vendor examples exactly, rather than Pydantic's default isoformat.
        """
        body = self.model_dump(by_alias=True, exclude_none=True)
        if self.from_ is not None:
            body["from"] = _iso(self.from_)
        if self.to is not None:
            body["to"] = _iso(self.to)
        # Empty collections are dropped to keep the payload minimal and matching.
        for key in ("dimensions", "comparativeDimensions", "filters"):
            if key in body and not body[key]:
                del body[key]
        return body


class LoginModel(BaseModel):
    """Credentials body for ``POST /token`` (wire: ``LoginModel``)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    username: str
    password: str


# --------------------------------------------------------------------------- #
# Export / pivot models (plan.md §7.3)
# --------------------------------------------------------------------------- #
class DataDimensionConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    dimension_name: str = Field(alias="dimensionName")
    aggregate_function: str = Field(alias="aggregateFunction")


class PivotFilter(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    dimension_name: str = Field(alias="dimensionName")
    excluded_values: list[str] = Field(alias="excludedValues")


class PivotConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    row_dimensions: list[str] = Field(alias="rowDimensions")
    column_dimensions: list[str] = Field(alias="columnDimensions")
    data_dimensions: list[DataDimensionConfig] = Field(alias="dataDimensions")
    filters: list[PivotFilter] | None = None
    calculated_fields: list[str] | None = Field(default=None, alias="calculatedFields")
    show_column_grand_totals: bool | None = Field(
        default=None, alias="showColumnGrandTotals"
    )


__all__ = [
    "Sort",
    "Dimension",
    "ComparativeDimension",
    "Filter",
    "DateTimeFormattingOptions",
    "ReportFormattingOptions",
    "default_formatting",
    "QueryMessageV2",
    "LoginModel",
    "DataDimensionConfig",
    "PivotFilter",
    "PivotConfig",
]
