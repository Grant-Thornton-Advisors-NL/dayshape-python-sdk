"""The report registry: ``ReportId`` enum + per-report metadata (plan.md §0.4).

Data is sourced from the generated :mod:`dayshape.reports._catalogue` (workbook +
API doc). Lookups are case-insensitive (plan.md §0.3) since the vendor treats
identifiers case-insensitively on the wire.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ._catalogue import CATALOGUE


class ReportType(StrEnum):
    LISTING = "Listing"
    PIVOT = "Pivot"


# ``ReportId`` is a StrEnum whose members are the wire report ids. Built
# dynamically from the catalogue so it never drifts from the workbook.
ReportId = StrEnum(  # type: ignore[misc]
    "ReportId",
    {report_id: report_id for report_id in CATALOGUE},
)
ReportId.__doc__ = "Wire report identifiers for the 42 Reporting Service reports."


@dataclass(frozen=True, slots=True)
class ReportMeta:
    """Static metadata about a report."""

    report_id: str
    display_name: str
    type: ReportType
    permissions: str
    rate_limited: bool

    @property
    def is_pivot(self) -> bool:
        return self.type is ReportType.PIVOT

    @property
    def is_listing(self) -> bool:
        return self.type is ReportType.LISTING


_META: dict[str, ReportMeta] = {
    rid: ReportMeta(
        report_id=rid,
        display_name=name,
        type=ReportType(rtype),
        permissions=perms,
        rate_limited=rate_limited,
    )
    for rid, (name, rtype, perms, rate_limited) in CATALOGUE.items()
}

# Case-insensitive index.
_BY_LOWER: dict[str, ReportMeta] = {rid.lower(): meta for rid, meta in _META.items()}


def resolve_report_id(report_id: str) -> str:
    """Return the canonical wire report id for ``report_id`` (case-insensitive).

    Unknown ids are returned unchanged — tenant/custom reports and forward
    compatibility are not blocked by the registry; downstream validation (or the
    server) decides. Callers that want strictness can check :func:`get_meta`.
    """
    meta = _BY_LOWER.get(report_id.lower())
    return meta.report_id if meta else report_id


def get_meta(report_id: str) -> ReportMeta | None:
    """Return the :class:`ReportMeta` for ``report_id`` (case-insensitive), or None."""
    return _BY_LOWER.get(report_id.lower())


def is_rate_limited(report_id: str) -> bool:
    """Whether ``report_id`` is one of the 17 per-user single-concurrency reports."""
    meta = _BY_LOWER.get(report_id.lower())
    return bool(meta and meta.rate_limited)


__all__ = [
    "ReportId",
    "ReportType",
    "ReportMeta",
    "resolve_report_id",
    "get_meta",
    "is_rate_limited",
]
