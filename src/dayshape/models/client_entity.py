"""The ``Client`` model (wire report ``ClientListing``)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from .base import DayshapeModel


class Client(DayshapeModel):
    """A client organisation that Engagements are delivered for."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "ClientName",
        "ClientCode",
    )

    name: str | None = Field(default=None, alias="ClientName")
    code: str | None = Field(default=None, alias="ClientCode")
    remote_id: str | None = Field(default=None, alias="ClientRemoteId")
    status: bool | None = Field(default=None, alias="ClientStatus")


__all__ = ["Client"]
