"""The client surface: :class:`DayshapeClient` and its scoped view (plan.md §7).

``DayshapeClient`` owns the transport, token lifecycle, rate-limit gate, and the
report runner, and exposes typed resource namespaces. ``client.period(...)``
returns a lightweight :class:`ScopedClient` that binds a default
:class:`~dayshape.period.Period` to every query made through it (a *sync* context
manager — scoping does no I/O).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import TracebackType
from typing import TYPE_CHECKING

import httpx
from pydantic import SecretStr

from ._logging import configure
from ._ratelimit import RateLimitGate
from ._transport import Transport
from .config import DayshapeConfig, RetryConfig, TimeoutConfig
from .period import Period
from .reports.query import ReportFormattingOptions, default_formatting
from .reports.runner import ReportRunner
from .resources.actuals import ActualResource
from .resources.audit import AuditNamespace
from .resources.bookings import BookingResource
from .resources.clients import ClientResource
from .resources.exchange_rates import ExchangeRateResource
from .resources.job_groups import JobGroupResource
from .resources.jobs import JobResource
from .resources.rates import RateResource
from .resources.reports import RawReportResource
from .resources.timeseries import TimeSeriesNamespace
from .resources.traits import TraitResource
from .resources.unavailabilities import UnavailabilityResource
from .resources.units import UnitResource
from .resources.users import UserResource
from .resources.workers import WorkerResource

if TYPE_CHECKING:
    from .resources.base import ClientView


class DayshapeClient:
    """An async client for the Dayshape Reporting Service API."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | SecretStr | None = None,
        *,
        api_version: str = "v2",
        currency: str | None = None,
        instance_id: int | None = None,
        formatting: ReportFormattingOptions | None = None,
        timeout: TimeoutConfig | float | None = None,
        retries: RetryConfig | None = None,
        rate_limit_gate: bool = True,
        refresh_skew: timedelta = timedelta(seconds=60),
        assumed_token_ttl: timedelta = timedelta(hours=1),
        log_level: int | str | None = None,
        debug: bool = False,
        strict_models: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        pw = password.get_secret_value() if isinstance(password, SecretStr) else password
        self._config = DayshapeConfig.resolve(
            base_url=base_url,
            username=username,
            password=pw,
            api_version=api_version,
            currency=currency,
            instance_id=instance_id,
            rate_limit_gate=rate_limit_gate,
            refresh_skew=refresh_skew,
            assumed_token_ttl=assumed_token_ttl,
            strict_models=strict_models,
            timeout=TimeoutConfig.coerce(timeout),
            retries=retries if retries is not None else RetryConfig(),
        )
        configure("DEBUG" if debug else log_level)
        self._transport = Transport(self._config, httpx_transport=transport)
        self._gate = RateLimitGate(enabled=self._config.rate_limit_gate)
        self._runner = ReportRunner(self._transport, self._config, self._gate)
        self._formatting_opts = formatting or default_formatting()

        self._workers = WorkerResource(self)
        self._jobs = JobResource(self)
        self._bookings = BookingResource(self)
        self._job_groups = JobGroupResource(self)
        self._unavailabilities = UnavailabilityResource(self)
        self._users = UserResource(self)
        self._units = UnitResource(self)
        self._clients = ClientResource(self)
        self._traits = TraitResource(self)
        self._rates = RateResource(self)
        self._exchange_rates = ExchangeRateResource(self)
        self._actuals = ActualResource(self)
        self._audit = AuditNamespace(self)
        self._timeseries = TimeSeriesNamespace(self)
        self._reports = RawReportResource(self)

    # -- ClientView protocol ------------------------------------------------ #
    @property
    def _root(self) -> "DayshapeClient":
        return self

    @property
    def _formatting(self) -> ReportFormattingOptions:
        return self._formatting_opts

    def _scope_period(self) -> Period | None:
        return None

    def _ensure_open(self) -> None:
        self._transport._ensure_open()

    # -- resource namespaces ------------------------------------------------ #
    @property
    def workers(self) -> WorkerResource:
        return self._workers

    @property
    def jobs(self) -> JobResource:
        return self._jobs

    @property
    def bookings(self) -> BookingResource:
        return self._bookings

    @property
    def job_groups(self) -> JobGroupResource:
        return self._job_groups

    @property
    def unavailabilities(self) -> UnavailabilityResource:
        return self._unavailabilities

    @property
    def users(self) -> UserResource:
        return self._users

    @property
    def units(self) -> UnitResource:
        return self._units

    @property
    def clients(self) -> ClientResource:
        return self._clients

    @property
    def traits(self) -> TraitResource:
        return self._traits

    @property
    def rates(self) -> RateResource:
        return self._rates

    @property
    def exchange_rates(self) -> ExchangeRateResource:
        return self._exchange_rates

    @property
    def actuals(self) -> ActualResource:
        return self._actuals

    @property
    def audit(self) -> AuditNamespace:
        return self._audit

    @property
    def timeseries(self) -> TimeSeriesNamespace:
        return self._timeseries

    @property
    def reports(self) -> RawReportResource:
        return self._reports

    # -- temporal scoping --------------------------------------------------- #
    def period(
        self,
        period: Period | None = None,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> "ScopedClient":
        resolved = period
        if resolved is None and start is not None and end is not None:
            resolved = Period.between(start, end)
        if resolved is None:
            raise ValueError("period() requires a Period, or both start= and end=.")
        return ScopedClient(self, resolved)

    # -- lifecycle ---------------------------------------------------------- #
    async def __aenter__(self) -> "DayshapeClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def login(self) -> None:
        """Eagerly acquire a token (optional fail-fast auth)."""
        await self._transport.login()


class ScopedClient:
    """A period-bound view over a :class:`DayshapeClient` (plan.md §7.1)."""

    def __init__(self, root: DayshapeClient, period: Period) -> None:
        self._root_client = root
        self._period = period

    # -- ClientView protocol (delegates to the root) ------------------------ #
    @property
    def _runner(self) -> ReportRunner:
        return self._root_client._runner

    @property
    def _config(self) -> DayshapeConfig:
        return self._root_client._config

    @property
    def _root(self) -> DayshapeClient:
        return self._root_client

    @property
    def _formatting(self) -> ReportFormattingOptions:
        return self._root_client._formatting

    def _scope_period(self) -> Period | None:
        return self._period

    def _ensure_open(self) -> None:
        self._root_client._ensure_open()

    # -- resource namespaces (bound to this period) ------------------------- #
    @property
    def workers(self) -> WorkerResource:
        return WorkerResource(self)

    @property
    def jobs(self) -> JobResource:
        return JobResource(self)

    @property
    def bookings(self) -> BookingResource:
        return BookingResource(self)

    @property
    def job_groups(self) -> JobGroupResource:
        return JobGroupResource(self)

    @property
    def unavailabilities(self) -> UnavailabilityResource:
        return UnavailabilityResource(self)

    @property
    def users(self) -> UserResource:
        return UserResource(self)

    @property
    def units(self) -> UnitResource:
        return UnitResource(self)

    @property
    def clients(self) -> ClientResource:
        return ClientResource(self)

    @property
    def traits(self) -> TraitResource:
        return TraitResource(self)

    @property
    def rates(self) -> RateResource:
        return RateResource(self)

    @property
    def exchange_rates(self) -> ExchangeRateResource:
        return ExchangeRateResource(self)

    @property
    def actuals(self) -> ActualResource:
        return ActualResource(self)

    @property
    def audit(self) -> AuditNamespace:
        return AuditNamespace(self)

    @property
    def timeseries(self) -> TimeSeriesNamespace:
        return TimeSeriesNamespace(self)

    @property
    def reports(self) -> RawReportResource:
        return RawReportResource(self)

    # -- nested scoping ----------------------------------------------------- #
    def period(
        self,
        period: Period | None = None,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> "ScopedClient":
        return self._root_client.period(period, start=start, end=end)

    # -- sync context manager (scoping does no I/O) ------------------------- #
    def __enter__(self) -> "ScopedClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


# A static assertion that both client types satisfy the resource view protocol.
if TYPE_CHECKING:
    _root_view: "ClientView" = DayshapeClient.__new__(DayshapeClient)
    _scoped_view: "ClientView" = ScopedClient.__new__(ScopedClient)


__all__ = ["DayshapeClient", "ScopedClient"]
