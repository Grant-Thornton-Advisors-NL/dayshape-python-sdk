"""The ``Job`` model (wire report ``JobListing``; entity vocabulary 'Job'/Engagement)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from ..dims import JobDim
from ..exceptions import QueryError
from ..filters import JobIdFilter
from .base import DayshapeModel

if TYPE_CHECKING:
    from .._query import ReportQuery
    from ..period import Period
    from ..reports.query import ComparativeDimension, Filter
    from .booking import Booking


class Job(DayshapeModel):
    """An Engagement (a piece of client work that Bookings are scheduled against)."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        JobDim.ID,
        JobDim.CODE,
        JobDim.NAME,
        JobDim.CLIENT_NAME,
        JobDim.STATE,
    )

    id: int | None = Field(default=None, alias="JobId")
    code: str | None = Field(default=None, alias="JobCode")
    name: str | None = Field(default=None, alias="JobName")
    request_number: str | None = Field(default=None, alias="JobRequestNumber")
    has_remote_link: bool | None = Field(default=None, alias="JobHasRemoteLink")
    client_name: str | None = Field(default=None, alias="JobClientName")
    client_code: str | None = Field(default=None, alias="JobClientCode")
    priority: str | None = Field(default=None, alias="JobPriority")
    rate_type: str | None = Field(default=None, alias="JobRateType")
    functional_unit: str | None = Field(default=None, alias="JobFunctionalUnit")
    geographical_unit: str | None = Field(default=None, alias="JobGeographicalUnit")
    lead_worker: str | None = Field(default=None, alias="JobLeadWorker")
    state: str | None = Field(default=None, alias="JobState")
    workflow: str | None = Field(default=None, alias="JobWorkflow")

    def _rel(self, period: "Period | None") -> "Period | None":
        return period if period is not None else self._period

    def _require_id(self) -> int:
        if self.id is None:
            raise QueryError(
                "This Job has no id; request JobDim.ID to navigate its relations."
            )
        return self.id

    def bookings(
        self,
        *,
        period: "Period | None" = None,
        dimensions: Sequence[Any] | None = None,
        filters: "Sequence[Filter]" = (),
        comparative_dimensions: "Sequence[ComparativeDimension]" = (),
        chunk: Any = None,
    ) -> "ReportQuery[Booking]":
        """Bookings scheduled against this Engagement (``TaskListing`` + ``JobIdFilter``)."""
        return self._bound_client().bookings.list(
            period=self._rel(period),
            dimensions=dimensions,
            filters=(JobIdFilter([self._require_id()]), *filters),
            comparative_dimensions=comparative_dimensions,
            chunk=chunk,
        )


__all__ = ["Job"]
