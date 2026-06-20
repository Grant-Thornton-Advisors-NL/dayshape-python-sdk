"""The Jobs (Engagements) resource (``JobListing``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from ..filters import JobIdFilter, JobTextFilter
from ..models.base import DayshapeModel
from ..models.job import Job
from ..reports.query import Filter
from .base import ResourceClient


class JobResource(ResourceClient[Job]):
    report_id: ClassVar[str] = "JobListing"
    model: ClassVar[type[DayshapeModel]] = Job

    def _id_filter(self, ids: Sequence[int]) -> Filter:
        return JobIdFilter(ids)

    def _text_filter(self, text: str) -> Filter:
        return JobTextFilter(text)


__all__ = ["JobResource"]
