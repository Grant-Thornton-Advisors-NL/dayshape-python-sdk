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
        "ExchangeRateRate",
    )

    currency_from: str | None = Field(default=None, alias="ExchangeRateCurrencyFrom")
    currency_to: str | None = Field(default=None, alias="ExchangeRateCurrencyTo")
    # Live wire id is ``ExchangeRateRate`` (verified against /v2/metadata on a
    # v26.3 server); the bare ``ExchangeRate`` id from the v25.7 workbook does
    # not exist and left this field permanently null.
    rate: float | None = Field(default=None, alias="ExchangeRateRate")


__all__ = ["ExchangeRate"]
