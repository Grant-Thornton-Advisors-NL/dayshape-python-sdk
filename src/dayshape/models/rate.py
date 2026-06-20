"""The ``Rate`` model (wire report ``RateListing``)."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import Field

from .base import DateTimeValue, DayshapeModel


class Rate(DayshapeModel):
    """A charge/cost rate effective over a date range."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "RateChargeTypeName",
        "RateValue",
        "RateStart",
        "RateEnd",
        "RateCurrency",
    )

    remote_grade_id: str | None = Field(default=None, alias="RateRemoteGradeId")
    value: float | None = Field(default=None, alias="RateValue")
    start: DateTimeValue | None = Field(default=None, alias="RateStart")
    end: datetime | None = Field(default=None, alias="RateEnd")
    charge_type_name: str | None = Field(default=None, alias="RateChargeTypeName")
    functional_unit: str | None = Field(default=None, alias="RateFunctionalUnit")
    geographical_unit: str | None = Field(default=None, alias="RateGeographicalUnit")
    rate_type: str | None = Field(default=None, alias="RateType")
    currency: str | None = Field(default=None, alias="RateCurrency")


__all__ = ["Rate"]
