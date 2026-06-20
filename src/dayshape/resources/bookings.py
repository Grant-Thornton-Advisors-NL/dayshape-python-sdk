"""The Bookings resource (``TaskListing``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from ..filters import TaskIdFilter
from ..models.base import DayshapeModel
from ..models.booking import Booking
from ..reports.query import Filter
from .base import ResourceClient


class BookingResource(ResourceClient[Booking]):
    report_id: ClassVar[str] = "TaskListing"
    model: ClassVar[type[DayshapeModel]] = Booking

    def _id_filter(self, ids: Sequence[int]) -> Filter:
        return TaskIdFilter(ids)


__all__ = ["BookingResource"]
