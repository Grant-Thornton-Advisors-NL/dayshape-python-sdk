"""Logging helpers with credential redaction (plan.md §2, §1).

Nothing secret is ever logged. The :class:`RedactionFilter` is attached to the
SDK logger so that even an accidental interpolation of a password or bearer token
is scrubbed before it reaches a handler.
"""

from __future__ import annotations

import logging
import re

_LOGGER_NAME = "dayshape"

# Patterns that, if they ever appear in a log record, must be masked.
_REDACTIONS: tuple[re.Pattern[str], ...] = (
    # Authorization: Bearer <jwt>
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    # password=... or "password": "..."
    re.compile(r"(?i)(password\"?\s*[:=]\s*\"?)[^\s,\"}]+"),
)

_MASK = r"\1***"


class RedactionFilter(logging.Filter):
    """Scrub secrets from a log record's rendered message and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive; never block logging
            return True
        redacted = message
        for pattern in _REDACTIONS:
            redacted = pattern.sub(_MASK, redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the ``dayshape`` logger with redaction attached."""
    base = logging.getLogger(_LOGGER_NAME)
    if not any(isinstance(f, RedactionFilter) for f in base.filters):
        base.addFilter(RedactionFilter())
    if name:
        return base.getChild(name)
    return base


def configure(level: int | str | None) -> None:
    """Set the SDK logger level. ``None`` leaves the level untouched."""
    if level is not None:
        get_logger().setLevel(level)


__all__ = ["get_logger", "configure", "RedactionFilter"]
