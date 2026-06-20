"""Per-client concurrency gate for rate-limited reports (plan.md §3.5).

Seventeen reports are limited to one concurrent execution per user; a second
concurrent run returns HTTP 429. The registry flags these (``rate_limited=True``)
and the runner routes them through a per-client :class:`asyncio.Semaphore(1)` so
the SDK serialises them locally rather than relying solely on the retry backstop.

The gate is *per client instance* while the server rule is *per user* — multi
-client/same-user deployments fall back to the §3.3 retry policy (residual R-6).
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from ._logging import get_logger
from .reports.registry import is_rate_limited

_log = get_logger("ratelimit")


class RateLimitGate:
    """Serialises rate-limited reports through a single-permit semaphore.

    ``enabled=False`` (``rate_limit_gate=False`` on the client) makes every
    acquisition a no-op, deferring entirely to the transport's 429 handling.
    """

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        # Created lazily inside the running loop so the gate can be constructed
        # outside any event loop (e.g. at client init).
        self._semaphore: asyncio.Semaphore | None = None

    def _gate(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(1)
        return self._semaphore

    @asynccontextmanager
    async def guard(self, report_id: str) -> AsyncIterator[None]:
        """Acquire the gate for ``report_id`` if it is rate-limited, else pass through."""
        if not self._enabled or not is_rate_limited(report_id):
            yield
            return
        gate = self._gate()
        waited = not gate.locked()
        start = time.monotonic()
        async with gate:
            if not waited:
                _log.debug(
                    "rate-limit gate: waited %.3fs for %s",
                    time.monotonic() - start,
                    report_id,
                )
            yield


__all__ = ["RateLimitGate"]
