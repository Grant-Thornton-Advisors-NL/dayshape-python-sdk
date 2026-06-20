"""The ``Trait`` model (wire report ``TraitListing``)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from .base import DayshapeModel


class Trait(DayshapeModel):
    """A skill/attribute tag that can be attached to Resources, Bookings, etc."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "TraitName",
        "TraitFamilyName",
    )

    name: str | None = Field(default=None, alias="TraitName")
    remote_id: str | None = Field(default=None, alias="TraitRemoteId")
    description: str | None = Field(default=None, alias="TraitDescription")
    privacy_level: str | None = Field(default=None, alias="TraitPrivacyLevel")
    is_selectable: bool | None = Field(default=None, alias="TraitIsSelectable")
    family_name: str | None = Field(default=None, alias="TraitFamilyName")
    supported_entity_types: str | None = Field(
        default=None, alias="TraitSupportedEntityTypeNames"
    )
    path: str | None = Field(default=None, alias="TraitPath")

    @property
    def supported_entity_types_list(self) -> list[str]:
        return self._split(self.supported_entity_types)


__all__ = ["Trait"]
