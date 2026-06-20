"""Shared test fixtures and helpers.

Tests run against the real SDK with a stubbed HTTP layer via
``httpx.MockTransport`` (the ``transport=`` constructor seam). Nothing here hits
a network. Helpers build JWTs, columnar response envelopes, and clients wired to
a recording handler.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx
import pytest

from dayshape import DayshapeClient

BASE_URL = "https://acme.dayshape.app"


# --------------------------------------------------------------------------- #
# JWT helpers
# --------------------------------------------------------------------------- #
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt(*, exp_in: int | None = 3600, include_exp: bool = True) -> str:
    """A syntactically valid (unsigned) JWT. ``include_exp=False`` omits ``exp``."""
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    claims: dict[str, Any] = {"sub": "api-user"}
    if include_exp and exp_in is not None:
        claims["exp"] = int(time.time()) + exp_in
    payload = _b64url(json.dumps(claims).encode())
    return f"{header}.{payload}.signature"


# --------------------------------------------------------------------------- #
# Columnar response envelope
# --------------------------------------------------------------------------- #
def make_envelope(
    dimensions: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    record_count: int | None = None,
    display_names: Sequence[str] | None = None,
    duration_ms: int | None = 10,
    report_display_name: str | None = "A Report",
    report_started: str | None = "2026-01-01T00:00:00.000Z",
) -> dict[str, Any]:
    """Build a ``ReportResultMessageV2`` envelope for the given dimensions/rows."""
    index = {dim: i for i, dim in enumerate(dimensions)}
    return {
        "recordCount": record_count if record_count is not None else len(rows),
        "reportDurationMs": duration_ms,
        "reportDisplayName": report_display_name,
        "reportStarted": report_started,
        "dimensions": index,
        "dimensionDisplayNames": list(display_names)
        if display_names is not None
        else [f"{d} (display)" for d in dimensions],
        "rows": [list(r) for r in rows],
    }


def envelope_from_request(
    request: httpx.Request,
    *,
    n_rows: int = 1,
    cell: Callable[[str, int], Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Echo the requested dimensions back as ``n_rows`` rows of generated cells.

    ``cell(dimension_id, row_index)`` supplies a value; the default returns a
    small valid value per common dimension type (ids → int, dates → ISO string).
    """
    body = json.loads(request.content)
    dims = [d["dimensionId"] for d in body.get("dimensions", [])]

    def default_cell(dim: str, row: int) -> Any:
        if dim.endswith(("Id", "Rank")) or dim in {"RateValue"}:
            return 100 + row
        if "Start" in dim or "End" in dim or "Date" in dim:
            return "2026-01-10T09:00:00.000Z"
        if dim.startswith(("Exchange",)) or dim.endswith(("Hours", "Duration")):
            return 1.5
        return f"{dim}-{row}"

    pick = cell or default_cell
    rows = [[pick(d, r) for d in dims] for r in range(n_rows)]
    return httpx.Response(
        200, json=make_envelope(dims, rows), headers=headers or {}
    )


# --------------------------------------------------------------------------- #
# Handlers and client construction
# --------------------------------------------------------------------------- #
class MockBackend:
    """A configurable ``httpx.MockTransport`` handler that records requests."""

    def __init__(
        self,
        *,
        v2: Callable[[httpx.Request], httpx.Response] | None = None,
        token: Callable[[httpx.Request], httpx.Response] | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.token_calls = 0
        self.v2_calls = 0
        self._v2 = v2
        self._token = token

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/reporting/token"):
            self.token_calls += 1
            if self._token is not None:
                return self._token(request)
            return httpx.Response(200, text=make_jwt())
        if path.endswith("/reporting/v2") or "/reporting/v2" in path:
            self.v2_calls += 1
            if self._v2 is not None:
                return self._v2(request)
            return envelope_from_request(request)
        if path.endswith("/status"):
            return httpx.Response(200, text="ok")
        return httpx.Response(404, text="unhandled")

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def build_client(
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
    **kwargs: Any,
) -> DayshapeClient:
    """A :class:`DayshapeClient` wired to ``handler`` (or a default backend)."""
    backend = handler if handler is not None else MockBackend()
    transport = (
        backend.transport
        if isinstance(backend, MockBackend)
        else httpx.MockTransport(backend)
    )
    kwargs.setdefault("base_url", BASE_URL)
    kwargs.setdefault("username", "user")
    kwargs.setdefault("password", "pass")
    return DayshapeClient(transport=transport, **kwargs)


@pytest.fixture
def backend() -> MockBackend:
    """A default recording backend that echoes requested dimensions."""
    return MockBackend()


@pytest.fixture
async def client(backend: MockBackend) -> Any:
    """An open :class:`DayshapeClient` bound to the default backend."""
    async with build_client(backend) as c:
        yield c
