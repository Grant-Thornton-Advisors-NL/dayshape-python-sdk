"""The ``Unavailability`` model (wire report ``UnavailabilityListing``)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from ..exceptions import QueryError
from .base import DateTimeValue, DateValue, DayshapeModel

if TYPE_CHECKING:
    from .._query import ReportQuery
    from ..period import Period
    from ..reports.query import Filter
    from .worker import Worker


class Unavailability(DayshapeModel):
    """A period a Resource is unavailable to be booked."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "UnavailabilityName",
        "UnavailabilityWorkerId",
        "UnavailabilityStart",
        "UnavailabilityEnd",
        "UnavailabilityState",
    )

    name: str | None = Field(default=None, alias="UnavailabilityName")
    worker_id: int | None = Field(default=None, alias="UnavailabilityWorkerId")
    worker_name: str | None = Field(default=None, alias="UnavailabilityWorkerName")
    start: DateTimeValue | None = Field(default=None, alias="UnavailabilityStart")
    end: datetime | None = Field(default=None, alias="UnavailabilityEnd")
    state: str | None = Field(default=None, alias="UnavailabilityState")
    workflow: str | None = Field(default=None, alias="UnavailabilityWorkflow")
    trait: str | None = Field(default=None, alias="UnavailabilityTrait")
    duration: float | None = Field(default=None, alias="UnavailabilityDuration")
    remote_id: str | None = Field(default=None, alias="UnavailabilityRemoteId")
    worker_start_date: DateValue | None = Field(
        default=None, alias="UnavailabilityWorkerStartDate"
    )

    def worker(
        self,
        *,
        period: "Period | None" = None,
        dimensions: Sequence[Any] | None = None,
        filters: "Sequence[Filter]" = (),
    ) -> "ReportQuery[Worker]":
        """The Resource this Unavailability belongs to."""
        if self.worker_id is None:
            raise QueryError(
                "This Unavailability has no worker_id; request "
                "UnavailabilityDim.WORKER_ID to navigate to the Resource."
            )
        rel = period if period is not None else self._period
        return self._bound_client().workers.by_ids(
            [self.worker_id], period=rel, dimensions=dimensions, filters=filters
        )


__all__ = ["Unavailability"]
