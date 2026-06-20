"""The ``JobTaskPhase`` model (wire report ``JobTaskPhaseListing``; new in v26.3).

A task phase belonging to an Engagement (the workbook calls the report both
"Job Task Phase Listing" and "Engagement Task Phase Listing"). The live v26.3
``/v2/metadata`` exposes a mix of ``Job*`` and ``TaskPhase*`` dimension ids that
neither workbook sheet matches exactly — the aliases below follow the live server
(``JobTaskPhaseJobId`` is live-only and absent from the workbook, so it has no
:mod:`dayshape.dims` constant).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from .base import DayshapeModel


class JobTaskPhase(DayshapeModel):
    """A task phase of an Engagement."""

    default_dimensions: ClassVar[tuple[str, ...]] = (
        "TaskPhaseName",
        "TaskPhaseRemoteId",
        "JobTaskPhaseJobId",
        "JobName",
        "JobRequestNumber",
    )

    phase_name: str | None = Field(default=None, alias="TaskPhaseName")
    phase_remote_id: str | None = Field(default=None, alias="TaskPhaseRemoteId")
    job_id: int | None = Field(default=None, alias="JobTaskPhaseJobId")
    job_name: str | None = Field(default=None, alias="JobName")
    job_request_number: str | None = Field(default=None, alias="JobRequestNumber")


__all__ = ["JobTaskPhase"]
