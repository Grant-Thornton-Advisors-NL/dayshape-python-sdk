"""The Actuals resource (``ActualListing``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from .._query import ReportQuery
from ..filters import ActualAssignedResourceFilter
from ..models.actual import Actual
from ..models.base import DayshapeModel
from .base import ResourceClient


class ActualResource(ResourceClient[Actual]):
    report_id: ClassVar[str] = "ActualListing"
    model: ClassVar[type[DayshapeModel]] = Actual

    def by_worker_ids(
        self, worker_ids: Sequence[int], **kwargs: Any
    ) -> "ReportQuery[Actual]":
        """Actuals for the given Resource ids (there is no Actual-id filter)."""
        return self.list(filters=[ActualAssignedResourceFilter(worker_ids)], **kwargs)


__all__ = ["ActualResource"]
