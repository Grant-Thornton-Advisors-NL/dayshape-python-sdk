"""The Traits resource (``TraitListing``)."""

from __future__ import annotations

from typing import ClassVar

from ..models.base import DayshapeModel
from ..models.trait import Trait
from .base import ResourceClient


class TraitResource(ResourceClient[Trait]):
    report_id: ClassVar[str] = "TraitListing"
    model: ClassVar[type[DayshapeModel]] = Trait


__all__ = ["TraitResource"]
