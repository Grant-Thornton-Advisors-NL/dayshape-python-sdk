"""The time-series namespace (``client.timeseries``) — the pivot/over-time reports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .._query import ReportQuery
from ..models.pivot import PivotRow
from ..reports.query import Filter
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


class TimeSeriesNamespace:
    """Pivot / over-time reports, returning :class:`PivotRow` rows."""

    def __init__(self, view: ClientView) -> None:
        self._view = view

    def report(
        self,
        name: str,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[PivotRow]":
        """Run a named pivot report (see the methods below for the catalogue)."""
        report_id, default_dims = _REPORTS[name]
        resource: ResourceClient[PivotRow] = ResourceClient(
            self._view,
            report_id=report_id,
            model=PivotRow,
            default_dimensions=default_dims,
        )
        return resource.list(
            period=period, dimensions=dimensions, filters=filters, chunk=chunk
        )

    def availability(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("availability", **kwargs)

    def availability_planning(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("availability_planning", **kwargs)

    def utilisation(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("utilisation", **kwargs)

    def booking_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("booking_hours", **kwargs)

    def unavailability_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("unavailability_hours", **kwargs)

    def clash_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("clash_hours", **kwargs)

    def conflict_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("conflict_hours", **kwargs)

    def worker_work_hours(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("worker_work_hours", **kwargs)

    def revenue(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("revenue", **kwargs)

    def comparative_revenue(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("comparative_revenue", **kwargs)

    def schedule_export(self, **kwargs: Any) -> "ReportQuery[PivotRow]":
        return self.report("schedule_export", **kwargs)


__all__ = ["TimeSeriesNamespace"]
