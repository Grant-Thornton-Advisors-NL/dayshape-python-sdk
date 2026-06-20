"""The Rates resource (``RateListing``)."""

from __future__ import annotations

from typing import ClassVar

from ..models.base import DayshapeModel
from ..models.rate import Rate
from .base import ResourceClient


class RateResource(ResourceClient[Rate]):
    report_id: ClassVar[str] = "RateListing"
    model: ClassVar[type[DayshapeModel]] = Rate


__all__ = ["RateResource"]
