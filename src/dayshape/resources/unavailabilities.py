"""The Unavailabilities resource (``UnavailabilityListing``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from .._query import ReportQuery
from ..filters import UnavailabilityResourceFilter, UnavailabilityTextFilter
from ..models.base import DayshapeModel
from ..models.unavailability import Unavailability
from ..reports.query import Filter
from .base import ResourceClient


class UnavailabilityResource(ResourceClient[Unavailability]):
    report_id: ClassVar[str] = "UnavailabilityListing"
    model: ClassVar[type[DayshapeModel]] = Unavailability

    def _text_filter(self, text: str) -> Filter:
        return UnavailabilityTextFilter(text)

    def by_worker_ids(
        self, worker_ids: Sequence[int], **kwargs: Any
    ) -> "ReportQuery[Unavailability]":
        """Unavailabilities for the given Resource ids (there is no Unavailability-id filter)."""
        return self.list(filters=[UnavailabilityResourceFilter(worker_ids)], **kwargs)


__all__ = ["UnavailabilityResource"]
