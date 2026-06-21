"""Typed filter builders (plan.md §6, §7.2).

Each builder subclasses :class:`~dayshape.reports.query.Filter`, fixing the wire
``filterId`` and mapping friendly snake_case keyword arguments to the camelCase
``parameters`` the API expects. All filters are ANDed server-side. Parameter
names are taken verbatim from the Reporting Service Detail workbook (v25.7.0.0).

For any filter without a typed builder here, use :class:`RawFilter` (arbitrary
id + parameters) or :class:`CustomFieldFilter` (tenant custom-field filters).
"""
# NB: the docstring above cites the v25.7.0.0 workbook because the typed builders
# below were authored from it; v26.3.0 added reports/dimensions but did not change
# any existing filter parameter names. New v26.3 reports (Suggestion/Grade/Custom
# Member audit trails, JobTaskPhaseListing) are reachable via RawFilter.

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ..period import _iso
from ..reports.query import Filter


def _drop(params: dict[str, Any]) -> dict[str, Any] | None:
    cleaned = {k: v for k, v in params.items() if v is not None}
    return cleaned or None


# --------------------------------------------------------------------------- #
# Escape hatches
# --------------------------------------------------------------------------- #
class RawFilter(Filter):
    """Any ``filterId`` + ``parameters`` — the catch-all for untyped filters."""

    def __init__(self, filter_id: str, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(filter_id=filter_id, parameters=parameters)


class CustomFieldFilter(Filter):
    """A tenant custom-field filter; ``filter_id`` is the custom field's filter id."""

    def __init__(
        self,
        filter_id: str,
        *,
        selected_ids: Sequence[int] | None = None,
        text: str | None = None,
        **parameters: Any,
    ) -> None:
        params = dict(parameters)
        if selected_ids is not None:
            params["selectedIds"] = list(selected_ids)
        if text is not None:
            params["text"] = text
        super().__init__(filter_id=filter_id, parameters=params or None)


# --------------------------------------------------------------------------- #
# Booking (Task) filters
# --------------------------------------------------------------------------- #
class TaskIdFilter(Filter):
    """Filter Bookings by their ids."""

    def __init__(self, task_ids: Sequence[int]) -> None:
        super().__init__(filter_id="TaskIdFilter", parameters={"taskIds": list(task_ids)})


class TaskWorkflowStateFilter(Filter):
    """Filter Bookings by workflow state id."""

    def __init__(
        self, state_ids: Sequence[int], *, is_inclusive: bool | None = None
    ) -> None:
        super().__init__(
            filter_id="TaskWorkflowStateFilter",
            parameters=_drop({"stateIds": list(state_ids), "isInclusive": is_inclusive}),
        )


class TaskTraitFilter(Filter):
    """Filter Bookings by trait ids."""

    def __init__(
        self, trait_ids: Sequence[int], *, is_inclusive: bool | None = None
    ) -> None:
        super().__init__(
            filter_id="TaskTraitFilter",
            parameters=_drop({"traitIds": list(trait_ids), "isInclusive": is_inclusive}),
        )


class TaskAssignmentStatusFilter(Filter):
    """Filter Bookings by whether they are assigned."""

    def __init__(self, assigned: bool) -> None:
        super().__init__(
            filter_id="TaskAssignmentStatusFilter",
            parameters={"assignmentValue": assigned},
        )


class AssignedResourceFilter(Filter):
    """Filter Bookings/Engagements by the assigned Resource ids."""

    def __init__(self, worker_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="AssignedResourceFilter",
            parameters={"workerIds": list(worker_ids)},
        )


class AssignedResourceGradeFilter(Filter):
    def __init__(
        self, grade_ids: Sequence[int], *, is_inclusive: bool | None = None
    ) -> None:
        super().__init__(
            filter_id="AssignedResourceGradeFilter",
            parameters=_drop({"gradeIds": list(grade_ids), "isInclusive": is_inclusive}),
        )


class AssignedResourceTraitFilter(Filter):
    def __init__(self, trait_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="AssignedResourceTraitFilter",
            parameters={"traitIds": list(trait_ids)},
        )


class AssignedResourceFunctionalUnitFilter(Filter):
    def __init__(self, unit_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="AssignedResourceFunctionalUnitFilter",
            parameters={"unitIds": list(unit_ids)},
        )


class AssignedResourceGeographicalUnitFilter(Filter):
    def __init__(self, unit_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="AssignedResourceGeographicalUnitFilter",
            parameters={"unitIds": list(unit_ids)},
        )


# --------------------------------------------------------------------------- #
# Engagement (Job) filters
# --------------------------------------------------------------------------- #
class JobIdFilter(Filter):
    """Filter Engagements (or related rows) by Engagement ids."""

    def __init__(
        self, ids: Sequence[int], *, is_inclusive: bool | None = None
    ) -> None:
        super().__init__(
            filter_id="JobIdFilter",
            parameters=_drop({"ids": list(ids), "isInclusive": is_inclusive}),
        )


class JobTextFilter(Filter):
    """Filter Engagements by name / code / client name text."""

    def __init__(self, text: str) -> None:
        super().__init__(filter_id="JobTextFilter", parameters={"text": text})


class JobWorkflowStateFilter(Filter):
    """Filter Engagements by workflow state id."""

    def __init__(self, state_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="JobWorkflowStateFilter",
            parameters={"stateIds": list(state_ids)},
        )


class JobClientFilter(Filter):
    def __init__(
        self, client_ids: Sequence[int], *, is_inclusive: bool | None = None
    ) -> None:
        super().__init__(
            filter_id="JobClientFilter",
            parameters=_drop({"clientIds": list(client_ids), "isInclusive": is_inclusive}),
        )


class JobFunctionalUnitIdFilter(Filter):
    def __init__(
        self, functional_unit_ids: Sequence[int], *, is_inclusive: bool | None = None
    ) -> None:
        super().__init__(
            filter_id="JobFunctionalUnitIdFilter",
            parameters=_drop(
                {
                    "functionalUnitIds": list(functional_unit_ids),
                    "isInclusive": is_inclusive,
                }
            ),
        )


class JobGeographicalUnitIdFilter(Filter):
    def __init__(self, geographical_unit_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="JobGeographicalUnitIdFilter",
            parameters={"geographicalUnitIds": list(geographical_unit_ids)},
        )


class JobPriorityFilter(Filter):
    def __init__(self, priority_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="JobPriorityFilter",
            parameters={"priorityIds": list(priority_ids)},
        )


class JobLeaderFilter(Filter):
    """Filter Engagements by partner / manager Resource ids."""

    def __init__(
        self,
        worker_ids: Sequence[int],
        *,
        include_partners: bool | None = None,
        include_managers: bool | None = None,
        include_alt_partners: bool | None = None,
        include_alt_managers: bool | None = None,
        is_inclusive: bool | None = None,
    ) -> None:
        super().__init__(
            filter_id="JobLeaderFilter",
            parameters=_drop(
                {
                    "workerIds": list(worker_ids),
                    "includePartners": include_partners,
                    "includeManagers": include_managers,
                    "includeAltPartners": include_alt_partners,
                    "includeAltManagers": include_alt_managers,
                    "isInclusive": is_inclusive,
                }
            ),
        )


class JobCreationDateFilter(Filter):
    def __init__(
        self, *, start: datetime | None = None, end: datetime | None = None
    ) -> None:
        super().__init__(
            filter_id="JobCreationDateFilter",
            parameters=_drop(
                {
                    "from": _iso(start) if start is not None else None,
                    "to": _iso(end) if end is not None else None,
                }
            ),
        )


class JobHasParentFilter(Filter):
    def __init__(self, has_parent: bool) -> None:
        super().__init__(
            filter_id="JobHasParentFilter", parameters={"hasParent": has_parent}
        )


# --------------------------------------------------------------------------- #
# Engagement Group filters
# --------------------------------------------------------------------------- #
class JobGroupIdFilter(Filter):
    def __init__(
        self, ids: Sequence[int], *, is_inclusive: bool | None = None
    ) -> None:
        super().__init__(
            filter_id="JobGroupIdFilter",
            parameters=_drop({"ids": list(ids), "isInclusive": is_inclusive}),
        )


class JobGroupTextFilter(Filter):
    def __init__(self, text: str) -> None:
        super().__init__(filter_id="JobGroupTextFilter", parameters={"text": text})


class JobGroupWorkflowStateFilter(Filter):
    def __init__(self, state_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="JobGroupWorkflowStateFilter",
            parameters={"stateIds": list(state_ids)},
        )


class JobGroupClientFilter(Filter):
    def __init__(self, client_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="JobGroupClientFilter",
            parameters={"clientIds": list(client_ids)},
        )


class JobGroupPersonnelFilter(Filter):
    def __init__(self, worker_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="JobGroupPersonnelFilter",
            parameters={"workerIds": list(worker_ids)},
        )


# --------------------------------------------------------------------------- #
# Resource (Worker) filters
# --------------------------------------------------------------------------- #
class WorkerIdFilter(Filter):
    """Filter Resources by their ids."""

    def __init__(self, ids: Sequence[int]) -> None:
        super().__init__(filter_id="WorkerIdFilter", parameters={"ids": list(ids)})


class WorkerTextFilter(Filter):
    def __init__(self, text: str) -> None:
        super().__init__(filter_id="WorkerTextFilter", parameters={"text": text})


class WorkerGradeFilter(Filter):
    def __init__(self, grade_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="WorkerGradeFilter", parameters={"gradeIds": list(grade_ids)}
        )


class WorkerWorkerTraitFilter(Filter):
    def __init__(self, trait_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="WorkerWorkerTraitFilter",
            parameters={"traitIds": list(trait_ids)},
        )


class WorkerFunctionalUnitIdFilter(Filter):
    def __init__(self, unit_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="WorkerFunctionalUnitIdFilter",
            parameters={"unitIds": list(unit_ids)},
        )


class WorkerGeographicalUnitIdFilter(Filter):
    def __init__(self, unit_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="WorkerGeographicalUnitIdFilter",
            parameters={"unitIds": list(unit_ids)},
        )


class WorkerEmailFilter(Filter):
    def __init__(self, text: str) -> None:
        super().__init__(filter_id="WorkerEmailFilter", parameters={"text": text})


# --------------------------------------------------------------------------- #
# Unavailability filters
# --------------------------------------------------------------------------- #
class UnavailabilityResourceFilter(Filter):
    """Filter Unavailabilities by Resource ids."""

    def __init__(self, ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="UnavailabilityResourceFilter", parameters={"ids": list(ids)}
        )


class UnavailabilityTextFilter(Filter):
    def __init__(self, text: str) -> None:
        super().__init__(
            filter_id="UnavailabilityTextFilter", parameters={"text": text}
        )


class UnavailabilityWorkflowStateFilter(Filter):
    def __init__(self, state_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="UnavailabilityWorkflowStateFilter",
            parameters={"stateIds": list(state_ids)},
        )


class UnavailabilityTraitFilter(Filter):
    def __init__(self, trait_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="UnavailabilityTraitFilter",
            parameters={"traitIds": list(trait_ids)},
        )


# --------------------------------------------------------------------------- #
# User filters
# --------------------------------------------------------------------------- #
class UserIdFilter(Filter):
    def __init__(self, user_ids: Sequence[int]) -> None:
        super().__init__(filter_id="UserIdFilter", parameters={"userIds": list(user_ids)})


class UserTextFilter(Filter):
    def __init__(self, text: str) -> None:
        super().__init__(filter_id="UserTextFilter", parameters={"text": text})


class UserStatusFilter(Filter):
    def __init__(self, enabled: bool) -> None:
        super().__init__(filter_id="UserStatusFilter", parameters={"enabled": enabled})


class UserLinkedWorkerFilter(Filter):
    def __init__(self, worker_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="UserLinkedWorkerFilter",
            parameters={"workerIds": list(worker_ids)},
        )


# --------------------------------------------------------------------------- #
# Client / Trait / Restriction / Actual filters
# --------------------------------------------------------------------------- #
class ClientTextFilter(Filter):
    def __init__(self, text: str) -> None:
        super().__init__(filter_id="ClientTextFilter", parameters={"text": text})


class ClientStatusFilter(Filter):
    def __init__(self, status: Any) -> None:
        super().__init__(filter_id="ClientStatusFilter", parameters={"status": status})


class TraitSupportedEntityTypeFilter(Filter):
    def __init__(self, entity_type: str) -> None:
        super().__init__(
            filter_id="TraitSupportedEntityTypeFilter",
            parameters={"entityType": entity_type},
        )


class RestrictionClientFilter(Filter):
    def __init__(self, ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="RestrictionClientFilter", parameters={"ids": list(ids)}
        )


class ActualAssignedResourceFilter(Filter):
    def __init__(self, worker_ids: Sequence[int]) -> None:
        super().__init__(
            filter_id="ActualAssignedResourceFilter",
            parameters={"workerIds": list(worker_ids)},
        )


__all__ = [
    "RawFilter",
    "CustomFieldFilter",
    # Booking
    "TaskIdFilter",
    "TaskWorkflowStateFilter",
    "TaskTraitFilter",
    "TaskAssignmentStatusFilter",
    "AssignedResourceFilter",
    "AssignedResourceGradeFilter",
    "AssignedResourceTraitFilter",
    "AssignedResourceFunctionalUnitFilter",
    "AssignedResourceGeographicalUnitFilter",
    # Engagement
    "JobIdFilter",
    "JobTextFilter",
    "JobWorkflowStateFilter",
    "JobClientFilter",
    "JobFunctionalUnitIdFilter",
    "JobGeographicalUnitIdFilter",
    "JobPriorityFilter",
    "JobLeaderFilter",
    "JobCreationDateFilter",
    "JobHasParentFilter",
    # Engagement Group
    "JobGroupIdFilter",
    "JobGroupTextFilter",
    "JobGroupWorkflowStateFilter",
    "JobGroupClientFilter",
    "JobGroupPersonnelFilter",
    # Resource
    "WorkerIdFilter",
    "WorkerTextFilter",
    "WorkerGradeFilter",
    "WorkerWorkerTraitFilter",
    "WorkerFunctionalUnitIdFilter",
    "WorkerGeographicalUnitIdFilter",
    "WorkerEmailFilter",
    # Unavailability
    "UnavailabilityResourceFilter",
    "UnavailabilityTextFilter",
    "UnavailabilityWorkflowStateFilter",
    "UnavailabilityTraitFilter",
    # User
    "UserIdFilter",
    "UserTextFilter",
    "UserStatusFilter",
    "UserLinkedWorkerFilter",
    # Client / Trait / Restriction / Actual
    "ClientTextFilter",
    "ClientStatusFilter",
    "TraitSupportedEntityTypeFilter",
    "RestrictionClientFilter",
    "ActualAssignedResourceFilter",
]
