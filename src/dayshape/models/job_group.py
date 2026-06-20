"""The ``JobGroup`` model (wire report ``JobGroupListing``; Engagement Group)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from .base import DayshapeModel


class JobGroup(DayshapeModel):
    """An Engagement Group (a hierarchical grouping of Engagements)."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "JobGroupId",
        "JobGroupName",
        "JobGroupCode",
        "JobGroupClientName",
        "JobGroupState",
    )

    id: int | None = Field(default=None, alias="JobGroupId")
    name: str | None = Field(default=None, alias="JobGroupName")
    code: str | None = Field(default=None, alias="JobGroupCode")
    has_remote_link: bool | None = Field(default=None, alias="JobGroupHasRemoteLink")
    state: str | None = Field(default=None, alias="JobGroupState")
    workflow: str | None = Field(default=None, alias="JobGroupWorkflow")
    client_name: str | None = Field(default=None, alias="JobGroupClientName")
    client_code: str | None = Field(default=None, alias="JobGroupClientCode")
    level: str | None = Field(default=None, alias="JobGroupLevel")
    has_parent: bool | None = Field(default=None, alias="JobGroupHasParent")
    root_job_group_id: int | None = Field(default=None, alias="JobGroupRootJobGroupId")


__all__ = ["JobGroup"]
