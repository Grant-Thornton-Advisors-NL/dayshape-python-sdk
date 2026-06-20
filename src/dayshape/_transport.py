"""HTTP transport: one ``httpx.AsyncClient`` per client, with retries and error
mapping (plan.md §3).

A single async client (connection pool + TLS reuse) backs every request. Auth is
applied via :class:`~dayshape._auth.BearerAuth`; the ``/token`` exchange bypasses
it. Read-only report runs are safely retried on transient transport errors and
``502/503/504``; ``429`` is waited-out within the retry budget. Status codes map
to the typed exception hierarchy (§8). Content-type discipline: ``/token`` is
``text/plain``, ``/v2`` is JSON, ``/v2/export`` is XLSX bytes.
"""

from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any

import httpx

from ._auth import BearerAuth, Credentials, TokenManager
from ._logging import get_logger
from .config import DayshapeConfig
from .exceptions import (
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

_log = get_logger("transport")


class Transport:
    """Owns the async HTTP client, token lifecycle, retries, and error mapping."""

    def __init__(
        self,
        config: DayshapeConfig,
        *,
        httpx_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._credentials = Credentials(config.username, config.password)
        timeout = httpx.Timeout(
            connect=config.timeout.connect,
            read=config.timeout.read,
            write=config.timeout.write,
            pool=config.timeout.pool,
        )
        self._client = httpx.AsyncClient(timeout=timeout, transport=httpx_transport)
        self._tokens = TokenManager(
            self._login,
            refresh_skew=config.refresh_skew,
            assumed_ttl=config.assumed_token_ttl,
        )
        self._auth = BearerAuth(self._tokens)
        self._closed = False
        self._version_warned = False
        #: Latest API-version discovery headers seen on any response (plan.md §3.2).
        self._captured_versions: dict[str, str | None] = {
            "supported": None,
            "deprecated": None,
            "sunset": None,
        }

    # -- lifecycle ---------------------------------------------------------- #
    async def __aenter__(self) -> "Transport":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            await self._client.aclose()

    def _ensure_open(self) -> None:
        if self._closed:
            raise ClientClosedError("This DayshapeClient has been closed.")

    # -- token acquisition (bypasses BearerAuth) ---------------------------- #
    async def _login(self) -> str:
        url = f"{self._config.reporting_root()}/token"
        resp = await self._client.post(
            url,
            json=self._credentials.login_body(),
            headers={"Accept": "text/plain"},
        )
        # The token endpoint rejects bad credentials with 401 ("Invalid Username
        # or Password!") on current servers, or 403 ("not an API user") — both
        # mean the same thing to the caller: authentication failed at /token.
        # Map them to a single, actionable AuthenticationError rather than the
        # generic 401 message (which speaks of a token refresh that never
        # happened on the initial acquisition).
        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed ({resp.status_code}) at /token: invalid "
                "credentials, or the user is not configured as an API user."
            )
        if resp.status_code >= 400:
            raise self._error_for(resp)
        return resp.text.strip()

    async def login(self) -> None:
        """Eagerly acquire a token (fail-fast auth)."""
        self._ensure_open()
        await self._tokens.token()

    # -- public request helpers --------------------------------------------- #
    async def request_json(
        self,
        method: str,
        url: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, httpx.Headers]:
        resp = await self._send(method, url, json=json, params=params)
        try:
            return resp.json(), resp.headers
        except ValueError as exc:
            raise ResponseFormatError(
                f"Expected a JSON response from {url} but could not decode the body."
            ) from exc

    async def request_bytes(
        self,
        method: str,
        url: str,
        *,
        json: Any | None = None,
    ) -> tuple[bytes, httpx.Headers]:
        resp = await self._send(method, url, json=json, accept="application/octet-stream")
        return resp.content, resp.headers

    # -- core send with retries --------------------------------------------- #
    async def _send(
        self,
        method: str,
        url: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        accept: str = "application/json",
    ) -> httpx.Response:
        self._ensure_open()
        retries = self._config.retries
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.request(
                    method,
                    url,
                    json=json,
                    params=params,
                    headers={"Accept": accept},
                    auth=self._auth,
                )
            except httpx.TimeoutException as exc:
                if retries.enabled and attempt < retries.max_attempts:
                    await self._backoff(attempt)
                    continue
                raise DayshapeTimeoutError(
                    f"Request to {url} timed out. The server enforces a 15-minute "
                    "ceiling; this likely breached it."
                ) from exc
            except httpx.TransportError as exc:
                if retries.enabled and attempt < retries.max_attempts:
                    await self._backoff(attempt)
                    continue
                raise DayshapeConnectionError(
                    f"Network error contacting {url}: {exc}"
                ) from exc

            self._check_version(resp)
            self._capture_versions(resp.headers)
            status = resp.status_code
            if status < 400:
                return resp
            if status in retries.retry_statuses and attempt < retries.max_attempts:
                await self._backoff(attempt)
                continue
            if status == 429 and attempt < retries.max_attempts:
                await self._wait_rate_limit(resp, attempt)
                continue
            raise self._error_for(resp)

    # -- backoff ------------------------------------------------------------ #
    async def _backoff(self, attempt: int) -> None:
        cfg = self._config.retries
        delay = min(cfg.backoff_cap, cfg.backoff_base * (2 ** (attempt - 1)))
        delay += random.uniform(0.0, cfg.backoff_base * cfg.jitter)
        if delay > 0:
            await asyncio.sleep(delay)

    async def _wait_rate_limit(self, resp: httpx.Response, attempt: int) -> None:
        cfg = self._config.retries
        delay = self._retry_after_seconds(resp.headers.get("Retry-After"))
        if delay is None:
            delay = cfg.rate_limit_base * (2 ** (attempt - 1))
        delay = min(cfg.rate_limit_cap, delay)
        _log.debug("429 received; waiting %.2fs before retry", delay)
        if delay > 0:
            await asyncio.sleep(delay)

    @staticmethod
    def _retry_after_seconds(value: str | None) -> float | None:
        """Parse a ``Retry-After`` header in either delta-seconds or HTTP-date form."""
        if value is None:
            return None
        token = value.strip()
        if token.isdigit():
            return float(token)
        try:
            when = parsedate_to_datetime(token)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())

    # -- version discovery -------------------------------------------------- #
    @staticmethod
    def _normalise_version(value: str) -> str:
        """Canonicalise a version token to ``major.minor`` (``"v2"`` → ``"2.0"``)."""
        token = value.strip().lstrip("vV")
        return token if "." in token else f"{token}.0"

    def _check_version(self, resp: httpx.Response) -> None:
        if self._version_warned:
            return
        deprecated = resp.headers.get("Api-Deprecated-Versions")
        sunset = resp.headers.get("Sunset")
        in_use = self._normalise_version(self._config.api_version)
        deprecated_versions = {
            self._normalise_version(tok)
            for tok in re.split(r"[,\s]+", deprecated or "")
            if tok.strip()
        }
        if in_use in deprecated_versions or sunset:
            self._version_warned = True
            _log.warning(
                "The Dayshape API version in use (%s) is deprecated or scheduled "
                "for sunset (Sunset: %s). Plan to upgrade.",
                self._config.api_version,
                sunset,
            )

    def server_versions(self, headers: httpx.Headers) -> dict[str, str | None]:
        return {
            "supported": headers.get("Api-Supported-Versions"),
            "deprecated": headers.get("Api-Deprecated-Versions"),
            "sunset": headers.get("Sunset"),
        }

    def _capture_versions(self, headers: httpx.Headers) -> None:
        """Remember the latest non-empty version-discovery headers from a response."""
        for key, value in self.server_versions(headers).items():
            if value is not None:
                self._captured_versions[key] = value

    async def fetch_server_versions(self) -> dict[str, str | None]:
        """Return the server's API-version discovery headers (plan.md §3.2).

        Populated from any response's ``Api-Supported-Versions`` /
        ``Api-Deprecated-Versions`` / ``Sunset`` headers. If nothing has been
        captured yet, a single lightweight metadata request is made to populate
        it (the headers ride on ``/v2``-family responses, not ``/token`` or
        ``/status``). Best-effort: values stay ``None`` if the probe fails.
        """
        self._ensure_open()
        if all(v is None for v in self._captured_versions.values()):
            try:
                await self._send(
                    "GET",
                    f"{self._config.versioned_root()}/metadata",
                    params={"reportId": "WorkerListing"},
                )
            except DayshapeError:
                pass
        return dict(self._captured_versions)

    # -- error mapping ------------------------------------------------------ #
    def _error_for(self, resp: httpx.Response) -> DayshapeError:
        status = resp.status_code
        body = resp.text[:500]
        if status == 400:
            return BadRequestError(
                f"Bad request (400): the report query was rejected. {body}",
                response=resp,
            )
        if status == 401:
            return AuthenticationError(
                "Authentication failed (401) and persisted after a token refresh."
            )
        if status == 403:
            return PermissionDeniedError(
                "Permission denied (403): the API user lacks the required "
                f"Reporting_*_Read permission for this report. {body}",
                response=resp,
            )
        if status == 404:
            supported = resp.headers.get("Api-Supported-Versions")
            hint = f" Supported versions: {supported}." if supported else ""
            return NotFoundError(
                f"Not found (404): check base_url and api_version.{hint}",
                response=resp,
            )
        if status == 429:
            return ConcurrentReportLimitError(
                "Too many concurrent rate-limited reports (429); retry budget "
                "exhausted.",
                response=resp,
            )
        if status >= 500:
            return ServerError(
                f"Server error ({status}) after the retry budget was exhausted. {body}",
                response=resp,
            )
        return APIStatusError(f"Unexpected status {status}. {body}", response=resp)


__all__ = ["Transport"]
