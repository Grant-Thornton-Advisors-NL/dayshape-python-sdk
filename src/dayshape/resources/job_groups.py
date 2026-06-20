"""The Job Groups (Engagement Groups) resource (``JobGroupListing``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from ..filters import JobGroupIdFilter, JobGroupTextFilter
from ..models.base import DayshapeModel
from ..models.job_group import JobGroup
from ..reports.query import Filter
from .base import ResourceClient


class JobGroupResource(ResourceClient[JobGroup]):
    report_id: ClassVar[str] = "JobGroupListing"
    model: ClassVar[type[DayshapeModel]] = JobGroup

    def _id_filter(self, ids: Sequence[int]) -> Filter:
        return JobGroupIdFilter(ids)

    def _text_filter(self, text: str) -> Filter:
        return JobGroupTextFilter(text)


__all__ = ["JobGroupResource"]
