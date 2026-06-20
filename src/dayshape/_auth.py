"""Token acquisition, expiry detection, and single-flight refresh (plan.md §2).

The confirmed contract: ``POST {base}/reporting/token`` with a ``LoginModel``
body returns the raw JWT as ``text/plain``; invalid credentials return ``403``.
Tokens expire (issuer-configurable; ~1 h assumed). Recovery for a ``401`` is a
single refresh-and-replay.

Expiry detection has three layers:

1. the JWT ``exp`` claim (base64-decoded payload, *no signature verification* —
   a scheduling hint only);
2. an assumed-TTL fallback when ``exp`` is absent or undecodable;
3. the reactive ``401`` safety net handled by :class:`BearerAuth`.

Refresh is *single-flight*: concurrent callers that observe the same stale token
piggyback on one in-flight refresh via a generation counter under an
:class:`asyncio.Lock` created lazily inside the running loop. ``Credentials``
holds the password as a :class:`~pydantic.SecretStr`; nothing secret is logged.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import httpx
from pydantic import SecretStr

from ._logging import get_logger

_log = get_logger("auth")

#: Signature of the coroutine that performs the raw ``POST /token`` exchange and
#: returns the JWT string (or raises :class:`AuthenticationError` on ``403``).
TokenAcquirer = Callable[[], Awaitable[str]]


class Credentials:
    """Username + password, with the password sealed in a :class:`SecretStr`."""

    __slots__ = ("username", "_password")

    def __init__(self, username: str, password: str | SecretStr) -> None:
        self.username = username
        self._password: SecretStr = (
            password if isinstance(password, SecretStr) else SecretStr(password)
        )

    @property
    def password(self) -> SecretStr:
        return self._password

    def login_body(self) -> dict[str, str]:
        """The ``LoginModel`` JSON body for ``POST /token``."""
        return {"username": self.username, "password": self._password.get_secret_value()}

    def __repr__(self) -> str:  # never leak the secret
        return f"Credentials(username={self.username!r}, password=SecretStr('**********'))"


@dataclass(frozen=True, slots=True)
class _TokenState:
    """An immutable snapshot of the current token, its expiry, and its generation."""

    token: str
    expires_at: float  # epoch seconds
    generation: int


def decode_exp(token: str) -> int | None:
    """Return the JWT ``exp`` claim (epoch seconds), or ``None`` if undecodable.

    No signature verification is performed — this is a scheduling hint only.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload + padding)
        claims = json.loads(raw)
    except (binascii.Error, ValueError):
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    if isinstance(exp, (int, float)):
        return int(exp)
    return None


class TokenManager:
    """Holds the current token and refreshes it single-flight."""

    def __init__(
        self,
        acquire: TokenAcquirer,
        *,
        refresh_skew: timedelta = timedelta(seconds=60),
        assumed_ttl: timedelta = timedelta(hours=1),
        now: Callable[[], float] = time.time,
    ) -> None:
        self._acquire = acquire
        self._skew = refresh_skew.total_seconds()
        self._assumed_ttl = assumed_ttl.total_seconds()
        self._now = now
        self._state: _TokenState | None = None
        self._generation = 0
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        # Created lazily so the manager can be built outside a running loop.
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _expiry_for(self, token: str) -> float:
        exp = decode_exp(token)
        if exp is not None:
            return float(exp)
        return self._now() + self._assumed_ttl

    def _is_stale(self, state: _TokenState) -> bool:
        return self._now() >= state.expires_at - self._skew

    async def _store_new(self) -> str:
        """Acquire a fresh token and publish a new state snapshot. Caller holds the lock."""
        token = await self._acquire()
        self._generation += 1
        self._state = _TokenState(token, self._expiry_for(token), self._generation)
        return token

    async def token(self) -> str:
        """Return a valid token, refreshing if the current one is missing or stale."""
        state = self._state
        if state is not None and not self._is_stale(state):
            return state.token
        seen_generation = state.generation if state is not None else 0
        async with self._get_lock():
            current = self._state
            # Single-flight: another caller refreshed while we waited for the lock.
            if (
                current is not None
                and current.generation != seen_generation
                and not self._is_stale(current)
            ):
                return current.token
            return await self._store_new()

    async def refresh_for_401(self, stale_token: str) -> str:
        """Force one refresh in response to a ``401`` (single-flight replay path)."""
        async with self._get_lock():
            current = self._state
            # Another 401 handler already rotated the token we were carrying.
            if (
                current is not None
                and current.token != stale_token
                and not self._is_stale(current)
            ):
                return current.token
            _log.debug("refreshing token after 401")
            return await self._store_new()


class BearerAuth(httpx.Auth):
    """Attaches ``Authorization: Bearer`` and performs the single refresh-and-replay."""

    requires_response_body = False

    def __init__(self, manager: TokenManager) -> None:
        self._manager = manager

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await self._manager.token()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == 401:
            refreshed = await self._manager.refresh_for_401(token)
            request.headers["Authorization"] = f"Bearer {refreshed}"
            yield request


__all__ = [
    "Credentials",
    "TokenManager",
    "BearerAuth",
    "TokenAcquirer",
    "decode_exp",
]
