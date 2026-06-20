"""The Units resource (``UnitListing``)."""

from __future__ import annotations

from typing import ClassVar

from ..models.base import DayshapeModel
from ..models.unit import Unit
from .base import ResourceClient


class UnitResource(ResourceClient[Unit]):
    report_id: ClassVar[str] = "UnitListing"
    model: ClassVar[type[DayshapeModel]] = Unit


__all__ = ["UnitResource"]
