# dayshape-python-sdk

A typed, fully-async Python SDK for the **Dayshape Reporting Service API (v2.0)**.

Built on `httpx` + Pydantic v2. The Reporting Service is a report-execution API:
one logical "run report" operation across 38 reports. This SDK wraps it as a
typed core with resource façades (`client.workers`, `client.jobs`,
`client.bookings`, …) and a raw escape hatch (`client.reports`).

## Install

```bash
pip install dayshape-python-sdk
```

For reproducible installs, pin to a released tag (or a specific commit) — the
`v0.1` tag predates the live-server fixes, so pin to `v0.2.0` or later:

```bash
pip install "dayshape-python-sdk @ git+https://github.com/Grant-Thornton-Advisors-NL/dayshape-python-sdk@v0.2.0"
```

`pip install --upgrade` is a no-op when the version is unchanged; the SDK now
bumps `__version__` on every shipped change so upgrades take effect without
`--force-reinstall`.

## Quick start

```python
import asyncio
from dayshape import DayshapeClient, Period
from dayshape.dims import TaskDim


async def main() -> None:
    # Credentials via DAYSHAPE_BASE_URL / DAYSHAPE_USERNAME / DAYSHAPE_PASSWORD,
    # or pass them to DayshapeClient(...).
    async with DayshapeClient() as client:
        with client.period(Period.fiscal_year(2026)) as c:
            # Two ways to consume *any* multi-row retrieval:
            async for booking in c.bookings.list(dimensions=[TaskDim.ID, TaskDim.START]):
                print(booking.id, booking.start)

            # ...or materialise to a list:
            bookings = await c.bookings.list(dimensions=[TaskDim.ID])
            print(f"{len(bookings)} bookings")


asyncio.run(main())
```

## Core ideas

- **One consumption contract.** Every multi-row retrieval returns a lazy
  `ReportQuery[T]`. `async for q` streams rows; `await q` materialises a list.
  Constructing a query does no I/O — the request fires on first consumption.
- **`Period` + scoping.** The API's mandatory `from`/`to` is supplied once via a
  `Period`, bound to the client with `client.period(...)`, or per-call with
  `period=`. Resolution order: *call > model's originating scope > scoped client*.
- **Typed identifiers.** `dayshape.dims` provides autocompleting dimension
  constants (`TaskDim.ID`), `Sort.ASC/DESC` for ordering, and typed filter
  builders. Raw strings remain accepted everywhere.
- **No hidden I/O, no implicit caching.** Network calls happen at explicit
  `await`/`async for` points. Awaiting a query twice runs it twice.
- **No pagination** (by vendor statement). Slice with narrower filters and date
  windows; opt into explicit `chunk=` date-windowing for large ranges.
- **Catalogue-drift guardrails.** The dimension catalogue is pinned to a workbook
  version, but the live server may run a newer one. If the server silently drops a
  requested dimension (every value would be `None`), the SDK warns by default —
  set `validate_dimensions="error"` to raise `UnknownDimensionError`, or `"off"`
  to opt out. `await client.validate_catalogue()` diffs the SDK's default
  dimensions against each report's live `/v2/metadata` and pairs with
  `server_versions()`.

### Over-time (timeseries) reports

The `client.timeseries.*` pivot reports return **one row per identity per time
bucket** — e.g. `availability()` yields ~22 rows per worker over a three-week
window (one per day), scaling with the window. Treating one row as one worker
over-counts. To collapse to one row per identity pass
`dedupe_on=AvailabilityDim.WORKER_NAME` (keeps the first row per key); to sum a
column across buckets, aggregate the streamed rows yourself. For utilisation
specifically, `await client.timeseries.utilisation_rate()` computes it per worker
from the Availability report's hours (`ScheduledTaskHours / WorkHours`) — the live
`Utilisation` report may not expose the figure. Note the hours trap:
`AvailableHours = WorkHours − ScheduledTaskHours` is *free time*, not capacity, so
it is never the denominator.

## Authentication

`POST /token` exchanges `{username, password}` for a JWT (returned as plain
text). The SDK manages acquisition, expiry (via the JWT `exp` claim, with a TTL
fallback), and single-flight refresh on `401`. Bad credentials surface as
`AuthenticationError`.

## Status

Beta. Wire contracts are taken verbatim from the v2 OpenAPI specification and the
March 2025 API documentation; identifier catalogues from the Reporting Service
Detail workbook (v25.7.0.0). Residual assumptions are tracked in `plan.md` §11.2.
