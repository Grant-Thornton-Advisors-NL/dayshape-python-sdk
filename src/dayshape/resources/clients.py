"""The Clients resource (``ClientListing``)."""

from __future__ import annotations

from typing import ClassVar

from ..filters import ClientTextFilter
from ..models.base import DayshapeModel
from ..models.client_entity import Client
from ..reports.query import Filter
from .base import ResourceClient


class ClientResource(ResourceClient[Client]):
    report_id: ClassVar[str] = "ClientListing"
    model: ClassVar[type[DayshapeModel]] = Client

    def _text_filter(self, text: str) -> Filter:
        return ClientTextFilter(text)


__all__ = ["ClientResource"]
