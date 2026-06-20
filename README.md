# dayshape-python-sdk

A typed, fully-async Python SDK for the **Dayshape Reporting Service API (v2.0)**.

Built on `httpx` + Pydantic v2. The Reporting Service is a report-execution API:
one logical "run report" operation across 42 reports. This SDK wraps it as a
typed core with resource façades (`client.workers`, `client.jobs`,
`client.bookings`, …) and a raw escape hatch (`client.reports`).

## Install

```bash
pip install dayshape-python-sdk
```

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

## Authentication

`POST /token` exchanges `{username, password}` for a JWT (returned as plain
text). The SDK manages acquisition, expiry (via the JWT `exp` claim, with a TTL
fallback), and single-flight refresh on `401`. Bad credentials surface as
`AuthenticationError`.

## Status

Beta. Wire contracts are taken verbatim from the v2 OpenAPI specification and the
March 2025 API documentation; identifier catalogues from the Reporting Service
Detail workbook (v26.3.0). Residual assumptions are tracked in `plan.md` §11.2.
Where the live v26.3 server's `/v2/metadata` disagrees with the workbook (a few
dimensions were renamed/removed server-side without a workbook update), the typed
models follow the live server.
