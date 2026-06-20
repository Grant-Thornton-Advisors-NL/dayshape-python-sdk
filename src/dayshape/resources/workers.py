"""The Workers (Resources) resource (``WorkerListing``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from ..filters import WorkerIdFilter, WorkerTextFilter
from ..models.base import DayshapeModel
from ..models.worker import Worker
from ..reports.query import Filter
from .base import ResourceClient


class WorkerResource(ResourceClient[Worker]):
    report_id: ClassVar[str] = "WorkerListing"
    model: ClassVar[type[DayshapeModel]] = Worker

    def _id_filter(self, ids: Sequence[int]) -> Filter:
        return WorkerIdFilter(ids)

    def _text_filter(self, text: str) -> Filter:
        return WorkerTextFilter(text)


__all__ = ["WorkerResource"]
