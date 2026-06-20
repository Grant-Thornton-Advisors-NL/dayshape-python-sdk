"""The ``User`` model (wire report ``UserListing``)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from .base import DayshapeModel


class User(DayshapeModel):
    """A Dayshape user account."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "UserId",
        "UserFullName",
        "UserEmail",
    )

    id: int | None = Field(default=None, alias="UserId")
    first_name: str | None = Field(default=None, alias="UserFirstName")
    last_name: str | None = Field(default=None, alias="UserLastName")
    full_name: str | None = Field(default=None, alias="UserFullName")
    guid: str | None = Field(default=None, alias="UserGuid")
    email: str | None = Field(default=None, alias="UserEmail")
    linked_worker: str | None = Field(default=None, alias="UserLinkedWorker")
    timezone: str | None = Field(default=None, alias="UserTimezone")
    is_disabled: bool | None = Field(default=None, alias="UserIsDisabled")
    groups: str | None = Field(default=None, alias="UserGroups")
    viewable_units: str | None = Field(default=None, alias="UserViewableUnits")
    editable_units: str | None = Field(default=None, alias="UserEditableUnits")


__all__ = ["User"]
