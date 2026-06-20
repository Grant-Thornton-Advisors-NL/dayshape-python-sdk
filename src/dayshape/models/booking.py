"""The ``Booking`` model (wire report ``TaskListing``; entity vocabulary 'Task')."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from ..dims import TaskDim
from ..exceptions import QueryError
from .base import DateTimeValue, DayshapeModel

if TYPE_CHECKING:
    from .._query import ReportQuery
    from ..period import Period
    from ..reports.query import Filter
    from .job import Job
    from .worker import Worker


class Booking(DayshapeModel):
    """A Booking (a Resource's assignment to an Engagement over a time window)."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        TaskDim.ID,
        TaskDim.START,
        TaskDim.END,
        TaskDim.STATE,
        TaskDim.JOB_ID,
        TaskDim.WORKER_ID,
    )

    id: int | None = Field(default=None, alias="TaskId")
    mapping_id: str | None = Field(default=None, alias="TaskMappingId")
    start: DateTimeValue | None = Field(default=None, alias="TaskStart")
    end: datetime | None = Field(default=None, alias="TaskEnd")
    state: str | None = Field(default=None, alias="TaskState")
    workflow: str | None = Field(default=None, alias="TaskWorkflow")
    assignee: str | None = Field(default=None, alias="Assignee")
    chargeable_hours: float | None = Field(default=None, alias="TaskUtilisationHours")
    traits: str | None = Field(default=None, alias="TaskTraits")
    worker_id: int | None = Field(default=None, alias="TaskWorkerId")
    worker_remote_id: str | None = Field(default=None, alias="TaskWorkerRemoteId")
    job_id: int | None = Field(default=None, alias="TaskJobId")
    job_code: str | None = Field(default=None, alias="TaskJobCode")
    job_name: str | None = Field(default=None, alias="TaskJobName")
    client_name: str | None = Field(default=None, alias="TaskJobClientName")
    parent_job_group_id: int | None = Field(default=None, alias="TaskParentJobGroupId")
    notes: str | None = Field(default=None, alias="TaskDescription")

    @property
    def traits_list(self) -> list[str]:
        return self._split(self.traits)

    def _rel(self, period: "Period | None") -> "Period | None":
        return period if period is not None else self._period

    def job(
        self,
        *,
        period: "Period | None" = None,
        dimensions: Sequence[Any] | None = None,
        filters: "Sequence[Filter]" = (),
    ) -> "ReportQuery[Job]":
        """The Engagement this Booking belongs to (``JobListing`` + ``JobIdFilter``)."""
        if self.job_id is None:
            raise QueryError(
                "This Booking has no job_id; request TaskDim.JOB_ID to navigate to "
                "its Engagement."
            )
        return self._bound_client().jobs.by_ids(
            [self.job_id], period=self._rel(period), dimensions=dimensions, filters=filters
        )

    def worker(
        self,
        *,
        period: "Period | None" = None,
        dimensions: Sequence[Any] | None = None,
        filters: "Sequence[Filter]" = (),
    ) -> "ReportQuery[Worker]":
        """The assigned Resource (``WorkerListing`` + ``WorkerIdFilter``)."""
        if self.worker_id is None:
            raise QueryError(
                "This Booking has no worker_id; request TaskDim.WORKER_ID to navigate "
                "to the assigned Resource."
            )
        return self._bound_client().workers.by_ids(
            [self.worker_id],
            period=self._rel(period),
            dimensions=dimensions,
            filters=filters,
        )


__all__ = ["Booking"]
