"""The Users resource (``UserListing``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from ..filters import UserIdFilter, UserTextFilter
from ..models.base import DayshapeModel
from ..models.user import User
from ..reports.query import Filter
from .base import ResourceClient


class UserResource(ResourceClient[User]):
    report_id: ClassVar[str] = "UserListing"
    model: ClassVar[type[DayshapeModel]] = User

    def _id_filter(self, ids: Sequence[int]) -> Filter:
        return UserIdFilter(ids)

    def _text_filter(self, text: str) -> Filter:
        return UserTextFilter(text)


__all__ = ["UserResource"]
