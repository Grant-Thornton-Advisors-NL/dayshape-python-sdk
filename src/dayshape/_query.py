"""The single collection-consumption contract: ``ReportQuery[T]`` (plan.md §5.1).

Every multi-row retrieval — resource listing, relational hop, saved report, raw
report — returns the same lazy object, consumed the same two ways::

    async for row in query: ...   # stream
    rows = await query            # materialise to a list

Construction performs no I/O (principle #4); the request fires on first
consumption. Queries are immutable — ``with_period`` / ``with_chunk`` return new
instances — and re-running a query runs it again (no implicit caching).
"""

from __future__ import annotations

import warnings
from collections.abc import AsyncIterator, Awaitable, Callable, Generator
from datetime import timedelta
from typing import Any, Generic, TypeVar

from ._chunking import ChunkSpec
from ._logging import get_logger
from .config import DimensionValidation
from .exceptions import QueryError, UnknownDimensionError
from .period import Period
from .reports.query import Dimension, QueryMessageV2
from .reports.result import ReportResult, ResultMeta
from .reports.runner import ReportRunner

T = TypeVar("T")

_log = get_logger("query")

RowDecoder = Callable[[dict[str, Any]], T]


class ReportQuery(Generic[T]):
    """A lazy, awaitable, async-iterable handle on one report retrieval."""

    def __init__(
        self,
        *,
        runner: ReportRunner,
        decode: RowDecoder[T],
        query: QueryMessageV2 | None = None,
        period: Period | None = None,
        chunk: ChunkSpec | None = None,
        dedupe_on: str | None = None,
        saved_hash: str | None = None,
        identity_dimension: str | None = None,
        allow_unordered: bool = False,
        validate_dimensions: DimensionValidation = "off",
    ) -> None:
        self._runner = runner
        self._decode = decode
        self._query = query
        self._period = period
        self._chunk = chunk
        self._dedupe_on = dedupe_on
        self._saved_hash = saved_hash
        self._identity_dimension = identity_dimension
        self._allow_unordered = allow_unordered
        self._validate_dimensions = validate_dimensions
        self._meta = ResultMeta()
        self._consumptions = 0

    # -- introspection ------------------------------------------------------ #
    @property
    def meta(self) -> ResultMeta:
        """Result metadata, populated on first fetch."""
        return self._meta

    # -- consumption -------------------------------------------------------- #
    def __aiter__(self) -> AsyncIterator[T]:
        return self._stream()

    def __await__(self) -> Generator[Any, None, list[T]]:
        return self._collect().__await__()

    async def all(self, *, max_rows: int | None = None) -> list[T]:
        """Materialise to a list. ``await query`` is the idiomatic spelling."""
        return await self._collect(max_rows=max_rows)

    async def first(self) -> T | None:
        """The first row, or ``None``. Stops the stream after one row."""
        async for row in self:
            return row
        return None

    async def count(self) -> int:
        """The server-side ``recordCount`` (a full execution with one dimension)."""
        if self._saved_hash is not None:
            result = await self._runner.run_saved(self._saved_hash)
            return result.meta.record_count or 0
        identity = self._identity_dimension or self._first_dimension_id()
        if identity is None:
            raise QueryError(
                "count() needs at least one dimension to identify rows; none was set."
            )
        base = self._require_query()
        counting = base.model_copy(
            update={
                "dimensions": [Dimension(identity)],
                "comparative_dimensions": [],
            }
        )
        counting = self._stamp(counting, self._period)
        result = await self._runner.run(counting)
        return result.meta.record_count or 0

    def to_records(self) -> "ReportQuery[dict[str, Any]]":
        """A twin query that yields raw ``{dimension_id: cell}`` dicts, bypassing models."""
        return ReportQuery(
            runner=self._runner,
            decode=lambda record: record,
            query=self._query,
            period=self._period,
            chunk=self._chunk,
            dedupe_on=self._dedupe_on,
            saved_hash=self._saved_hash,
            identity_dimension=self._identity_dimension,
            allow_unordered=self._allow_unordered,
            validate_dimensions=self._validate_dimensions,
        )

    # -- immutable refinement ---------------------------------------------- #
    def with_period(self, period: Period) -> "ReportQuery[T]":
        return self._clone(period=period)

    def with_chunk(
        self, chunk: timedelta | int | str | ChunkSpec | None
    ) -> "ReportQuery[T]":
        spec = ChunkSpec.parse(chunk)
        if (
            spec is not None
            and not self._allow_unordered
            and self._query is not None
            and any(d.order is not None for d in self._query.dimensions)
        ):
            raise QueryError(
                "chunk= breaks global ordering (each window is sorted independently). "
                "Drop the sort, or build the query with allow_unordered=True before "
                "chunking."
            )
        return self._clone(chunk=spec)

    def with_dedupe(self, dimension_id: str) -> "ReportQuery[T]":
        return self._clone(dedupe_on=dimension_id)

    # -- internals ---------------------------------------------------------- #
    async def _collect(self, *, max_rows: int | None = None) -> list[T]:
        out: list[T] = []
        async for row in self:
            out.append(row)
            if max_rows is not None and len(out) >= max_rows:
                break
        return out

    async def _stream(self) -> AsyncIterator[T]:
        self._consumptions += 1
        if self._consumptions > 1:
            _log.debug("re-running ReportQuery (consumption #%d)", self._consumptions)
        self._meta = ResultMeta()
        dedupe_on = self._dedupe_on
        seen: set[Any] | None = set() if dedupe_on is not None else None
        for i, window in enumerate(self._windows()):
            result = await self._run(window)
            self._absorb_meta(result)
            if i == 0:
                self._validate_returned_dimensions(result)
            for record in result.iter_records():
                if seen is not None and dedupe_on is not None:
                    key = record.get(dedupe_on)
                    if key in seen:
                        continue
                    seen.add(key)
                yield self._decode(record)
            self._meta.completed_windows = i + 1

    def _validate_returned_dimensions(self, result: ReportResult) -> None:
        """Flag requested dimensions the server silently dropped (plan.md §4.4).

        The Reporting Service omits any dimension it does not recognise from the
        columnar result rather than erroring, so every value for that column would
        decode to ``None`` — silent data loss. Comparing the requested dimension
        ids against the columns actually returned turns that into a clear signal
        (``"warn"`` → :class:`UserWarning`; ``"error"`` →
        :class:`UnknownDimensionError`) at no extra request cost.
        """
        mode = self._validate_dimensions
        if mode == "off" or self._query is None:
            return
        returned = set(result.index)
        if not returned:
            # The server described no columns (an empty/zero-column envelope); we
            # cannot tell "unknown report" from "no data", so do not guess.
            return
        # Only literal requested dimensions are checked — server-derived
        # comparative columns carry computed ids that are validated by the server.
        missing = [
            d.dimension_id
            for d in self._query.dimensions
            if d.dimension_id not in returned
        ]
        if not missing:
            return
        report_id = self._query.report_id
        listed = ", ".join(missing)
        message = (
            f"The {report_id} report did not return {len(missing)} requested "
            f"dimension(s): {listed}. The server does not expose them on this "
            "version, so every value would be null (silent data loss). Run "
            "client.validate_catalogue() to see catalogue-vs-server drift."
        )
        if mode == "error":
            raise UnknownDimensionError(
                message, report_id=report_id, dimensions=missing
            )
        warnings.warn(message, stacklevel=2)

    def _windows(self) -> list[Period | None]:
        if self._saved_hash is not None or self._period is None:
            return [None]
        if self._chunk is not None:
            return list(self._chunk.windows(self._period))
        return [self._period]

    async def _run(self, window: Period | None) -> ReportResult:
        if self._saved_hash is not None:
            return await self._runner.run_saved(self._saved_hash)
        query = self._stamp(self._require_query(), window)
        return await self._runner.run(query)

    def _absorb_meta(self, result: ReportResult) -> None:
        meta = result.meta
        if self._meta.record_count is None:
            self._meta.record_count = meta.record_count
        elif meta.record_count is not None:
            self._meta.record_count += meta.record_count
        self._meta.report_duration_ms = meta.report_duration_ms
        self._meta.report_display_name = (
            self._meta.report_display_name or meta.report_display_name
        )
        self._meta.report_started = self._meta.report_started or meta.report_started
        self._meta.dimension_display_names.update(meta.dimension_display_names)
        if meta.oldest_cache_age is not None:
            current = self._meta.oldest_cache_age
            if current is None or meta.oldest_cache_age < current:
                self._meta.oldest_cache_age = meta.oldest_cache_age

    def _clone(self, **overrides: Any) -> "ReportQuery[T]":
        params: dict[str, Any] = {
            "runner": self._runner,
            "decode": self._decode,
            "query": self._query,
            "period": self._period,
            "chunk": self._chunk,
            "dedupe_on": self._dedupe_on,
            "saved_hash": self._saved_hash,
            "identity_dimension": self._identity_dimension,
            "allow_unordered": self._allow_unordered,
            "validate_dimensions": self._validate_dimensions,
        }
        params.update(overrides)
        return ReportQuery(**params)

    def _require_query(self) -> QueryMessageV2:
        if self._query is None:
            raise QueryError("This query has no QueryMessageV2 to execute.")
        return self._query

    def _first_dimension_id(self) -> str | None:
        if self._query is not None and self._query.dimensions:
            return self._query.dimensions[0].dimension_id
        return None

    @staticmethod
    def _stamp(query: QueryMessageV2, window: Period | None) -> QueryMessageV2:
        if window is None:
            return query
        return query.model_copy(update={"from_": window.start, "to": window.end})


__all__ = ["ReportQuery", "RowDecoder"]
