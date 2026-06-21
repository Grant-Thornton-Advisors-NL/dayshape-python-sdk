"""Exception hierarchy for the Dayshape SDK (plan.md §8).

```
DayshapeError
├── DayshapeConnectionError / DayshapeTimeoutError
├── AuthenticationError
├── APIStatusError
│   ├── BadRequestError
│   ├── PermissionDeniedError
│   ├── RateLimitError
│   │   └── ConcurrentReportLimitError
│   ├── NotFoundError
│   └── ServerError
├── ResponseError
│   ├── ResponseFormatError
│   └── ResponseValidationError
├── QueryError
├── ChunkingError
├── ResultTooLargeError
├── DetachedModelError
└── ClientClosedError
```
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx


class DayshapeError(Exception):
    """Base class for every error raised by the SDK."""


# --------------------------------------------------------------------------- #
# Transport-level
# --------------------------------------------------------------------------- #
class DayshapeConnectionError(DayshapeError):
    """A network-level failure occurred before a response was received."""


class DayshapeTimeoutError(DayshapeConnectionError):
    """A request exceeded the configured timeout.

    The Dayshape server enforces a documented 15-minute ceiling per request; the
    SDK's read timeout defaults just above that so the server's diagnosable error
    wins over an opaque local ``ReadTimeout``. If you see this, the request very
    likely breached the server ceiling.
    """


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
class AuthenticationError(DayshapeError):
    """Authentication failed.

    Raised for a ``403`` from ``/token`` (invalid credentials *or* the user is not
    configured as an API user), and for any ``401`` that persists after a single
    refresh-and-replay.
    """


# --------------------------------------------------------------------------- #
# API status errors (non-2xx responses with a meaningful HTTP status)
# --------------------------------------------------------------------------- #
class APIStatusError(DayshapeError):
    """Base class for errors derived from an HTTP status code."""

    #: HTTP status code associated with this error class (``None`` on the base).
    status_code: int | None = None

    def __init__(
        self,
        message: str,
        *,
        response: httpx.Response | None = None,
        request: httpx.Request | None = None,
    ) -> None:
        super().__init__(message)
        self.response = response
        self.request = request
        if response is not None:
            self.status_code = response.status_code


class BadRequestError(APIStatusError):
    """``400`` — the request payload was invalid.

    Unknown identifiers, a missing ``subType``, or a ``MaxTimeHorizon`` breach.
    The metadata-validated pre-flight catches most of these as :class:`QueryError`
    before any request is sent.
    """

    status_code = 400


class PermissionDeniedError(APIStatusError):
    """``403`` from ``/v2`` — the user may not run the requested query.

    Distinct from :class:`AuthenticationError`: the credentials are valid but the
    API user lacks the required ``Reporting_*_Read`` permissions for this report.
    """

    status_code = 403


class RateLimitError(APIStatusError):
    """A volumetric limit was hit. Parent of :class:`ConcurrentReportLimitError`.

    Retained as a parent class so ``except RateLimitError`` survives any future
    volumetric limits beyond the current per-user concurrency rule.
    """

    status_code = 429


class ConcurrentReportLimitError(RateLimitError):
    """``429`` — too many of the rate-limited reports running concurrently.

    Raised only after the transport's retry budget for ``429`` is exhausted.
    """


class NotFoundError(APIStatusError):
    """``404`` — wrong ``base_url`` or a sunsetted API version.

    Includes ``Api-Supported-Versions`` content when the server provides it.
    """

    status_code = 404


class ServerError(APIStatusError):
    """``5xx`` after the retry budget is exhausted.

    For ``/v2/export`` a ``500`` may also mean the result exceeds the maximum
    spreadsheet size; that ambiguity is quoted verbatim in the message.
    """

    status_code = 500


# --------------------------------------------------------------------------- #
# Response decoding
# --------------------------------------------------------------------------- #
class ResponseError(DayshapeError):
    """Base class for failures decoding an otherwise-successful response."""


class ResponseFormatError(ResponseError):
    """The response body did not match the expected envelope shape."""


class ResponseValidationError(ResponseError):
    """A result row failed model validation under ``strict_models=True``.

    Carries the offending row and the report id for diagnosis.
    """

    def __init__(
        self, message: str, *, report_id: str | None = None, row: Any | None = None
    ) -> None:
        super().__init__(message)
        self.report_id = report_id
        self.row = row


# --------------------------------------------------------------------------- #
# Pre-flight / usage errors (raised before any I/O where possible)
# --------------------------------------------------------------------------- #
class QueryError(DayshapeError):
    """A query is invalid before it is sent.

    No resolvable :class:`~dayshape.period.Period`; a missing ``subType``; an
    unknown identifier (in metadata-validated mode); or ``chunk`` combined with a
    sorted dimension without ``allow_unordered=True``.
    """


class UnknownDimensionError(QueryError):
    """One or more requested dimensions were not returned by the server.

    The Reporting Service silently drops a dimension it does not recognise from
    the columnar result, so *every* value for that dimension decodes to ``None`` —
    indistinguishable from a genuine null. This is raised (under
    ``validate_dimensions="error"``) or warned (under ``"warn"``, the default)
    when the response omits a requested dimension, naming the offending ids so a
    catalogue-vs-server drift surfaces immediately instead of as silent data loss.

    Subclasses :class:`QueryError`, so ``except QueryError`` still catches it.
    """

    def __init__(
        self,
        message: str,
        *,
        report_id: str | None = None,
        dimensions: "tuple[str, ...] | list[str] | None" = None,
    ) -> None:
        super().__init__(message)
        self.report_id = report_id
        self.dimensions: tuple[str, ...] = tuple(dimensions or ())


class ChunkingError(DayshapeError):
    """An invalid chunk window specification."""


class ResultTooLargeError(DayshapeError):
    """A materialisation would exceed a caller-imposed ``max_rows`` bound."""


class DetachedModelError(DayshapeError):
    """A relational hop was attempted on a model with no live client binding.

    Re-fetch the entity through a live client, or pass an explicit client.
    """


class ClientClosedError(DayshapeError):
    """An operation was attempted on a closed :class:`~dayshape.client.DayshapeClient`."""


__all__ = [
    "DayshapeError",
    "DayshapeConnectionError",
    "DayshapeTimeoutError",
    "AuthenticationError",
    "APIStatusError",
    "BadRequestError",
    "PermissionDeniedError",
    "RateLimitError",
    "ConcurrentReportLimitError",
    "NotFoundError",
    "ServerError",
    "ResponseError",
    "ResponseFormatError",
    "ResponseValidationError",
    "QueryError",
    "UnknownDimensionError",
    "ChunkingError",
    "ResultTooLargeError",
    "DetachedModelError",
    "ClientClosedError",
]
