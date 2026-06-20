"""The single report-execution path (plan.md §0.1, §3.5, §4.5).

Every report run — resource listing, relational hop, saved report, raw report —
flows through :class:`ReportRunner`. It applies the rate-limit gate, performs the
HTTP exchange via the transport, and decodes the columnar envelope into a
:class:`~dayshape.reports.result.ReportResult`.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO, Any

from .._ratelimit import RateLimitGate
from .._transport import Transport
from ..config import DayshapeConfig
from .metadata import ReportMetadata
from .query import QueryMessageV2
from .registry import resolve_report_id
from .result import ReportResult


class ReportRunner:
    """Coordinates auth, transport, rate limiting, and response decoding."""

    def __init__(
        self, transport: Transport, config: DayshapeConfig, gate: RateLimitGate
    ) -> None:
        self._transport = transport
        self._config = config
        self._gate = gate

    async def run(self, query: QueryMessageV2) -> ReportResult:
        """Run a ``QueryMessageV2`` via ``POST /v2`` (rate-gated when applicable)."""
        async with self._gate.guard(query.report_id):
            data, headers = await self._transport.request_json(
                "POST", self._config.versioned_root(), json=query.to_wire()
            )
        return ReportResult.from_envelope(data, headers)

    async def run_saved(self, report_hash: str) -> ReportResult:
        """Run a saved report by hash via ``GET /runSavedReport/{hash}``."""
        url = f"{self._config.reporting_root()}/runSavedReport/{report_hash}"
        data, headers = await self._transport.request_json("GET", url)
        return ReportResult.from_envelope(data, headers)

    async def get_saved_query(self, report_hash: str) -> QueryMessageV2:
        """Retrieve the stored query for a hash via ``GET /getReportQuery/{hash}``."""
        url = f"{self._config.reporting_root()}/getReportQuery/{report_hash}"
        data, _ = await self._transport.request_json("GET", url)
        payload = data.get("query", data) if isinstance(data, dict) else data
        return QueryMessageV2.model_validate(payload)

    async def metadata(
        self, report_id: str, sub_type: int | None = None
    ) -> ReportMetadata:
        """Fetch report metadata via ``GET /v2/metadata``."""
        url = f"{self._config.versioned_root()}/metadata"
        params: dict[str, Any] = {"reportId": resolve_report_id(report_id)}
        if sub_type is not None:
            params["reportSubTypeId"] = sub_type
        data, _ = await self._transport.request_json("GET", url, params=params)
        return ReportMetadata.model_validate(data)

    async def export(
        self, message: dict[str, Any], dest: Path | str | IO[bytes] | None = None
    ) -> bytes | None:
        """Run an export via ``POST /v2/export`` (XLSX bytes)."""
        url = f"{self._config.versioned_root()}/export"
        content, _ = await self._transport.request_bytes("POST", url, json=message)
        if dest is None:
            return content
        if isinstance(dest, (str, Path)):
            Path(dest).write_bytes(content)
        else:
            dest.write(content)
        return None

    async def overview(self) -> Any:
        """Fetch the production reports overview via ``GET /Info/reportsOverview``."""
        url = f"{self._config.reporting_root()}/Info/reportsOverview"
        data, _ = await self._transport.request_json("GET", url)
        return data

    async def status(self) -> bool:
        """Liveness probe via ``GET /status``."""
        url = f"{self._config.reporting_root()}/status"
        await self._transport.request_bytes("GET", url)
        return True


__all__ = ["ReportRunner"]
