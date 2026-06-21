"""Typed runtime metadata models (plan.md §4.7).

``GET /v2/metadata?reportId=&reportSubTypeId=`` returns the dimensions and filter
group definitions available for a report — the runtime-discovery channel for
tenant custom-member dimensions. Every attribute is declared (no ``hasattr``
probing), and the model feeds the optional pre-flight :class:`QueryError`
validation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


class FilterType(StrEnum):
    """The kinds of filter input a filter group exposes (wire: ``FilterType``).

    The wire vocabulary is extended by the server over time (e.g. ``date``,
    ``percentage`` and ``jobClaim`` appeared after the v25.7 workbook). Unknown
    values are tolerated rather than rejected — see :data:`FilterTypeValue` — so
    metadata discovery never hard-fails on a newer server (plan.md §4.4, §4.7).
    """

    SELECTOR = "selector"
    TEXT = "text"
    PICKER = "picker"
    IN_OUT_PICKER = "inOutPicker"
    JOB_LEADER = "jobLeader"
    JOB_RESOURCE_MGT = "jobResourceMgt"
    JOB_ECONOMICS = "jobEconomics"
    JOB_CREATION_DATE = "jobCreationDate"
    CURRENCY_PICKER = "currencyPicker"
    DATE = "date"
    PERCENTAGE = "percentage"
    JOB_CLAIM = "jobClaim"


def _coerce_filter_type(value: Any) -> Any:
    """Map a known wire value to :class:`FilterType`, else leave it a raw string.

    The Reporting Service introduces new filter-type tokens between releases; a
    strict enum would crash :meth:`ReportMetadata` (the runtime-discovery
    channel) on any newer server. Unknown values pass through as plain strings —
    they still compare equal to their wire token via :class:`StrEnum` semantics.
    """
    if isinstance(value, str) and not isinstance(value, FilterType):
        try:
            return FilterType(value)
        except ValueError:
            return value
    return value


#: A filter type that upgrades to :class:`FilterType` when known and tolerates
#: novel server tokens as raw strings (plan.md §4.4 warn-not-raise philosophy).
FilterTypeValue = Annotated[FilterType | str, BeforeValidator(_coerce_filter_type)]


class DimensionMetadata(BaseModel):
    """A dimension available for a report: its id and localized display name."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    dimension_id: str | None = Field(default=None, alias="dimensionId")
    display_name: str | None = Field(default=None, alias="displayName")


class FilterDefinition(BaseModel):
    """A single filter input within a filter group (wire: ``FilterDefinitionDto``)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    type: FilterTypeValue | None = None
    data_required: bool = Field(default=False, alias="dataRequired")
    parameter_names: list[str] = Field(default_factory=list, alias="parameterNames")
    selection_placeholder: str | None = Field(
        default=None, alias="selectionPlaceholder"
    )


class FilterGroupDefinition(BaseModel):
    """A group of related filters (wire: ``FilterGroupDefinitionDto``)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    display_name: str | None = Field(default=None, alias="displayName")
    title: str | None = None
    filter_types: list[FilterDefinition] = Field(
        default_factory=list, alias="filterTypes"
    )


class ReportMetadata(BaseModel):
    """Available dimensions and filter groups for a report (wire: ``ReportMetadataMessageV2``)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    dimensions: list[DimensionMetadata] = Field(default_factory=list)
    filter_groups: list[FilterGroupDefinition] = Field(
        default_factory=list, alias="filterGroupDefinitions"
    )

    @property
    def dimension_ids(self) -> frozenset[str]:
        """The set of known dimension ids (for pre-flight validation).

        A ``@property`` so it reads naturally — ``set(md.dimension_ids)`` and
        ``"TaskId" in md.dimension_ids`` work directly (issue #9).
        """
        return frozenset(
            d.dimension_id for d in self.dimensions if d.dimension_id is not None
        )


__all__ = [
    "FilterType",
    "FilterTypeValue",
    "DimensionMetadata",
    "FilterDefinition",
    "FilterGroupDefinition",
    "ReportMetadata",
]
