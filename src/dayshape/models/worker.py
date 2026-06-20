"""The ``Worker`` model (wire report ``WorkerListing``; entity vocabulary 'Worker')."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from ..dims import WorkerDim
from ..exceptions import QueryError
from ..filters import AssignedResourceFilter
from .base import DateValue, DayshapeModel, GuidValue

if TYPE_CHECKING:
    from .._query import ReportQuery
    from ..period import Period
    from ..reports.query import ComparativeDimension, Filter
    from .booking import Booking
    from .job import Job


class Worker(DayshapeModel):
    """A Resource (person who can be booked onto Engagements)."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        WorkerDim.ID,
        WorkerDim.NAME,
        WorkerDim.FIRST_NAME,
        WorkerDim.LAST_NAME,
        WorkerDim.EMAIL,
    )

    id: int | None = Field(default=None, alias="WorkerId")
    first_name: str | None = Field(default=None, alias="WorkerFirstName")
    middle_name: str | None = Field(default=None, alias="WorkerMiddleName")
    last_name: str | None = Field(default=None, alias="WorkerLastName")
    name: str | None = Field(default=None, alias="WorkerName")
    remote_id: str | None = Field(default=None, alias="WorkerRemoteId")
    mapping_id: GuidValue | None = Field(default=None, alias="WorkerMappingId")
    email: str | None = Field(default=None, alias="WorkerEmail")
    employment_start: DateValue | None = Field(
        default=None, alias="WorkerEmploymentStart"
    )
    employment_end: DateValue | None = Field(default=None, alias="WorkerEmploymentEnd")
    is_remote_sync_enabled: bool | None = Field(
        default=None, alias="WorkerIsRemoteSyncEnabled"
    )
    trait_names: str | None = Field(default=None, alias="WorkerTraitNames")
    functional_unit: str | None = Field(default=None, alias="WorkerFunctionalUnit")
    geographical_unit: str | None = Field(default=None, alias="WorkerGeographicalUnit")

    @property
    def traits_list(self) -> list[str]:
        return self._split(self.trait_names)

    def _rel(self, period: "Period | None") -> "Period | None":
        return period if period is not None else self._period

    def _require_id(self) -> int:
        if self.id is None:
            raise QueryError(
                "This Worker has no id; request WorkerDim.ID to navigate its relations."
            )
        return self.id

    def jobs(
        self,
        *,
        period: "Period | None" = None,
        dimensions: Sequence[Any] | None = None,
        filters: "Sequence[Filter]" = (),
        comparative_dimensions: "Sequence[ComparativeDimension]" = (),
        chunk: Any = None,
    ) -> "ReportQuery[Job]":
        """Engagements this Resource is assigned to (``JobListing`` + ``AssignedResourceFilter``)."""
        return self._bound_client().jobs.list(
            period=self._rel(period),
            dimensions=dimensions,
            filters=(AssignedResourceFilter([self._require_id()]), *filters),
            comparative_dimensions=comparative_dimensions,
            chunk=chunk,
        )

    def bookings(
        self,
        *,
        period: "Period | None" = None,
        dimensions: Sequence[Any] | None = None,
        filters: "Sequence[Filter]" = (),
        comparative_dimensions: "Sequence[ComparativeDimension]" = (),
        chunk: Any = None,
    ) -> "ReportQuery[Booking]":
        """Bookings assigned to this Resource (``TaskListing`` + ``AssignedResourceFilter``)."""
        return self._bound_client().bookings.list(
            period=self._rel(period),
            dimensions=dimensions,
            filters=(AssignedResourceFilter([self._require_id()]), *filters),
            comparative_dimensions=comparative_dimensions,
            chunk=chunk,
        )


__all__ = ["Worker"]
