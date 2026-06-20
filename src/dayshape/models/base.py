"""Base model + type machinery for result rows (plan.md §4.1–§4.4).

Listing rows are *projections*: a row contains only the requested dimensions, so
every dimension-backed field is ``Optional`` defaulting to ``None``. The
``requested_dimensions`` frozenset distinguishes "not requested" from "null in
source". Undeclared dimensions (tenant custom members, comparative columns) flow
into ``model_extra`` and are surfaced via :pyattr:`custom_fields`.
"""

from __future__ import annotations

import warnings
import weakref
from collections.abc import Iterator
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Annotated, Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PrivateAttr

from ..exceptions import DetachedModelError

if TYPE_CHECKING:
    from ..client import DayshapeClient
    from ..period import Period
    from ..reports.query import Dimension


# --------------------------------------------------------------------------- #
# Tolerant cell parsers (mode="before")
# --------------------------------------------------------------------------- #
def parse_datetime(value: Any) -> Any:
    """Parse a datetime cell tolerantly (plan.md §4.3).

    Accepts ``datetime`` as-is and ISO-8601 strings including the trailing ``Z``
    and 7-fractional-digit forms the API emits. Anything else is passed through
    for Pydantic to handle or reject.
    """
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return _parse_iso(value)
    return value


def parse_date(value: Any) -> Any:
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        parsed = _parse_iso(value)
        return parsed.date() if isinstance(parsed, datetime) else parsed
    return value


def _parse_iso(text: str) -> Any:
    raw = text.strip()
    if not raw:
        return None
    candidate = raw
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    # Truncate over-long fractional seconds (e.g. 7 digits) to 6 for fromisoformat.
    if "." in candidate:
        head, _, tail = candidate.partition(".")
        digits = ""
        rest = ""
        for i, ch in enumerate(tail):
            if ch.isdigit():
                digits += ch
            else:
                rest = tail[i:]
                break
        candidate = f"{head}.{digits[:6]}{rest}"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return text  # leave the original for the field type to reject if needed


def parse_guid(value: Any) -> Any:
    """Lenient ``UUID``-or-``str`` (the spec's own samples include ``"M1"``)."""
    if value is None or isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return value
    return value


class Percentage(float):
    """A percentage as a decimal fraction in ``[0, 1]`` under ``formatNumbers=false``.

    ``0.9`` means 90%. This is a documented consequence of the SDK's deterministic
    formatting defaults (plan.md §4.3, §4.6).
    """

    __slots__ = ()


def _parse_percentage(value: Any) -> Any:
    if value is None or isinstance(value, Percentage):
        return value
    if isinstance(value, (int, float)):
        return Percentage(value)
    if isinstance(value, str) and value.strip():
        try:
            return Percentage(float(value))
        except ValueError:
            return value
    return value


# Annotated aliases used by entity models.
DateTimeValue = Annotated[datetime, BeforeValidator(parse_datetime)]
DateValue = Annotated[date, BeforeValidator(parse_date)]
GuidValue = Annotated[UUID | str, BeforeValidator(parse_guid)]
PercentageValue = Annotated[Percentage, BeforeValidator(_parse_percentage)]


# --------------------------------------------------------------------------- #
# Base model
# --------------------------------------------------------------------------- #
class DayshapeModel(BaseModel):
    """Base for every result-row entity model."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        arbitrary_types_allowed=True,
    )

    #: The default dimensions a resource requests when the caller specifies none
    #: (identity + navigation core). Overridden per entity.
    default_dimensions: ClassVar[tuple[str, ...]] = ()

    #: Which dimension ids were requested for this row (set by the decoder).
    requested_dimensions: frozenset[str] = Field(
        default_factory=frozenset, exclude=True, repr=False
    )

    _client: "weakref.ref[DayshapeClient] | None" = PrivateAttr(default=None)
    _period: "Period | None" = PrivateAttr(default=None)

    # -- custom / extra fields --------------------------------------------- #
    @property
    def custom_fields(self) -> dict[str, Any]:
        """Undeclared dimensions: tenant custom members and comparative columns."""
        return dict(self.model_extra or {})

    def field(self, dimension_id: str) -> Any:
        """Read any dimension by its wire id, whether declared or extra."""
        for name, info in type(self).model_fields.items():
            if info.alias == dimension_id or name == dimension_id:
                return getattr(self, name)
        return (self.model_extra or {}).get(dimension_id)

    def was_requested(self, dimension_id: str) -> bool:
        return dimension_id in self.requested_dimensions

    # -- client binding (weak) for relational hops ------------------------- #
    def _bind(self, client: "DayshapeClient", period: "Period | None") -> None:
        self._client = weakref.ref(client)
        self._period = period

    def _bound_client(self) -> "DayshapeClient":
        ref = self._client
        live = ref() if ref is not None else None
        if live is None:
            raise DetachedModelError(
                f"{type(self).__name__} has no live client binding; re-fetch it "
                "through a DayshapeClient resource before navigating relations."
            )
        return live

    def _inherited_period(self) -> "Period | None":
        """The period of the query that produced this row (for relational hops)."""
        return self._period

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _split(value: str | None) -> list[str]:
        """Split a comma-separated dimension string. ``None`` → ``[]`` (legacy note)."""
        if not value:
            return []
        return [part.strip() for part in value.split(",") if part.strip()]


def warn_unknown_enum(field_name: str, value: Any, known: frozenset[str]) -> None:
    """Warn (not raise) on a novel categorical value, e.g. ``LogOperation`` (§4.4)."""
    if value is not None and value not in known:
        warnings.warn(
            f"Unknown {field_name} value {value!r}; treating as opaque. "
            "The SDK may need updating for a new server enum.",
            stacklevel=2,
        )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "DayshapeModel",
    "Percentage",
    "DateTimeValue",
    "DateValue",
    "GuidValue",
    "PercentageValue",
    "parse_datetime",
    "parse_date",
    "parse_guid",
    "warn_unknown_enum",
]
