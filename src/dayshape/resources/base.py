"""Resource base classes and the client-view protocol (plan.md §6, §7.3).

A :class:`ResourceClient` turns ergonomic ``list`` / ``by_ids`` / ``search`` /
``get`` calls into a :class:`~dayshape._query.ReportQuery`. It resolves the
reporting period (call ``period=`` > the view's scope > :class:`QueryError`),
builds a :class:`~dayshape.reports.query.QueryMessageV2`, and wires a row decoder
that validates each row into the resource's model and binds it for relational
navigation.

``ClientView`` is the surface a resource needs from its owning client — both
:class:`~dayshape.client.DayshapeClient` and its scoped view satisfy it.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Protocol,
    TypeVar,
    cast,
)

from pydantic import ValidationError

from .._chunking import ChunkSpec
from .._query import ReportQuery, RowDecoder
from ..exceptions import QueryError, ResponseValidationError
from ..models.base import DayshapeModel
from ..period import Period
from ..reports.query import (
    ComparativeDimension,
    Dimension,
    Filter,
    QueryMessageV2,
    ReportFormattingOptions,
)
from ..reports.runner import ReportRunner

if TYPE_CHECKING:
    from ..client import DayshapeClient
    from ..config import DayshapeConfig

T = TypeVar("T", bound=DayshapeModel)

DimensionInput = "str | Dimension"


class ClientView(Protocol):
    """What a resource needs from its owning client or scoped view."""

    @property
    def _runner(self) -> ReportRunner: ...
    @property
    def _config(self) -> "DayshapeConfig": ...
    @property
    def _root(self) -> "DayshapeClient": ...
    @property
    def _formatting(self) -> ReportFormattingOptions: ...
    def _scope_period(self) -> Period | None: ...
    def _ensure_open(self) -> None: ...


def decode_row(
    model_cls: type[DayshapeModel],
    record: dict[str, Any],
    requested: frozenset[str],
    client: "DayshapeClient",
    period: Period | None,
    *,
    strict: bool,
    report_id: str | None = None,
) -> DayshapeModel:
    """Validate a ``{dimension_id: cell}`` record into a bound model row (§4.4)."""
    data = dict(record)
    data["requested_dimensions"] = requested
    try:
        obj = model_cls.model_validate(data)
    except ValidationError as exc:
        if strict:
            raise ResponseValidationError(
                f"A {model_cls.__name__} row failed validation: {exc}",
                report_id=report_id,
                row=record,
            ) from exc
        warnings.warn(
            f"{model_cls.__name__} row failed validation; returning a best-effort "
            f"row: {exc}",
            stacklevel=2,
        )
        obj = model_cls.model_construct(**data)
    obj._bind(client, period)
    return obj


class ResourceClient(Generic[T]):
    """Base for every entity resource (workers, jobs, bookings, …)."""

    #: The wire report id this resource runs (set by subclasses).
    report_id: ClassVar[str] = ""
    #: The model rows are decoded into (set by subclasses).
    model: ClassVar[type[DayshapeModel]] = DayshapeModel

    def __init__(
        self,
        view: ClientView,
        *,
        report_id: str | None = None,
        model: type[DayshapeModel] | None = None,
        default_dimensions: Sequence[str] | None = None,
    ) -> None:
        self._view = view
        self._report_id_override = report_id
        self._model_override = model
        self._default_dimensions_override = default_dimensions

    # -- report/model resolution (instance override > class attr) ----------- #
    def _report_id(self) -> str:
        return self._report_id_override or type(self).report_id

    def _model_cls(self) -> type[DayshapeModel]:
        return self._model_override or type(self).model

    def _default_dims(self) -> Sequence[str]:
        if self._default_dimensions_override is not None:
            return self._default_dimensions_override
        return self._model_cls().default_dimensions

    # -- period resolution -------------------------------------------------- #
    def _resolve_period(self, override: Period | None) -> Period:
        period = override if override is not None else self._view._scope_period()
        if period is None:
            raise QueryError(
                "No reporting period is set. Supply one of: a per-call period= "
                "(or start=/end=), a scoped client.period(...), or call within a "
                "Period-bound model relation."
            )
        return period

    # -- query construction ------------------------------------------------- #
    def _build(
        self,
        *,
        report_id: str | None = None,
        model: type[DayshapeModel] | None = None,
        period: Period | None,
        dimensions: Sequence[Any] | None,
        filters: Sequence[Filter],
        comparative_dimensions: Sequence[ComparativeDimension],
        sub_type: int | None,
        currency: str | None,
        formatting: ReportFormattingOptions | None,
        chunk: Any,
        allow_unordered: bool,
        dedupe_on: str | None,
    ) -> ReportQuery[T]:
        view = self._view
        view._ensure_open()
        resolved = self._resolve_period(period)
        resolved_report_id = report_id or self._report_id()
        model_cls = model or self._model_cls()
        raw_dims = dimensions if dimensions is not None else self._default_dims()
        dims = [Dimension.coerce(d) for d in raw_dims]
        comp = list(comparative_dimensions)
        chunk_spec = ChunkSpec.parse(chunk)
        if (
            chunk_spec is not None
            and not allow_unordered
            and any(d.order is not None for d in dims)
        ):
            raise QueryError(
                "chunk= breaks global ordering (each window is sorted independently). "
                "Drop the sort, or pass allow_unordered=True to accept window-local order."
            )
        query = QueryMessageV2(
            report_id=resolved_report_id,
            sub_type=sub_type,
            currency=currency if currency is not None else view._config.currency,
            instance_id=view._config.instance_id,
            from_=resolved.start,
            to=resolved.end,
            dimensions=dims,
            comparative_dimensions=comp,
            filters=list(filters),
            report_formatting_options=formatting or view._formatting,
        )
        requested = frozenset(d.dimension_id for d in dims) | {
            c.result_id for c in comp
        }
        decoder = self._make_decoder(model_cls, requested, resolved, resolved_report_id)
        identity = dims[0].dimension_id if dims else None
        return ReportQuery(
            runner=view._runner,
            decode=decoder,
            query=query,
            period=resolved,
            chunk=chunk_spec,
            dedupe_on=dedupe_on,
            identity_dimension=identity,
            allow_unordered=allow_unordered,
        )

    def _make_decoder(
        self,
        model_cls: type[DayshapeModel],
        requested: frozenset[str],
        period: Period,
        report_id: str,
    ) -> RowDecoder[T]:
        view = self._view
        strict = view._config.strict_models
        root = view._root

        def decode(record: dict[str, Any]) -> T:
            return cast(
                T,
                decode_row(
                    model_cls,
                    record,
                    requested,
                    root,
                    period,
                    strict=strict,
                    report_id=report_id,
                ),
            )

        return decode

    # -- entity-specific hooks (overridden by subclasses) ------------------- #
    def _id_filter(self, ids: Sequence[int]) -> Filter:
        raise QueryError(f"{type(self).__name__} does not support lookup by id.")

    def _text_filter(self, text: str) -> Filter:
        raise QueryError(f"{type(self).__name__} does not support text search.")

    # -- public API --------------------------------------------------------- #
    def list(
        self,
        *,
        period: Period | None = None,
        dimensions: Sequence[Any] | None = None,
        filters: Sequence[Filter] = (),
        comparative_dimensions: Sequence[ComparativeDimension] = (),
        chunk: Any = None,
        formatting: ReportFormattingOptions | None = None,
        sub_type: int | None = None,
        currency: str | None = None,
        allow_unordered: bool = False,
        dedupe_on: str | None = None,
    ) -> ReportQuery[T]:
        return self._build(
            period=period,
            dimensions=dimensions,
            filters=filters,
            comparative_dimensions=comparative_dimensions,
            sub_type=sub_type,
            currency=currency,
            formatting=formatting,
            chunk=chunk,
            allow_unordered=allow_unordered,
            dedupe_on=dedupe_on,
        )

    def by_ids(
        self,
        ids: Sequence[int],
        *,
        period: Period | None = None,
        dimensions: Sequence[Any] | None = None,
        filters: Sequence[Filter] = (),
        **kwargs: Any,
    ) -> ReportQuery[T]:
        merged = (self._id_filter(ids), *filters)
        return self.list(
            period=period, dimensions=dimensions, filters=merged, **kwargs
        )

    def search(
        self,
        text: str,
        *,
        period: Period | None = None,
        dimensions: Sequence[Any] | None = None,
        filters: Sequence[Filter] = (),
        **kwargs: Any,
    ) -> ReportQuery[T]:
        merged = (self._text_filter(text), *filters)
        return self.list(
            period=period, dimensions=dimensions, filters=merged, **kwargs
        )

    async def get(
        self,
        entity_id: int,
        *,
        period: Period | None = None,
        dimensions: Sequence[Any] | None = None,
    ) -> T | None:
        return await self.by_ids(
            [entity_id], period=period, dimensions=dimensions
        ).first()


__all__ = ["ClientView", "ResourceClient", "decode_row"]
