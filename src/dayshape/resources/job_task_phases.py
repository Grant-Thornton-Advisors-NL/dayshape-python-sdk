"""The Job Task Phases resource (``JobTaskPhaseListing``; new in v26.3)."""

from __future__ import annotations

from typing import ClassVar

from ..models.base import DayshapeModel
from ..models.job_task_phase import JobTaskPhase
from .base import ResourceClient


class JobTaskPhaseResource(ResourceClient[JobTaskPhase]):
    report_id: ClassVar[str] = "JobTaskPhaseListing"
    model: ClassVar[type[DayshapeModel]] = JobTaskPhase


__all__ = ["JobTaskPhaseResource"]
