"""Tests for ``dayshape._transport.Transport`` — retries, error mapping, and
the JSON/bytes request helpers (plan.md §3, §8).

These drive the transport two ways:

* directly, by instantiating :class:`~dayshape._transport.Transport` with an
  ``httpx.MockTransport`` for fine control over status codes, headers, and raised
  exceptions; and
* end-to-end, through ``build_client(...).reports.run(...)`` / ``.status()`` so the
  runner/transport seam is exercised the way callers see it.

Nothing here hits a network. ``asyncio.sleep`` is monkeypatched out on the backoff
paths so retries don't wait on the wall clock.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import httpx
import pytest

from dayshape import RetryConfig
from dayshape._transport import Transport
from dayshape.config import DayshapeConfig, TimeoutConfig
from dayshape.exceptions import (
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    ClientClosedError,
    ConcurrentReportLimitError,
    DayshapeConnectionError,
    DayshapeError,
    DayshapeTimeoutError,
    NotFoundError,
    PermissionDeniedError,
    ResponseFormatError,
    ServerError,
)

from conftest import BASE_URL, MockBackend, build_client, make_jwt

# --------------------------------------------------------------------------- #
# Low-level helpers: build a Transport wired to a sequence-of-responses handler.
# --------------------------------------------------------------------------- #
V2_URL = f"{BASE_URL}/reporting/v2"
TOKEN_URL = f"{BASE_URL}/reporting/token"


def make_config(**kwargs) -> DayshapeConfig:
    """A resolved config with sensible defaults; override anything via kwargs."""
    kwargs.setdefault("base_url", BASE_URL)
    kwargs.setdefault("username", "user")
    kwargs.setdefault("password", "pass")
    return DayshapeConfig.resolve(**kwargs)


def sequence_handler(*v2_responses, token=None):
    """An httpx handler: ``/token`` returns a JWT; ``/v2`` walks ``v2_responses``.

    Each element of ``v2_responses`` may be an ``httpx.Response`` or a callable
    ``(request) -> httpx.Response`` (so it can raise a transport exception).
    """
    state = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            if token is not None:
                return token(request)
            return httpx.Response(200, text=make_jwt())
        # /v2 (or any other) → next scripted response
        item = v2_responses[min(state["i"], len(v2_responses) - 1)]
        state["i"] += 1
        if callable(item):
            return item(request)
        return item

    handler.state = state  # type: ignore[attr-defined]
    return handler


def make_transport(handler, *, retries=None, **cfg_kwargs) -> Transport:
    config = make_config(
        retries=retries if retries is not None else RetryConfig(),
        **cfg_kwargs,
    )
    return Transport(config, httpx_transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make all backoff/rate-limit sleeps instantaneous (keeps retries fast)."""

    async def _instant(_delay: float) -> None:
        return None

    monkeypatch.setattr("dayshape._transport.asyncio.sleep", _instant)


def envelope_response(headers=None) -> httpx.Response:
    """A minimal valid JSON envelope body (the transport doesn't parse it)."""
    return httpx.Response(200, json={"rows": [], "dimensions": {}}, headers=headers or {})


# --------------------------------------------------------------------------- #
# Successful request_json / request_bytes
# --------------------------------------------------------------------------- #
async def test_request_json_success_returns_body_and_headers() -> None:
    handler = sequence_handler(
        httpx.Response(200, json={"hello": "world"}, headers={"X-Trace": "abc"})
    )
    async with make_transport(handler) as t:
        data, headers = await t.request_json("POST", V2_URL, json={"q": 1})
    assert data == {"hello": "world"}
    assert headers["X-Trace"] == "abc"


async def test_request_json_sends_bearer_token() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, text=make_jwt())
        seen.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"ok": True})

    async with make_transport(handler) as t:
        await t.request_json("GET", V2_URL)
    assert len(seen) == 1 and seen[0].startswith("Bearer ")


async def test_request_bytes_success_returns_content() -> None:
    handler = sequence_handler(httpx.Response(200, content=b"\x50\x4b\x03\x04"))
    async with make_transport(handler) as t:
        content, headers = await t.request_bytes("GET", f"{BASE_URL}/reporting/status")
    assert content == b"\x50\x4b\x03\x04"


# --------------------------------------------------------------------------- #
# Transient retry on 502/503/504 then success
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", [502, 503, 504])
async def test_retry_on_transient_status_then_success(status: int) -> None:
    handler = sequence_handler(
        httpx.Response(status),
        httpx.Response(200, json={"recovered": True}),
    )
    retries = RetryConfig(max_attempts=3, backoff_base=0.0)
    async with make_transport(handler, retries=retries) as t:
        data, _ = await t.request_json("POST", V2_URL, json={})
    assert data == {"recovered": True}
    assert handler.state["i"] == 2  # one failure + one success


async def test_retry_exhausted_on_503_raises_server_error() -> None:
    handler = sequence_handler(httpx.Response(503), httpx.Response(503))
    retries = RetryConfig(max_attempts=2, backoff_base=0.0)
    async with make_transport(handler, retries=retries) as t:
        with pytest.raises(ServerError) as exc:
            await t.request_json("POST", V2_URL, json={})
    assert exc.value.status_code == 503
    assert handler.state["i"] == 2


async def test_no_retry_when_retries_disabled() -> None:
    handler = sequence_handler(httpx.Response(503), httpx.Response(200, json={}))
    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(ServerError):
            await t.request_json("POST", V2_URL, json={})
    assert handler.state["i"] == 1  # exactly one attempt, no replay


# --------------------------------------------------------------------------- #
# 429 retry: numeric Retry-After AND backoff path; then exhaustion.
# --------------------------------------------------------------------------- #
async def test_429_numeric_retry_after_then_success() -> None:
    handler = sequence_handler(
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(200, json={"ok": 1}),
    )
    retries = RetryConfig(max_attempts=3)
    async with make_transport(handler, retries=retries) as t:
        data, _ = await t.request_json("POST", V2_URL, json={})
    assert data == {"ok": 1}
    assert handler.state["i"] == 2


async def test_429_backoff_path_without_retry_after_then_success() -> None:
    # No Retry-After header → exponential rate-limit backoff branch.
    handler = sequence_handler(
        httpx.Response(429),
        httpx.Response(200, json={"ok": 2}),
    )
    retries = RetryConfig(max_attempts=3)
    async with make_transport(handler, retries=retries) as t:
        data, _ = await t.request_json("POST", V2_URL, json={})
    assert data == {"ok": 2}


async def test_429_non_numeric_retry_after_uses_backoff() -> None:
    # A non-digit Retry-After ("Wed, 21 Oct ...") falls through to the backoff branch.
    handler = sequence_handler(
        httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        httpx.Response(200, json={"ok": 3}),
    )
    retries = RetryConfig(max_attempts=3)
    async with make_transport(handler, retries=retries) as t:
        data, _ = await t.request_json("POST", V2_URL, json={})
    assert data == {"ok": 3}


async def test_429_budget_exhausted_raises_concurrent_report_limit() -> None:
    handler = sequence_handler(
        httpx.Response(429),
        httpx.Response(429),
        httpx.Response(429),
    )
    retries = RetryConfig(max_attempts=3)
    async with make_transport(handler, retries=retries) as t:
        with pytest.raises(ConcurrentReportLimitError) as exc:
            await t.request_json("POST", V2_URL, json={})
    assert isinstance(exc.value, DayshapeError)
    assert exc.value.status_code == 429
    assert handler.state["i"] == 3  # all attempts consumed


# --------------------------------------------------------------------------- #
# Transport-level exceptions: connect error and read timeout.
# --------------------------------------------------------------------------- #
async def test_connect_error_maps_to_connection_error() -> None:
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    handler = sequence_handler(boom)
    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(DayshapeConnectionError) as exc:
            await t.request_json("POST", V2_URL, json={})
    # The original transport error is chained.
    assert isinstance(exc.value.__cause__, httpx.ConnectError)


async def test_read_timeout_maps_to_timeout_error() -> None:
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out")

    handler = sequence_handler(boom)
    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(DayshapeTimeoutError) as exc:
            await t.request_json("POST", V2_URL, json={})
    # DayshapeTimeoutError is a subclass of DayshapeConnectionError.
    assert isinstance(exc.value, DayshapeConnectionError)
    assert isinstance(exc.value.__cause__, httpx.ReadTimeout)


async def test_connect_error_retried_then_success() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, text=make_jwt())
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("transient")
        return httpx.Response(200, json={"ok": True})

    retries = RetryConfig(max_attempts=3, backoff_base=0.0)
    async with make_transport(handler, retries=retries) as t:
        data, _ = await t.request_json("POST", V2_URL, json={})
    assert data == {"ok": True}
    assert calls["n"] == 2


async def test_timeout_retried_then_exhausts() -> None:
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    handler = sequence_handler(boom, boom)
    retries = RetryConfig(max_attempts=2, backoff_base=0.0)
    async with make_transport(handler, retries=retries) as t:
        with pytest.raises(DayshapeTimeoutError):
            await t.request_json("POST", V2_URL, json={})
    assert handler.state["i"] == 2  # retried once before raising


# --------------------------------------------------------------------------- #
# Status-code → exception mapping (single attempt, non-retryable).
# --------------------------------------------------------------------------- #
async def test_400_maps_to_bad_request() -> None:
    handler = sequence_handler(httpx.Response(400, text="bad query"))
    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(BadRequestError) as exc:
            await t.request_json("POST", V2_URL, json={})
    assert exc.value.status_code == 400
    assert "bad query" in str(exc.value)
    assert exc.value.response is not None


async def test_403_maps_to_permission_denied() -> None:
    handler = sequence_handler(httpx.Response(403, text="nope"))
    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(PermissionDeniedError) as exc:
            await t.request_json("POST", V2_URL, json={})
    assert exc.value.status_code == 403


async def test_404_maps_to_not_found_with_supported_versions() -> None:
    handler = sequence_handler(
        httpx.Response(404, headers={"Api-Supported-Versions": "v1, v2"})
    )
    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(NotFoundError) as exc:
            await t.request_json("POST", V2_URL, json={})
    assert exc.value.status_code == 404
    assert "Supported versions: v1, v2" in str(exc.value)


async def test_404_without_supported_versions_header() -> None:
    handler = sequence_handler(httpx.Response(404))
    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(NotFoundError) as exc:
            await t.request_json("POST", V2_URL, json={})
    assert "Supported versions" not in str(exc.value)


async def test_500_maps_to_server_error() -> None:
    handler = sequence_handler(httpx.Response(500, text="kaboom"))
    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(ServerError) as exc:
            await t.request_json("POST", V2_URL, json={})
    assert exc.value.status_code == 500
    assert "kaboom" in str(exc.value)


async def test_unexpected_4xx_maps_to_api_status_error() -> None:
    # 418 isn't specifically mapped → base APIStatusError.
    handler = sequence_handler(httpx.Response(418, text="teapot"))
    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(APIStatusError) as exc:
            await t.request_json("POST", V2_URL, json={})
    assert type(exc.value) is APIStatusError
    assert exc.value.status_code == 418
    assert "Unexpected status 418" in str(exc.value)


# --------------------------------------------------------------------------- #
# Persistent 401 → AuthenticationError (BearerAuth refreshes once, then gives up).
# --------------------------------------------------------------------------- #
async def test_persistent_401_raises_authentication_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, text=make_jwt())
        return httpx.Response(401, text="unauthorized")

    async with make_transport(handler, retries=RetryConfig.disabled()) as t:
        with pytest.raises(AuthenticationError):
            await t.request_json("POST", V2_URL, json={})


# --------------------------------------------------------------------------- #
# ResponseFormatError when /v2 returns non-JSON with a 2xx status.
# --------------------------------------------------------------------------- #
async def test_non_json_2xx_body_raises_response_format_error() -> None:
    handler = sequence_handler(
        httpx.Response(200, text="<html>not json</html>")
    )
    async with make_transport(handler) as t:
        with pytest.raises(ResponseFormatError) as exc:
            await t.request_json("GET", V2_URL)
    assert V2_URL in str(exc.value)


# --------------------------------------------------------------------------- #
# login(): 403 from /token → AuthenticationError; other 4xx → mapped error.
# --------------------------------------------------------------------------- #
async def test_login_403_raises_authentication_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(403, text="invalid creds")
        return httpx.Response(200, json={})

    async with make_transport(handler) as t:
        with pytest.raises(AuthenticationError) as exc:
            await t.login()
    assert "Authentication failed (403)" in str(exc.value)


async def test_login_other_error_uses_error_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(500, text="token service down")
        return httpx.Response(200, json={})

    async with make_transport(handler) as t:
        with pytest.raises(ServerError):
            await t.login()


async def test_login_success_acquires_token() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            calls["n"] += 1
            return httpx.Response(200, text=make_jwt())
        return httpx.Response(200, json={})

    async with make_transport(handler) as t:
        await t.login()
    assert calls["n"] == 1


# --------------------------------------------------------------------------- #
# ClientClosedError after aclose().
# --------------------------------------------------------------------------- #
async def test_request_after_close_raises_client_closed() -> None:
    handler = sequence_handler(httpx.Response(200, json={}))
    t = make_transport(handler)
    await t.aclose()
    with pytest.raises(ClientClosedError):
        await t.request_json("POST", V2_URL, json={})


async def test_login_after_close_raises_client_closed() -> None:
    handler = sequence_handler(httpx.Response(200, json={}))
    t = make_transport(handler)
    await t.aclose()
    with pytest.raises(ClientClosedError):
        await t.login()


async def test_aclose_is_idempotent() -> None:
    handler = sequence_handler(httpx.Response(200, json={}))
    t = make_transport(handler)
    await t.aclose()
    await t.aclose()  # second close is a no-op, must not raise
    assert t._closed is True


# --------------------------------------------------------------------------- #
# Version deprecation warning: logged once via Api-Deprecated-Versions / Sunset.
# --------------------------------------------------------------------------- #
async def test_deprecated_version_logs_warning_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = sequence_handler(
        httpx.Response(200, json={"a": 1}, headers={"Api-Deprecated-Versions": "v2"}),
        httpx.Response(200, json={"b": 2}, headers={"Api-Deprecated-Versions": "v2"}),
    )
    async with make_transport(handler) as t:
        with caplog.at_level(logging.WARNING, logger="dayshape.transport"):
            await t.request_json("GET", V2_URL)
            await t.request_json("GET", V2_URL)
    warnings = [r for r in caplog.records if "deprecated" in r.getMessage().lower()]
    assert len(warnings) == 1  # warned exactly once despite two deprecated responses
    assert t._version_warned is True


async def test_sunset_header_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    handler = sequence_handler(
        httpx.Response(
            200, json={"a": 1}, headers={"Sunset": "Wed, 31 Dec 2026 23:59:59 GMT"}
        )
    )
    async with make_transport(handler) as t:
        with caplog.at_level(logging.WARNING, logger="dayshape.transport"):
            await t.request_json("GET", V2_URL)
    warnings = [r for r in caplog.records if "deprecated or scheduled" in r.getMessage()]
    assert len(warnings) == 1
    assert "Wed, 31 Dec 2026" in warnings[0].getMessage()


async def test_deprecated_version_not_in_use_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Server deprecates v1 but we're on v2 → no warning, no Sunset.
    handler = sequence_handler(
        httpx.Response(200, json={"a": 1}, headers={"Api-Deprecated-Versions": "v1"})
    )
    async with make_transport(handler) as t:
        with caplog.at_level(logging.WARNING, logger="dayshape.transport"):
            await t.request_json("GET", V2_URL)
    assert t._version_warned is False
    assert not [r for r in caplog.records if "deprecated" in r.getMessage().lower()]


async def test_no_version_headers_no_warning() -> None:
    handler = sequence_handler(httpx.Response(200, json={"a": 1}))
    async with make_transport(handler) as t:
        await t.request_json("GET", V2_URL)
    assert t._version_warned is False


# --------------------------------------------------------------------------- #
# server_versions() reflection helper.
# --------------------------------------------------------------------------- #
async def test_server_versions_extracts_headers() -> None:
    handler = sequence_handler(
        httpx.Response(
            200,
            json={"a": 1},
            headers={
                "Api-Supported-Versions": "v1, v2",
                "Api-Deprecated-Versions": "v1",
                "Sunset": "soon",
            },
        )
    )
    async with make_transport(handler) as t:
        _, headers = await t.request_json("GET", V2_URL)
        versions = t.server_versions(headers)
    assert versions == {"supported": "v1, v2", "deprecated": "v1", "sunset": "soon"}


# --------------------------------------------------------------------------- #
# End-to-end through the client/runner seam.
# --------------------------------------------------------------------------- #
async def test_client_reports_status_success() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        ok = await client.reports.status()
    assert ok is True
    assert backend.token_calls == 1


async def test_client_run_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dayshape.period import Period

    async def _instant(_delay: float) -> None:
        return None

    monkeypatch.setattr("dayshape._transport.asyncio.sleep", _instant)

    state = {"i": 0}
    sequence = [httpx.Response(503), None]  # second → default echo envelope

    def v2(request: httpx.Request) -> httpx.Response:
        from conftest import envelope_from_request

        item = sequence[min(state["i"], len(sequence) - 1)]
        state["i"] += 1
        if item is None:
            return envelope_from_request(request)
        return item

    backend = MockBackend(v2=v2)
    retries = RetryConfig(max_attempts=3, backoff_base=0.0)
    async with build_client(backend, retries=retries) as client:
        with client.period(Period.year(2026)) as scoped:
            rows = await scoped.reports.run("TaskListing", dimensions=["TaskId"])
    assert isinstance(rows, list)
    assert backend.v2_calls == 2  # one 503 + one success


async def test_client_run_429_exhausted_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dayshape.period import Period

    async def _instant(_delay: float) -> None:
        return None

    monkeypatch.setattr("dayshape._transport.asyncio.sleep", _instant)

    def v2(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    backend = MockBackend(v2=v2)
    retries = RetryConfig(max_attempts=2)
    async with build_client(backend, retries=retries) as client:
        with client.period(Period.year(2026)) as scoped:
            with pytest.raises(ConcurrentReportLimitError):
                await scoped.reports.run("TaskListing", dimensions=["TaskId"])
    assert backend.v2_calls == 2


async def test_client_run_after_close_raises_client_closed() -> None:
    from dayshape.period import Period

    backend = MockBackend()
    client = build_client(backend)
    await client.aclose()
    with client.period(Period.year(2026)) as scoped:
        with pytest.raises(ClientClosedError):
            await scoped.reports.run("TaskListing", dimensions=["TaskId"])


# --------------------------------------------------------------------------- #
# Backoff timing sanity: with a real (tiny) base the exponential delay is bounded.
# --------------------------------------------------------------------------- #
async def test_backoff_delay_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []

    async def _record(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr("dayshape._transport.asyncio.sleep", _record)

    handler = sequence_handler(
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json={"ok": True}),
    )
    retries = RetryConfig(
        max_attempts=3, backoff_base=1.0, backoff_cap=1.5, jitter=0.0
    )
    async with make_transport(handler, retries=retries) as t:
        await t.request_json("POST", V2_URL, json={})
    # attempt 1 → base*2^0 = 1.0 ; attempt 2 → base*2^1 = 2.0 capped to 1.5.
    assert slept == pytest.approx([1.0, 1.5])


async def test_rate_limit_wait_uses_numeric_retry_after_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def _record(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr("dayshape._transport.asyncio.sleep", _record)

    handler = sequence_handler(
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, json={"ok": True}),
    )
    retries = RetryConfig(max_attempts=3, rate_limit_cap=30.0)
    async with make_transport(handler, retries=retries) as t:
        await t.request_json("POST", V2_URL, json={})
    assert slept == [7.0]


async def test_rate_limit_wait_caps_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    async def _record(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr("dayshape._transport.asyncio.sleep", _record)

    handler = sequence_handler(
        httpx.Response(429, headers={"Retry-After": "999"}),
        httpx.Response(200, json={"ok": True}),
    )
    retries = RetryConfig(max_attempts=3, rate_limit_cap=10.0)
    async with make_transport(handler, retries=retries) as t:
        await t.request_json("POST", V2_URL, json={})
    assert slept == [10.0]  # 999 capped to rate_limit_cap


async def test_429_zero_retry_after_does_not_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Retry-After: 0 → delay is 0 → the wait short-circuits without sleeping.
    slept: list[float] = []

    async def _record(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr("dayshape._transport.asyncio.sleep", _record)

    handler = sequence_handler(
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"ok": True}),
    )
    retries = RetryConfig(max_attempts=3)
    async with make_transport(handler, retries=retries) as t:
        data, _ = await t.request_json("POST", V2_URL, json={})
    assert data == {"ok": True}
    assert slept == []  # delay==0 → no asyncio.sleep call


# --------------------------------------------------------------------------- #
# Timeout configuration threads through to the httpx client.
# --------------------------------------------------------------------------- #
async def test_timeout_config_is_applied() -> None:
    handler = sequence_handler(httpx.Response(200, json={}))
    t = make_transport(handler, timeout=TimeoutConfig(connect=1, read=2, write=3, pool=4))
    try:
        assert t._client.timeout.connect == 1
        assert t._client.timeout.read == 2
    finally:
        await t.aclose()
