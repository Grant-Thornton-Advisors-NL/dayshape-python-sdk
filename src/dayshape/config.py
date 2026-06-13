"""Configuration objects and environment resolution (plan.md §3, §7.3)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta

#: Documented server ceiling per request (15 minutes). The default read timeout
#: sits just above this so the server's diagnosable error wins (plan.md §3.1).
SERVER_REQUEST_CEILING = timedelta(minutes=15)

ENV_BASE_URL = "DAYSHAPE_BASE_URL"
ENV_USERNAME = "DAYSHAPE_USERNAME"
ENV_PASSWORD = "DAYSHAPE_PASSWORD"


@dataclass(frozen=True, slots=True)
class TimeoutConfig:
    """Per-phase HTTP timeouts in seconds (plan.md §3.1).

    The ``read`` default (930 s) is deliberately just above the server's 15-minute
    ceiling so that a server-side timeout (a diagnosable HTTP error) is returned
    before the client's own ``ReadTimeout`` fires.
    """

    connect: float = 10.0
    read: float = 930.0
    write: float = 60.0
    pool: float = 10.0

    @classmethod
    def coerce(cls, value: "TimeoutConfig | float | None") -> "TimeoutConfig":
        if value is None:
            return cls()
        if isinstance(value, TimeoutConfig):
            return value
        # A bare number sets every phase to that value.
        return cls(connect=value, read=value, write=value, pool=value)


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Transient-retry policy (plan.md §3.3).

    Report runs are read-only, so replay is safe. ``429`` is retried within
    ``max_attempts`` honouring ``Retry-After`` when present; on exhaustion a
    :class:`~dayshape.exceptions.ConcurrentReportLimitError` is raised.
    """

    max_attempts: int = 3
    backoff_base: float = 0.5
    backoff_cap: float = 30.0
    jitter: float = 0.2
    #: Backoff bounds used specifically for ``429`` waits.
    rate_limit_base: float = 2.0
    rate_limit_cap: float = 30.0
    #: Status codes eligible for transient retry.
    retry_statuses: frozenset[int] = frozenset({502, 503, 504})

    @property
    def enabled(self) -> bool:
        return self.max_attempts > 1

    @classmethod
    def disabled(cls) -> "RetryConfig":
        return cls(max_attempts=1)


@dataclass(frozen=True, slots=True)
class DayshapeConfig:
    """Resolved client configuration (plan.md §7.3).

    Construction parameters fall back to ``DAYSHAPE_*`` environment variables.
    ``password`` is kept here only as a plain string at the boundary; it is wrapped
    in a :class:`~pydantic.SecretStr` by the auth layer and never logged.
    """

    base_url: str
    username: str
    password: str
    api_version: str = "v2"
    currency: str | None = None
    instance_id: int | None = None
    rate_limit_gate: bool = True
    refresh_skew: timedelta = timedelta(seconds=60)
    assumed_token_ttl: timedelta = timedelta(hours=1)
    strict_models: bool = False
    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    retries: RetryConfig = field(default_factory=RetryConfig)

    @classmethod
    def resolve(
        cls,
        *,
        base_url: str | None,
        username: str | None,
        password: str | None,
        **kwargs: object,
    ) -> "DayshapeConfig":
        """Resolve explicit args against the environment, validating presence."""
        resolved_base = base_url or os.environ.get(ENV_BASE_URL)
        resolved_user = username or os.environ.get(ENV_USERNAME)
        resolved_pass = password or os.environ.get(ENV_PASSWORD)

        missing = [
            name
            for name, value in (
                (ENV_BASE_URL, resolved_base),
                (ENV_USERNAME, resolved_user),
                (ENV_PASSWORD, resolved_pass),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing required configuration: "
                + ", ".join(missing)
                + ". Pass it to DayshapeClient(...) or set the environment variable."
            )

        # mypy: the missing-check above guarantees these are non-None.
        assert resolved_base and resolved_user and resolved_pass
        return cls(
            base_url=resolved_base.rstrip("/"),
            username=resolved_user,
            password=resolved_pass,
            **kwargs,  # type: ignore[arg-type]
        )

    def reporting_root(self) -> str:
        """Base URL for the reporting service, e.g. ``https://x.dayshape.app/reporting``."""
        return f"{self.base_url}/reporting"

    def versioned_root(self) -> str:
        """Versioned route prefix, e.g. ``.../reporting/v2``."""
        return f"{self.reporting_root()}/{self.api_version}"


__all__ = [
    "DayshapeConfig",
    "TimeoutConfig",
    "RetryConfig",
    "SERVER_REQUEST_CEILING",
    "ENV_BASE_URL",
    "ENV_USERNAME",
    "ENV_PASSWORD",
]
