"""Resource façades over the report-execution core (plan.md §6, §7.3)."""

from __future__ import annotations

from .actuals import ActualResource
from .audit import AuditNamespace
from .base import ClientView, ResourceClient
from .bookings import BookingResource
from .clients import ClientResource
from .exchange_rates import ExchangeRateResource
from .job_groups import JobGroupResource
from .job_task_phases import JobTaskPhaseResource
from .jobs import JobResource
from .rates import RateResource
from .reports import RawReportResource
from .timeseries import TimeSeriesNamespace
from .traits import TraitResource
from .unavailabilities import UnavailabilityResource
from .units import UnitResource
from .users import UserResource
from .workers import WorkerResource

__all__ = [
    "ClientView",
    "ResourceClient",
    "ActualResource",
    "BookingResource",
    "ClientResource",
    "ExchangeRateResource",
    "JobGroupResource",
    "JobResource",
    "JobTaskPhaseResource",
    "RateResource",
    "TraitResource",
    "UnavailabilityResource",
    "UnitResource",
    "UserResource",
    "WorkerResource",
    "RawReportResource",
    "AuditNamespace",
    "TimeSeriesNamespace",
]
