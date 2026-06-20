"""The ``PivotRow`` model for time-series / pivot reports.

Pivot reports project a small number of identity dimensions plus a wide set of
dynamic time-fragment columns (``FragmentHours``, per-date/-week/-month values).
Those dynamic columns are not declared; access them via :meth:`field` or
:pyattr:`custom_fields`.
"""

from __future__ import annotations

from typing import Any, ClassVar

from .base import DayshapeModel


class PivotRow(DayshapeModel):
    """One row of a pivot / over-time report."""

    default_dimensions: ClassVar[tuple[str, ...]] = ()

    def values(self) -> dict[str, Any]:
        """All decoded cells of this row, declared and dynamic alike."""
        return dict(self.model_extra or {})


__all__ = ["PivotRow"]
