"""Saved-report handle (plan.md §7.3).

A saved report (built in the UI, lifted by hash) is one noun with two verbs:
``run()`` executes it (``GET /runSavedReport/{hash}``) returning the same lazy
``ReportQuery`` contract as everything else, and ``query()`` retrieves the stored
``QueryMessageV2`` (``GET /getReportQuery/{hash}``) — which can be checked into
version control as a byte-compatibility contract.
"""

from __future__ import annotations

from typing import Any

from .._query import ReportQuery
from .query import QueryMessageV2
from .runner import ReportRunner


class SavedReportRef:
    """A handle on a saved report identified by its UI hash."""

    def __init__(self, runner: ReportRunner, report_hash: str) -> None:
        self._runner = runner
        self._hash = report_hash

    @property
    def hash(self) -> str:
        return self._hash

    def run(self) -> "ReportQuery[dict[str, Any]]":
        """Execute the saved report. Same ``ReportQuery`` contract as everything else.

        Note: the ``/runSavedReport`` response shape is assumed to match
        ``ReportResultMessageV2`` (plan.md §11.2 R-9) — treat as experimental until
        verified against a live tenant.
        """
        return ReportQuery(
            runner=self._runner,
            decode=lambda record: record,
            saved_hash=self._hash,
        )

    async def query(self) -> QueryMessageV2:
        """Retrieve the stored ``QueryMessageV2`` for this hash."""
        return await self._runner.get_saved_query(self._hash)


__all__ = ["SavedReportRef"]
