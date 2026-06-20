"""The ``AuditLogEntry`` model for audit-trail reports (``LogListing*``).

Audit reports vary their columns by entity, so this model declares the handful of
shared fields (timestamps, the acting user) and lets the rest flow through
``model_extra`` — read them via :meth:`field` or :pyattr:`custom_fields`.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import Field

from .base import DateTimeValue, DayshapeModel


class AuditLogEntry(DayshapeModel):
    """One change recorded in an audit trail.

    The first five fields are the dimensions shared by *every* ``LogListing*``
    report (the workbook's "Audit Trail shared Dims-Filters"); ``start``/``end``
    exist only on some reports and stay ``None`` elsewhere.
    """

    default_dimensions: ClassVar[tuple[str, ...]] = ()

    action_time: DateTimeValue | None = Field(default=None, alias="LogActionTime")
    operation: str | None = Field(default=None, alias="LogOperation")
    actor: str | None = Field(default=None, alias="LogActor")
    actor_guid: str | None = Field(default=None, alias="LogActorGuid")
    entity_type: str | None = Field(default=None, alias="LogEntityType")
    changes: str | None = Field(default=None, alias="LogChanges")
    start: DateTimeValue | None = Field(default=None, alias="LogStart")
    end: datetime | None = Field(default=None, alias="LogEnd")


__all__ = ["AuditLogEntry"]
