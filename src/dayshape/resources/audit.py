"""The audit-trail namespace (``client.audit``) — the ``LogListing*`` reports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .._query import ReportQuery
from ..models.audit import AuditLogEntry
from ..reports.query import Filter
from .base import ClientView, ResourceClient


class AuditNamespace:
    """Audit trails for each entity, returning :class:`AuditLogEntry` rows."""

    def __init__(self, view: ClientView) -> None:
        self._view = view

    def _run(
        self,
        report_id: str,
        default_dims: Sequence[str],
        *,
        period: Any,
        dimensions: Any,
        filters: Sequence[Filter],
        chunk: Any,
    ) -> "ReportQuery[AuditLogEntry]":
        resource: ResourceClient[AuditLogEntry] = ResourceClient(
            self._view,
            report_id=report_id,
            model=AuditLogEntry,
            default_dimensions=list(default_dims),
        )
        return resource.list(
            period=period, dimensions=dimensions, filters=filters, chunk=chunk
        )

    def jobs(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        return self._run(
            "LogListingJob",
            ["LogJobId", "LogJobName", "LogActionTime", "LogOperation", "LogActor"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def bookings(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        return self._run(
            "LogListingTask",
            ["LogTaskMappingId", "LogJobId", "LogJobName", "LogActionTime", "LogOperation"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def workers(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        return self._run(
            "LogListingWorker",
            ["LogWorkerId", "LogWorkerName", "LogActionTime", "LogOperation", "LogActor"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def job_groups(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        return self._run(
            "LogListingJobGroup",
            ["LogJobGroupId", "LogJobGroupName", "LogActionTime", "LogOperation", "LogActor"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def traits(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        return self._run(
            "LogListingTrait",
            ["LogActionTime", "LogOperation", "LogActor", "LogEntityType"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def unavailabilities(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        return self._run(
            "LogListingUnavailability",
            ["LogUnavailabilityName", "LogActionTime", "LogOperation", "LogActor"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def users(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        return self._run(
            "LogListingUser",
            ["LogUserGuid", "LogUserFirstName", "LogUserLastName", "LogActionTime", "LogOperation"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def settings(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        return self._run(
            "LogListingSetting",
            ["LogSettingName", "LogActionTime", "LogOperation", "LogActor"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def workflow(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        return self._run(
            "LogListingWorkflow",
            ["LogWorkflowName", "LogActionTime", "LogOperation", "LogActor"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def grades(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        """Grade audit trail (new in v26.3; report ``LogListingGrade``)."""
        return self._run(
            "LogListingGrade",
            ["LogGradeName", "LogActionTime", "LogOperation", "LogActor"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def suggestions(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        """Suggestion audit trail (new in v26.3; report ``LogListingSuggestion``)."""
        return self._run(
            "LogListingSuggestion",
            [
                "LogSuggestionId",
                "LogSuggestedWorkerName",
                "LogJobName",
                "LogActionTime",
                "LogOperation",
            ],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )

    def custom_members(
        self,
        *,
        period: Any = None,
        dimensions: Any = None,
        filters: Sequence[Filter] = (),
        chunk: Any = None,
    ) -> "ReportQuery[AuditLogEntry]":
        """Custom member audit trail (new in v26.3; report ``LogListingCustomMember``)."""
        return self._run(
            "LogListingCustomMember",
            ["LogCustomMemberName", "LogActionTime", "LogOperation", "LogActor"],
            period=period,
            dimensions=dimensions,
            filters=filters,
            chunk=chunk,
        )


__all__ = ["AuditNamespace"]
