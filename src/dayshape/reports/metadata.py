"""Typed runtime metadata models (plan.md §4.7).

``GET /v2/metadata?reportId=&reportSubTypeId=`` returns the dimensions and filter
group definitions available for a report — the runtime-discovery channel for
tenant custom-member dimensions. Every attribute is declared (no ``hasattr``
probing), and the model feeds the optional pre-flight :class:`QueryError`
validation.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FilterType(StrEnum):
    """The kinds of filter input a filter group exposes (wire: ``FilterType``)."""

    SELECTOR = "selector"
    TEXT = "text"
    PICKER = "picker"
    IN_OUT_PICKER = "inOutPicker"
    JOB_LEADER = "jobLeader"
    JOB_RESOURCE_MGT = "jobResourceMgt"
    JOB_ECONOMICS = "jobEconomics"
    JOB_CREATION_DATE = "jobCreationDate"
    CURRENCY_PICKER = "currencyPicker"


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
    type: FilterType | None = None
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

    def dimension_ids(self) -> frozenset[str]:
        """The set of known dimension ids (for pre-flight validation)."""
        return frozenset(
            d.dimension_id for d in self.dimensions if d.dimension_id is not None
        )


__all__ = [
    "FilterType",
    "DimensionMetadata",
    "FilterDefinition",
    "FilterGroupDefinition",
    "ReportMetadata",
]
