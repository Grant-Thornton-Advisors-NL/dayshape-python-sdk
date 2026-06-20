"""The ``Unit`` model (wire report ``UnitListing``)."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import Field

from .base import DateTimeValue, DayshapeModel


class Unit(DayshapeModel):
    """A business unit or location in the org hierarchy."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "UnitName",
        "UnitParentName",
        "UnitLevelName",
    )

    hierarchy_name: str | None = Field(default=None, alias="UnitHierarchyName")
    name: str | None = Field(default=None, alias="UnitName")
    parent_name: str | None = Field(default=None, alias="UnitParentName")
    path: str | None = Field(default=None, alias="UnitPath")
    start: DateTimeValue | None = Field(default=None, alias="UnitStart")
    end: datetime | None = Field(default=None, alias="UnitEnd")
    level_name: str | None = Field(default=None, alias="UnitLevelName")
    remote_id: str | None = Field(default=None, alias="UnitRemoteId")


__all__ = ["Unit"]
