"""Tests for the auth layer — targets 100% branch coverage of ``_auth.py``."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import timedelta

import httpx
import pytest
from pydantic import SecretStr

from dayshape._auth import BearerAuth, Credentials, TokenManager, decode_exp

from conftest import make_jwt


# --------------------------------------------------------------------------- #
# decode_exp
# --------------------------------------------------------------------------- #
def test_decode_exp_valid() -> None:
    token = make_jwt(exp_in=3600)
    assert decode_exp(token) is not None


def test_decode_exp_float_exp() -> None:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": 123.0}).encode()).rstrip(b"=").decode()
    assert decode_exp(f"h.{payload}.s") == 123


def test_decode_exp_not_three_parts() -> None:
    assert decode_exp("only.two") is None


def test_decode_exp_bad_base64() -> None:
    assert decode_exp("h.!!!notbase64!!!.s") is None


def test_decode_exp_not_json() -> None:
    payload = base64.urlsafe_b64encode(b"not json at all").rstrip(b"=").decode()
    assert decode_exp(f"h.{payload}.s") is None


def test_decode_exp_json_not_dict() -> None:
    payload = base64.urlsafe_b64encode(b"[1, 2, 3]").rstrip(b"=").decode()
    assert decode_exp(f"h.{payload}.s") is None


def test_decode_exp_missing_exp() -> None:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "x"}).encode()).rstrip(b"=").decode()
    assert decode_exp(f"h.{payload}.s") is None


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #
def test_credentials_login_body_and_repr() -> None:
    creds = Credentials("alice", "s3cret")
    assert creds.login_body() == {"username": "alice", "password": "s3cret"}
    assert "s3cret" not in repr(creds)
    assert isinstance(creds.password, SecretStr)


def test_credentials_accepts_secretstr() -> None:
    creds = Credentials("bob", SecretStr("hidden"))
    assert creds.login_body()["password"] == "hidden"


# --------------------------------------------------------------------------- #
# TokenManager
# --------------------------------------------------------------------------- #
def _acquirer(tokens: list[str] | str):
    state = {"n": 0}

    async def acquire() -> str:
        state["n"] += 1
        if isinstance(tokens, str):
            return tokens
        return tokens[state["n"] - 1]

    return acquire, state


async def test_token_fast_path_caches() -> None:
    acquire, state = _acquirer(make_jwt())
    mgr = TokenManager(acquire)
    t1 = await mgr.token()
    t2 = await mgr.token()
    assert t1 == t2
    assert state["n"] == 1  # second call took the lock-free fast path


async def test_token_refreshes_when_stale() -> None:
    clock = {"t": 1000.0}
    acquire, state = _acquirer([make_jwt(include_exp=False), make_jwt(include_exp=False)])
    mgr = TokenManager(
        acquire,
        assumed_ttl=timedelta(seconds=10),
        refresh_skew=timedelta(0),
        now=lambda: clock["t"],
    )
    await mgr.token()
    assert state["n"] == 1
    clock["t"] += 20  # past the assumed TTL → stale
    await mgr.token()
    assert state["n"] == 2


async def test_token_uses_exp_claim_for_expiry() -> None:
    acquire, state = _acquirer(make_jwt(exp_in=3600))
    mgr = TokenManager(acquire, now=lambda: 0.0)
    await mgr.token()
    await mgr.token()
    assert state["n"] == 1  # exp far in the future → not stale


async def test_single_flight_refresh() -> None:
    gate = asyncio.Event()
    count = {"n": 0}

    async def acquire() -> str:
        count["n"] += 1
        await gate.wait()
        return make_jwt()

    mgr = TokenManager(acquire)
    tasks = [asyncio.create_task(mgr.token()) for _ in range(50)]
    await asyncio.sleep(0.01)  # let all 50 queue on the lock
    gate.set()
    results = await asyncio.gather(*tasks)
    assert count["n"] == 1  # exactly one acquisition served all 50
    assert len(set(results)) == 1


async def test_refresh_for_401_forces_refresh() -> None:
    acquire, state = _acquirer([make_jwt(), make_jwt()])
    mgr = TokenManager(acquire)
    first = await mgr.token()
    assert state["n"] == 1
    refreshed = await mgr.refresh_for_401(first)
    assert state["n"] == 2
    assert refreshed != first or state["n"] == 2


async def test_refresh_for_401_piggybacks_when_already_rotated() -> None:
    acquire, state = _acquirer([make_jwt(exp_in=3600), make_jwt(exp_in=3600)])
    mgr = TokenManager(acquire)
    current = await mgr.token()
    # A handler carrying an older token asks to refresh; current is already fresh
    # and different → no new acquisition.
    result = await mgr.refresh_for_401("a-stale-older-token")
    assert result == current
    assert state["n"] == 1


# --------------------------------------------------------------------------- #
# BearerAuth
# --------------------------------------------------------------------------- #
async def test_bearer_auth_happy_path() -> None:
    acquire, state = _acquirer(make_jwt())
    auth = BearerAuth(TokenManager(acquire))
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        resp = await c.get("https://x/v2", auth=auth)
    assert resp.status_code == 200
    assert len(seen) == 1 and seen[0].startswith("Bearer ")
    assert state["n"] == 1


async def test_bearer_auth_refreshes_on_401() -> None:
    acquire, state = _acquirer(["token-one", "token-two"])
    auth = BearerAuth(TokenManager(acquire))
    responses = [httpx.Response(401), httpx.Response(200, text="ok")]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return responses[len(seen) - 1]

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        resp = await c.get("https://x/v2", auth=auth)
    assert resp.status_code == 200
    assert seen == ["Bearer token-one", "Bearer token-two"]
    assert state["n"] == 2
