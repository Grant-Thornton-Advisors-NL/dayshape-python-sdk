"""Async Python SDK for the Dayshape Reporting Service API (v2.0).

Quick start::

    from dayshape import DayshapeClient, Period
    from dayshape.dims import TaskDim

    async with DayshapeClient() as client:
        with client.period(Period.fiscal_year(2026)) as c:
            async for booking in c.bookings.list(dimensions=[TaskDim.ID, TaskDim.START]):
                ...
"""

from __future__ import annotations

from . import dims, exceptions, filters, models
from ._version import SPEC_VERSION, __version__
from .client import DayshapeClient, ScopedClient
from .config import DayshapeConfig, RetryConfig, TimeoutConfig
from .exceptions import (
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    ChunkingError,
    ClientClosedError,
    ConcurrentReportLimitError,
    DayshapeConnectionError,
    DayshapeError,
    DayshapeTimeoutError,
    DetachedModelError,
    NotFoundError,
    PermissionDeniedError,
    QueryError,
    RateLimitError,
    ResponseError,
    ResponseFormatError,
    ResponseValidationError,
    ResultTooLargeError,
    ServerError,
    UnknownDimensionError,
)
from .models import (
    Actual,
    AuditLogEntry,
    Booking,
    Client,
    DayshapeModel,
    ExchangeRate,
    Job,
    JobGroup,
    Percentage,
    PivotRow,
    Rate,
    Trait,
    Unavailability,
    Unit,
    User,
    Worker,
)
from .period import Period
from .reports.drift import CatalogueReport, ReportDrift
from .reports.metadata import ReportMetadata
from .reports.query import (
    ComparativeDimension,
    Dimension,
    Filter,
    ReportFormattingOptions,
    Sort,
    default_formatting,
)
from .reports.registry import ReportId, ReportType
from .reports.result import ReportResult, ResultMeta
from .resources.timeseries import WorkerUtilisation

__all__ = [
    "__version__",
    "SPEC_VERSION",
    # client
    "DayshapeClient",
    "ScopedClient",
    "Period",
    # query building
    "Sort",
    "Dimension",
    "ComparativeDimension",
    "Filter",
    "ReportFormattingOptions",
    "default_formatting",
    "ReportId",
    "ReportType",
    "ReportMetadata",
    "ReportResult",
    "ResultMeta",
    "CatalogueReport",
    "ReportDrift",
    "WorkerUtilisation",
    # models
    "DayshapeModel",
    "Percentage",
    "Actual",
    "AuditLogEntry",
    "Booking",
    "Client",
    "ExchangeRate",
    "Job",
    "JobGroup",
    "PivotRow",
    "Rate",
    "Trait",
    "Unavailability",
    "Unit",
    "User",
    "Worker",
    # config
    "DayshapeConfig",
    "TimeoutConfig",
    "RetryConfig",
    # submodules
    "dims",
    "filters",
    "models",
    "exceptions",
    # exceptions (common)
    "DayshapeError",
    "APIStatusError",
    "AuthenticationError",
    "BadRequestError",
    "PermissionDeniedError",
    "RateLimitError",
    "ConcurrentReportLimitError",
    "NotFoundError",
    "ServerError",
    "ResponseError",
    "ResponseValidationError",
    "QueryError",
    "UnknownDimensionError",
    "ChunkingError",
    "DetachedModelError",
    "ClientClosedError",
    "DayshapeConnectionError",
    "DayshapeTimeoutError",
    "ResponseFormatError",
    "ResultTooLargeError",
]
