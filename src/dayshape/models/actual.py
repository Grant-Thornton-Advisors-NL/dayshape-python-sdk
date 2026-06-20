"""The ``Actual`` model (wire report ``ActualListing``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from ..exceptions import QueryError
from .base import DayshapeModel

if TYPE_CHECKING:
    from .._query import ReportQuery
    from ..period import Period
    from ..reports.query import Filter
    from .worker import Worker


class Actual(DayshapeModel):
    """An actual (recorded) time entry against an Engagement."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "ActualId",
        "ActualWorkerId",
        "ActualParentJobId",
    )

    id: int | None = Field(default=None, alias="ActualId")
    parent_job_id: int | None = Field(default=None, alias="ActualParentJobId")
    parent_job_name: str | None = Field(default=None, alias="ActualParentJobName")
    parent_job_currency: str | None = Field(
        default=None, alias="ActualParentJobCurrency"
    )
    client_name: str | None = Field(default=None, alias="ActualParentJobClientName")
    remote_id: str | None = Field(default=None, alias="ActualRemoteId")
    worker_id: int | None = Field(default=None, alias="ActualWorkerId")
    worker_name: str | None = Field(default=None, alias="ActualWorkerName")
    worker_remote_id: str | None = Field(default=None, alias="ActualWorkerRemoteId")

    def worker(
        self,
        *,
        period: "Period | None" = None,
        dimensions: Sequence[Any] | None = None,
        filters: "Sequence[Filter]" = (),
    ) -> "ReportQuery[Worker]":
        """The Resource who recorded this actual."""
        if self.worker_id is None:
            raise QueryError(
                "This Actual has no worker_id; request ActualDim.WORKER_ID to "
                "navigate to the Resource."
            )
        rel = period if period is not None else self._period
        return self._bound_client().workers.by_ids(
            [self.worker_id], period=rel, dimensions=dimensions, filters=filters
        )


__all__ = ["Actual"]
