"""The raw reports namespace — escape hatch + saved/metadata/export (plan.md §7.3)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any

from .._chunking import ChunkSpec
from .._query import ReportQuery
from ..exceptions import QueryError
from ..period import Period
from ..reports.metadata import ReportMetadata
from ..reports.query import (
    ComparativeDimension,
    Dimension,
    Filter,
    PivotConfig,
    QueryMessageV2,
    ReportFormattingOptions,
)
from ..reports.registry import resolve_report_id
from ..reports.result import ReportResult, ResultMeta  # noqa: F401  (re-export convenience)
from ..reports.saved import SavedReportRef
from .base import ClientView


class RawReportResource:
    """Run any report by id, returning raw ``{dimension_id: cell}`` dict rows."""

    def __init__(self, view: ClientView) -> None:
        self._view = view

    def _resolve_period(self, override: Period | None) -> Period:
        period = override if override is not None else self._view._scope_period()
        if period is None:
            raise QueryError(
                "No reporting period is set. Pass period= or use client.period(...)."
            )
        return period

    def run(
        self,
        report_id: str,
        *,
        period: Period | None = None,
        dimensions: Sequence[Any] = (),
        comparative_dimensions: Sequence[ComparativeDimension] = (),
        filters: Sequence[Filter] = (),
        sub_type: int | None = None,
        currency: str | None = None,
        chunk: Any = None,
        formatting: ReportFormattingOptions | None = None,
        allow_unordered: bool = False,
        dedupe_on: str | None = None,
    ) -> "ReportQuery[dict[str, Any]]":
        view = self._view
        view._ensure_open()
        resolved = self._resolve_period(period)
        dims = [Dimension.coerce(d) for d in dimensions]
        chunk_spec = ChunkSpec.parse(chunk)
        if (
            chunk_spec is not None
            and not allow_unordered
            and any(d.order is not None for d in dims)
        ):
            raise QueryError(
                "chunk= breaks global ordering; drop the sort or pass allow_unordered=True."
            )
        query = QueryMessageV2(
            report_id=resolve_report_id(report_id),
            sub_type=sub_type,
            currency=currency if currency is not None else view._config.currency,
            instance_id=view._config.instance_id,
            from_=resolved.start,
            to=resolved.end,
            dimensions=dims,
            comparative_dimensions=list(comparative_dimensions),
            filters=list(filters),
            report_formatting_options=formatting or view._formatting,
        )
        identity = dims[0].dimension_id if dims else None
        return ReportQuery(
            runner=view._runner,
            decode=lambda record: record,
            query=query,
            period=resolved,
            chunk=chunk_spec,
            dedupe_on=dedupe_on,
            identity_dimension=identity,
            allow_unordered=allow_unordered,
        )

    async def metadata(
        self, report_id: str, sub_type: int | None = None
    ) -> ReportMetadata:
        self._view._ensure_open()
        return await self._view._runner.metadata(resolve_report_id(report_id), sub_type)

    async def export(
        self,
        report_id: str,
        *,
        period: Period | None = None,
        dimensions: Sequence[Any] = (),
        filters: Sequence[Filter] = (),
        pivot: PivotConfig | None = None,
        sub_type: int | None = None,
        currency: str | None = None,
        formatting: ReportFormattingOptions | None = None,
        dest: Path | str | IO[bytes] | None = None,
    ) -> bytes | None:
        view = self._view
        view._ensure_open()
        resolved = self._resolve_period(period)
        query = QueryMessageV2(
            report_id=resolve_report_id(report_id),
            sub_type=sub_type,
            currency=currency if currency is not None else view._config.currency,
            instance_id=view._config.instance_id,
            from_=resolved.start,
            to=resolved.end,
            dimensions=[Dimension.coerce(d) for d in dimensions],
            filters=list(filters),
            report_formatting_options=formatting or view._formatting,
        )
        body = query.to_wire()
        if pivot is not None:
            body["pivot"] = pivot.model_dump(by_alias=True, exclude_none=True)
        return await view._runner.export(body, dest)

    def saved(self, report_hash: str) -> SavedReportRef:
        return SavedReportRef(self._view._runner, report_hash)

    async def overview(self) -> Any:
        self._view._ensure_open()
        return await self._view._runner.overview()

    async def status(self) -> bool:
        self._view._ensure_open()
        return await self._view._runner.status()


__all__ = ["RawReportResource"]
