"""The ``ExchangeRate`` model (wire report ``ExchangeRateListing``)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from .base import DayshapeModel


class ExchangeRate(DayshapeModel):
    """A currency exchange rate between two reporting currencies."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "ExchangeRateCurrencyFrom",
        "ExchangeRateCurrencyTo",
        "ExchangeRate",
    )

    currency_from: str | None = Field(default=None, alias="ExchangeRateCurrencyFrom")
    currency_to: str | None = Field(default=None, alias="ExchangeRateCurrencyTo")
    rate: float | None = Field(default=None, alias="ExchangeRate")


__all__ = ["ExchangeRate"]
