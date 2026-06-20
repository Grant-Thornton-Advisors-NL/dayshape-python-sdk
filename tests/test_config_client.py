"""Tests for config, client lifecycle, logging, and the rate-limit gate.

Targets: ``config.py``, ``client.py`` lifecycle, ``_logging.py``, ``_ratelimit.py``.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from pydantic import SecretStr

from dayshape import DayshapeClient, Period
from dayshape._logging import RedactionFilter, configure, get_logger
from dayshape._ratelimit import RateLimitGate
from dayshape.client import ScopedClient
from dayshape.config import (
    ENV_BASE_URL,
    ENV_PASSWORD,
    ENV_USERNAME,
    DayshapeConfig,
    RetryConfig,
    TimeoutConfig,
)
from dayshape.exceptions import ClientClosedError
from dayshape.resources.bookings import BookingResource
from dayshape.resources.clients import ClientResource

from conftest import BASE_URL, MockBackend, build_client


# --------------------------------------------------------------------------- #
# DayshapeConfig.resolve — env fallback & validation
# --------------------------------------------------------------------------- #
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (ENV_BASE_URL, ENV_USERNAME, ENV_PASSWORD):
        monkeypatch.delenv(name, raising=False)


def test_resolve_explicit_args_win(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    cfg = DayshapeConfig.resolve(
        base_url="https://x.dayshape.app", username="alice", password="pw"
    )
    assert cfg.base_url == "https://x.dayshape.app"
    assert cfg.username == "alice"
    assert cfg.password == "pw"


def test_resolve_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_BASE_URL, "https://env.dayshape.app")
    monkeypatch.setenv(ENV_USERNAME, "env-user")
    monkeypatch.setenv(ENV_PASSWORD, "env-pass")
    cfg = DayshapeConfig.resolve(base_url=None, username=None, password=None)
    assert cfg.base_url == "https://env.dayshape.app"
    assert cfg.username == "env-user"
    assert cfg.password == "env-pass"


def test_resolve_missing_all_raises_listing_names(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    with pytest.raises(ValueError) as excinfo:
        DayshapeConfig.resolve(base_url=None, username=None, password=None)
    msg = str(excinfo.value)
    assert ENV_BASE_URL in msg
    assert ENV_USERNAME in msg
    assert ENV_PASSWORD in msg


def test_resolve_missing_one_lists_only_that_name(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    with pytest.raises(ValueError) as excinfo:
        DayshapeConfig.resolve(
            base_url="https://x.dayshape.app", username="alice", password=None
        )
    msg = str(excinfo.value)
    assert ENV_PASSWORD in msg
    assert ENV_BASE_URL not in msg
    assert ENV_USERNAME not in msg


def test_resolve_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    cfg = DayshapeConfig.resolve(
        base_url="https://x.dayshape.app///", username="alice", password="pw"
    )
    assert cfg.base_url == "https://x.dayshape.app"


def test_resolve_passes_through_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    cfg = DayshapeConfig.resolve(
        base_url="https://x.dayshape.app",
        username="alice",
        password="pw",
        currency="USD",
        instance_id=7,
        strict_models=True,
    )
    assert cfg.currency == "USD"
    assert cfg.instance_id == 7
    assert cfg.strict_models is True


def test_reporting_and_versioned_roots() -> None:
    cfg = DayshapeConfig(base_url="https://x.dayshape.app", username="u", password="p")
    assert cfg.reporting_root() == "https://x.dayshape.app/reporting"
    assert cfg.versioned_root() == "https://x.dayshape.app/reporting/v2"


def test_versioned_root_honours_api_version() -> None:
    cfg = DayshapeConfig(
        base_url="https://x.dayshape.app", username="u", password="p", api_version="v3"
    )
    assert cfg.versioned_root() == "https://x.dayshape.app/reporting/v3"


# --------------------------------------------------------------------------- #
# TimeoutConfig.coerce
# --------------------------------------------------------------------------- #
def test_timeout_coerce_none_returns_defaults() -> None:
    tc = TimeoutConfig.coerce(None)
    assert isinstance(tc, TimeoutConfig)
    assert tc.connect == 10.0
    assert tc.read == 930.0
    assert tc.write == 60.0
    assert tc.pool == 10.0


def test_timeout_coerce_float_sets_every_phase() -> None:
    tc = TimeoutConfig.coerce(5.0)
    assert tc.connect == 5.0
    assert tc.read == 5.0
    assert tc.write == 5.0
    assert tc.pool == 5.0


def test_timeout_coerce_passes_instance_through() -> None:
    original = TimeoutConfig(connect=1.0, read=2.0, write=3.0, pool=4.0)
    assert TimeoutConfig.coerce(original) is original


# --------------------------------------------------------------------------- #
# RetryConfig
# --------------------------------------------------------------------------- #
def test_retry_default_is_enabled() -> None:
    assert RetryConfig().enabled is True
    assert RetryConfig().max_attempts == 3


def test_retry_disabled_classmethod() -> None:
    rc = RetryConfig.disabled()
    assert rc.max_attempts == 1
    assert rc.enabled is False


def test_retry_enabled_property_threshold() -> None:
    assert RetryConfig(max_attempts=2).enabled is True
    assert RetryConfig(max_attempts=1).enabled is False


# --------------------------------------------------------------------------- #
# DayshapeClient — construction & credentials
# --------------------------------------------------------------------------- #
async def test_construct_with_explicit_creds_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    # build_client supplies explicit base_url/username/password; no env needed.
    async with build_client() as client:
        assert client._config.base_url == BASE_URL
        assert client._config.username == "user"
        assert client._config.password == "pass"


async def test_password_secretstr_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    async with build_client(password=SecretStr("s3cret")) as client:
        # SecretStr is unwrapped to a plain string in the resolved config.
        assert client._config.password == "s3cret"


# --------------------------------------------------------------------------- #
# DayshapeClient — lifecycle
# --------------------------------------------------------------------------- #
async def test_context_manager_enter_returns_self() -> None:
    async with build_client() as client:
        assert isinstance(client, DayshapeClient)
        client._ensure_open()  # does not raise while open


async def test_exit_closes_transport_then_use_raises() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        pass
    # After exit the transport is closed; any open-requiring use raises.
    with pytest.raises(ClientClosedError):
        client._ensure_open()


async def test_closed_client_login_raises() -> None:
    client = build_client()
    await client.aclose()
    with pytest.raises(ClientClosedError):
        await client.login()


async def test_aclose_is_idempotent() -> None:
    client = build_client()
    await client.aclose()
    await client.aclose()  # second close must not raise
    with pytest.raises(ClientClosedError):
        client._ensure_open()


async def test_login_acquires_token() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        await client.login()
    assert backend.token_calls == 1


async def test_debug_flag_does_not_error() -> None:
    async with build_client(debug=True) as client:
        assert isinstance(client, DayshapeClient)


# --------------------------------------------------------------------------- #
# DayshapeClient — period scoping
# --------------------------------------------------------------------------- #
def test_period_with_period_object_builds_scope() -> None:
    client = build_client()
    scoped = client.period(Period.year(2026))
    assert isinstance(scoped, ScopedClient)
    assert scoped._scope_period() == Period.year(2026)


def test_period_with_start_and_end_builds_scope() -> None:
    client = build_client()
    yr = Period.year(2026)
    scoped = client.period(start=yr.start, end=yr.end)
    assert isinstance(scoped, ScopedClient)
    assert scoped._scope_period() == yr


def test_period_with_neither_raises_value_error() -> None:
    client = build_client()
    with pytest.raises(ValueError):
        client.period()


def test_period_as_sync_context_manager() -> None:
    client = build_client()
    with client.period(Period.year(2026)) as scoped:
        assert isinstance(scoped, ScopedClient)


def test_nested_scoped_period_delegates_to_root() -> None:
    client = build_client()
    outer = client.period(Period.year(2026))
    inner = outer.period(Period.year(2025))
    assert isinstance(inner, ScopedClient)
    assert inner._scope_period() == Period.year(2025)
    assert inner._root is client


# --------------------------------------------------------------------------- #
# DayshapeClient — resource property types
# --------------------------------------------------------------------------- #
def test_root_resource_properties_return_expected_types() -> None:
    client = build_client()
    assert isinstance(client.bookings, BookingResource)
    assert isinstance(client.clients, ClientResource)


def test_scoped_resource_properties_return_expected_types() -> None:
    client = build_client()
    scoped = client.period(Period.year(2026))
    assert isinstance(scoped.bookings, BookingResource)
    assert isinstance(scoped.clients, ClientResource)


async def test_query_through_scoped_client_round_trips() -> None:
    backend = MockBackend()
    async with build_client(backend) as client:
        with client.period(Period.year(2026)) as c:
            rows = await c.bookings.list(dimensions=["TaskId"])
    assert isinstance(rows, list)
    assert backend.v2_calls == 1


# --------------------------------------------------------------------------- #
# _logging
# --------------------------------------------------------------------------- #
def test_get_logger_returns_child() -> None:
    child = get_logger("transport")
    assert child.name == "dayshape.transport"
    assert child.parent is get_logger()


def test_get_logger_attaches_redaction_filter_once() -> None:
    base = get_logger()
    get_logger("a")
    get_logger("b")
    redaction_filters = [f for f in base.filters if isinstance(f, RedactionFilter)]
    assert len(redaction_filters) == 1


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="dayshape.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_redaction_filter_scrubs_bearer_token() -> None:
    flt = RedactionFilter()
    rec = _record("Authorization: Bearer abc.def.ghi sent to server")
    assert flt.filter(rec) is True
    out = rec.getMessage()
    assert "abc.def.ghi" not in out
    assert "Bearer ***" in out


def test_redaction_filter_scrubs_password_occurrence() -> None:
    flt = RedactionFilter()
    rec = _record('login body {"password": "hunter2", "username": "x"}')
    assert flt.filter(rec) is True
    out = rec.getMessage()
    assert "hunter2" not in out
    assert "***" in out


def test_redaction_filter_scrubs_password_equals_form() -> None:
    flt = RedactionFilter()
    rec = _record("query string password=hunter2&next=1")
    assert flt.filter(rec) is True
    out = rec.getMessage()
    assert "hunter2" not in out


def test_redaction_filter_leaves_clean_message_untouched() -> None:
    flt = RedactionFilter()
    rec = _record("a perfectly innocent %s message", "log")
    assert flt.filter(rec) is True
    # No secret → args preserved and message interpolates normally.
    assert rec.getMessage() == "a perfectly innocent log message"
    assert rec.args == ("log",)


def test_configure_sets_level() -> None:
    base = get_logger()
    original = base.level
    try:
        configure(logging.WARNING)
        assert base.level == logging.WARNING
    finally:
        base.setLevel(original)


def test_configure_none_leaves_level_untouched() -> None:
    base = get_logger()
    base.setLevel(logging.ERROR)
    try:
        configure(None)
        assert base.level == logging.ERROR
    finally:
        base.setLevel(logging.NOTSET)


# --------------------------------------------------------------------------- #
# _ratelimit — RateLimitGate
# --------------------------------------------------------------------------- #
async def test_gate_serialises_rate_limited_report() -> None:
    gate = RateLimitGate(enabled=True)
    overlap = {"concurrent": 0, "max": 0}

    async def worker() -> None:
        async with gate.guard("TaskListing"):
            overlap["concurrent"] += 1
            overlap["max"] = max(overlap["max"], overlap["concurrent"])
            # Yield control so a second task could overlap if not serialised.
            await asyncio.sleep(0.01)
            overlap["concurrent"] -= 1

    await asyncio.gather(worker(), worker())
    # Rate-limited reports must never run concurrently through the gate.
    assert overlap["max"] == 1


async def test_gate_does_not_block_non_rate_limited_report() -> None:
    gate = RateLimitGate(enabled=True)
    overlap = {"concurrent": 0, "max": 0}

    async def worker() -> None:
        async with gate.guard("ClientListing"):
            overlap["concurrent"] += 1
            overlap["max"] = max(overlap["max"], overlap["concurrent"])
            await asyncio.sleep(0.01)
            overlap["concurrent"] -= 1

    await asyncio.gather(worker(), worker())
    # ClientListing is not rate-limited → both run concurrently.
    assert overlap["max"] == 2


async def test_gate_disabled_bypasses_serialisation() -> None:
    gate = RateLimitGate(enabled=False)
    overlap = {"concurrent": 0, "max": 0}

    async def worker() -> None:
        async with gate.guard("TaskListing"):
            overlap["concurrent"] += 1
            overlap["max"] = max(overlap["max"], overlap["concurrent"])
            await asyncio.sleep(0.01)
            overlap["concurrent"] -= 1

    await asyncio.gather(worker(), worker())
    # enabled=False → gate is a no-op even for rate-limited reports.
    assert overlap["max"] == 2


async def test_gate_lazy_semaphore_created_in_loop() -> None:
    gate = RateLimitGate(enabled=True)
    # Constructed outside any guard → semaphore not yet created.
    assert gate._semaphore is None
    async with gate.guard("TaskListing"):
        pass
    assert gate._semaphore is not None
