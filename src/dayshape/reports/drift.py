"""Catalogue-vs-server drift report (issue #4).

The generated catalogue (``dims.py`` / ``_catalogue.py``) is pinned to a workbook
version, while ``server_versions()`` reflects whatever the live Reporting Service
runs. When the two diverge, dimensions the SDK requests by default can silently
vanish from results (issue #3). :meth:`~dayshape.client.DayshapeClient.validate_catalogue`
diffs the dimensions the SDK's typed façades request against each report's live
``/v2/metadata`` and returns the structures below.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReportDrift:
    """The drift status of one report against the live server."""

    report_id: str
    #: Whether ``/v2/metadata`` returned successfully for this report. ``False``
    #: when the metadata fetch failed (e.g. a ``403`` permission denial), in which
    #: case :pyattr:`error` carries the reason and no dimension diff is possible.
    available: bool
    #: The failure reason when :pyattr:`available` is ``False``, else ``None``.
    error: str | None
    #: Dimensions the SDK requests by default for this report that the live server
    #: does **not** expose — every value for these would silently be ``None``.
    missing_dimensions: frozenset[str]
    #: The dimensions that were checked (the SDK's default set for the report).
    checked_dimensions: frozenset[str]

    @property
    def ok(self) -> bool:
        """True when the report is reachable and no expected dimension is missing."""
        return self.available and not self.missing_dimensions


@dataclass(frozen=True, slots=True)
class CatalogueReport:
    """The result of :meth:`~dayshape.client.DayshapeClient.validate_catalogue`."""

    #: The live server's API-version discovery headers (see ``server_versions``).
    server_versions: dict[str, str | None]
    #: The spec artefacts this SDK build was generated against (``SPEC_VERSION``).
    spec_version: dict[str, str]
    #: Per-report drift status, one entry per report checked.
    reports: tuple[ReportDrift, ...]

    @property
    def ok(self) -> bool:
        """True when no checked report is missing an expected dimension."""
        return all(not r.missing_dimensions for r in self.reports)

    @property
    def drifted(self) -> tuple[ReportDrift, ...]:
        """Reports with at least one expected dimension missing on the server."""
        return tuple(r for r in self.reports if r.missing_dimensions)

    @property
    def unavailable(self) -> tuple[ReportDrift, ...]:
        """Reports whose ``/v2/metadata`` could not be fetched (e.g. permissions)."""
        return tuple(r for r in self.reports if not r.available)

    def summary(self) -> str:
        """A short human-readable digest, suitable for logging."""
        lines = [
            f"Catalogue check (spec workbook {self.spec_version.get('workbook')!r}, "
            f"server supported versions {self.server_versions.get('supported')!r}):",
            f"  {len(self.reports)} report(s) checked, "
            f"{len(self.drifted)} drifted, {len(self.unavailable)} unavailable.",
        ]
        for r in self.drifted:
            lines.append(
                f"  DRIFT {r.report_id}: missing {sorted(r.missing_dimensions)}"
            )
        for r in self.unavailable:
            lines.append(f"  UNAVAILABLE {r.report_id}: {r.error}")
        return "\n".join(lines)


__all__ = ["ReportDrift", "CatalogueReport"]
