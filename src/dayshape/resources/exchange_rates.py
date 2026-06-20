"""The Exchange Rates resource (``ExchangeRateListing``)."""

from __future__ import annotations

from typing import ClassVar

from ..models.base import DayshapeModel
from ..models.exchange_rate import ExchangeRate
from .base import ResourceClient


class ExchangeRateResource(ResourceClient[ExchangeRate]):
    report_id: ClassVar[str] = "ExchangeRateListing"
    model: ClassVar[type[DayshapeModel]] = ExchangeRate


__all__ = ["ExchangeRateResource"]
