"""The time-series namespace (``client.timeseries``) — the pivot/over-time reports.

**Row granularity (issue #5).** Over-time reports return one row *per identity per
time bucket*, not one row per identity. ``availability()`` over a three-week window
yields roughly 22 rows per worker (one per day), and the count scales with the
window. A caller that treats one row as one worker over-counts accordingly. To
collapse to one row per identity, pass ``dedupe_on=<identity dimension>`` (issue
#6) — it keeps the first row seen per key. To *sum* a numeric column across the
buckets instead of dropping rows, aggregate the streamed rows yourself, or use
:meth:`TimeSeriesNamespace.utilisation_rate` for the worked utilisation case.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .._query import ReportQuery
from ..dims import AvailabilityDim
from ..models.pivot import PivotRow
from ..reports.query import (
    ComparativeDimension,
    Filter,
    ReportFormattingOptions,
)
from .base import ClientView, ResourceClient

#: method name -> (wire report id, sensible default dimensions)
_REPORTS: dict[str, tuple[str, list[str]]] = {
    "availability": (
        "Availability",
        ["AvailabilityWorkerName", "AvailabilityWorkerGrade"],
    ),
    "availability_planning": (
        "AvailabilityPlanning",
        ["AvailabilityWorkerName", "AvailabilityWorkerGrade"],
    ),
    "utilisation": (
        "Utilisation",
        ["AvailabilityWorkerName", "AvailabilityDate"],
    ),
    "booking_hours": (
        "TaskHoursByTime",
        ["FragmentHours", "FragmentDate", "FragmentMonth"],
    ),
    "unavailability_hours": (
        "UnavailabilityHoursByTime",
        ["FragmentHours", "FragmentDate", "FragmentMonth"],
    ),
    "clash_hours": (
        "ClashHoursByTime",
        ["AvailabilityWorkerName", "AvailabilityWorkerGrade"],
    ),
    "conflict_hours": (
        "ConflictHours",
        ["ConflictWorkerName", "ConflictWorkerGrade"],
    ),
    "worker_work_hours": (
        "WorkerWorkHours",
        ["FragmentHours", "FragmentDate", "FragmentMonth"],
    ),
    # RevenueByTime/ComparativeRevenue use the TaskVActual* dimension family,
    # not the Fragment* family of the hours-over-time pivots (verified against
    # /v2/metadata on v26.3). ComparativeRevenue exposes no time-bucket dim.
    "revenue": ("RevenueByTime", ["TaskVActualJobName", "TaskVActualMonth"]),
    "comparative_revenue": (
        "ComparativeRevenue",
        ["TaskVActualJobName", "TaskVActualJobClientName"],
    ),
    "schedule_export": (
        "ScheduleExport",
        ["ScheduleExportWorkerName", "ScheduleExportJobName"],
    ),
}


def _as_float(value: Any) -> float:
    """Coerce a cell to ``float``; non-numeric / missing cells count as ``0.0``."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


@dataclass(frozen=True, slots=True)
class WorkerUtilisation:
    """Per-worker utilisation computed from the Availability report (issue #7).

    Hours semantics (the documented trap): ``AvailableHours = WorkHours -
    ScheduledTaskHours`` is *free time*, not capacity, so it is never the
    denominator. Utilisation is ``ScheduledTaskHours / WorkHours``.
    """

    worker: str | None
    scheduled_hours: float
    work_hours: float
    #: Free time over the period (``work_hours - scheduled_hours``), not capacity.
    available_hours: float
    #: ``scheduled_hours / work_hours`` as a fraction in ``[0, 1]``, or ``None``
    #: when there are no work hours to divide by.
    utilisation: float | None


class TimeSeriesNamespace:
    """Pivot / over-time reports, returning :class:`PivotRow` rows.

    See the module docstring for the per-bucket row granularity these reports
    return, and ``dedupe_on=`` for collapsing it.
    """

    def __init__(self, view: ClientView) -> None:
        self._view = view

    def report(
        self,
        name: str,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        comparative_dimensions: Sequence[ComparativeDimension] = (),
        chunk: Any = None,
        allow_unordered: bool = False,
        dedupe_on: str | None = None,
        sub_type: int | None = None,
        currency: str | None = None,
        formatting: ReportFormattingOptions | None = None,
    ) -> "ReportQuery[PivotRow]":
        """Run a named pivot report (see the methods below for the catalogue).

        These reports return one row per identity per time bucket (see the module
        docstring). ``dedupe_on=`` collapses to the first row per key, and
        ``chunk=`` / ``allow_unordered=`` window large date ranges — all now
        forwarded from the convenience wrappers too (issue #6).
        """
        report_id, default_dims = _REPORTS[name]
        resource: ResourceClient[PivotRow] = ResourceClient(
            self._view,
            report_id=report_id,
            model=PivotRow,
            default_dimensions=default_dims,
        )
        return resource.list(
            period=period,
            dimensions=dimensions,
            filters=filters,
            comparative_dimensions=comparative_dimensions,
            chunk=chunk,
            allow_unordered=allow_unordered,
            dedupe_on=dedupe_on,
            sub_type=sub_type,
            currency=currency,
            formatting=formatting,
        )

    def availability(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Availability over time. Returns one row per worker per day; pass
        ``dedupe_on=AvailabilityDim.WORKER_NAME`` to collapse to one per worker."""
        return self.report("availability", **kwargs)

    def availability_planning(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Availability planning over time (one row per worker per time bucket)."""
        return self.report("availability_planning", **kwargs)

    def utilisation(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Run the ``Utilisation`` pivot report (one row per worker per bucket).

        Caveat (issue #7): on some live server versions the ``Utilisation`` report
        does **not** expose a usable utilisation figure (nor ``AvailableHours``).
        For a computed rate, prefer :meth:`utilisation_rate`, which derives it from
        the Availability report's hours as ``ScheduledTaskHours / WorkHours``.
        """
        return self.report("utilisation", **kwargs)

    def booking_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Booking (task) hours over time (one row per fragment / time bucket)."""
        return self.report("booking_hours", **kwargs)

    def unavailability_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Unavailability hours over time (one row per fragment / time bucket)."""
        return self.report("unavailability_hours", **kwargs)

    def clash_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Clash hours over time (one row per worker per time bucket)."""
        return self.report("clash_hours", **kwargs)

    def conflict_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Conflict hours over time (one row per worker per time bucket)."""
        return self.report("conflict_hours", **kwargs)

    def worker_work_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Worker work hours over time (one row per fragment / time bucket)."""
        return self.report("worker_work_hours", **kwargs)

    def revenue(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Revenue over time (one row per job per time bucket)."""
        return self.report("revenue", **kwargs)

    def comparative_revenue(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Comparative revenue (no time-bucket dimension; one row per job)."""
        return self.report("comparative_revenue", **kwargs)

    def schedule_export(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        """Master schedule export (one row per worker per booking)."""
        return self.report("schedule_export", **kwargs)

    # -- computed helpers --------------------------------------------------- #
    async def utilisation_rate(
        self,
        *,
        period: Any = None,
        identity: str = AvailabilityDim.WORKER_NAME,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> list[WorkerUtilisation]:
        """Compute utilisation per worker from the Availability report (issue #7).

        The live ``Utilisation`` report does not reliably expose a utilisation
        figure (see :meth:`utilisation`); this derives it the documented way —
        ``ScheduledTaskHours / WorkHours`` — by running the **Availability** report
        and summing each identity's hours across the per-day rows over the period.
        ``AvailableHours = WorkHours - ScheduledTaskHours`` (free time) is reported
        but never used as the denominator.

        Returns a list of :class:`WorkerUtilisation`, sorted by ``worker``.
        """
        dimensions = [
            identity,
            AvailabilityDim.SCHEDULED_TASK_HOURS,
            AvailabilityDim.WORK_HOURS,
        ]
        query = self.report(
            "availability",
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )
        totals: dict[str | None, list[float]] = {}
        async for row in query:
            key = row.field(identity)
            key = str(key) if key is not None else None
            scheduled = _as_float(row.field(AvailabilityDim.SCHEDULED_TASK_HOURS))
            work = _as_float(row.field(AvailabilityDim.WORK_HOURS))
            acc = totals.setdefault(key, [0.0, 0.0])
            acc[0] += scheduled
            acc[1] += work
        results = [
            WorkerUtilisation(
                worker=worker,
                scheduled_hours=scheduled,
                work_hours=work,
                available_hours=work - scheduled,
                utilisation=(scheduled / work) if work else None,
            )
            for worker, (scheduled, work) in totals.items()
        ]
        results.sort(key=lambda w: (w.worker is None, w.worker or ""))
        return results


__all__ = ["TimeSeriesNamespace", "WorkerUtilisation"]
