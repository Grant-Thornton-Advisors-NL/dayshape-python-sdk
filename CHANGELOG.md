# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-06-21

Integration-feedback hardening from running the SDK end-to-end against a live
v26.3 Reporting Service (GitHub issues #3–#10).

### Added

- **Dimension validation** (`validate_dimensions` client option, default `"warn"`).
  The server silently drops a requested dimension it does not recognise, so every
  value decodes to `None` — indistinguishable from a real null. The SDK now diffs
  requested dimensions against the columns actually returned and, by mode, warns
  (`"warn"`) or raises the new `UnknownDimensionError` (`"error"`); `"off"` keeps
  the old silent behaviour. No extra request. (#3)
- **`DayshapeClient.validate_catalogue()`** returning `CatalogueReport` /
  `ReportDrift`: diffs the dimensions the SDK's typed façades request by default
  against each report's live `/v2/metadata`, surfacing catalogue-vs-server drift
  per report. Pairs with `server_versions()`. (#4)
- **`timeseries.utilisation_rate()`** and the `WorkerUtilisation` result: computes
  utilisation per worker from the Availability report's hours
  (`ScheduledTaskHours / WorkHours`), since the live `Utilisation` report does not
  reliably expose the figure. (#7)
- **`Dim.id` / `Dim.name` / `Dim.value`** accessors for introspection and logging. (#9)

### Changed

- **`timeseries.report()` and its wrappers now forward** `dedupe_on`, `chunk`,
  `allow_unordered`, `comparative_dimensions`, `sub_type`, `currency`, and
  `formatting`. The dedup/window knobs that collapse the per-day rows are reachable
  from the convenience methods, not just the raw API. (#6)
- **`ReportMetadata.dimension_ids` is now a property** (was a method), so
  `set(md.dimension_ids)` and `"TaskId" in md.dimension_ids` work directly.
  *Breaking:* drop the parentheses at existing call sites. (#9)
- Documented the per-identity-per-time-bucket row granularity of the over-time
  reports (≈22 rows/worker for a 3-week window) and the hours semantics
  `AvailableHours = WorkHours − ScheduledTaskHours` (free time, not capacity). (#5, #7)

## [0.1.1] - 2026-06-20

### Fixed

- Live Reporting Service (v26.3) compatibility: always emit the
  `dimensions`/`comparativeDimensions`/`filters` arrays (the server `500`s when
  `filters` is omitted), tolerate novel `FilterType` tokens on `/v2/metadata`, map
  both `401` and `403` at `/token` to `AuthenticationError`, and honour
  `Retry-After`. (Shipped previously without a version bump — recorded here for
  release hygiene, see #8.)

## [0.1.0] - 2026-06-20

### Added

- Initial implementation of the async Dayshape Reporting Service SDK (plan.md Rev 3).
  - `DayshapeClient` with resource façades (`workers`, `jobs`, `bookings`, …),
    `audit`/`timeseries` namespaces, and the raw `reports` escape hatch.
  - Single lazy `ReportQuery[T]` consumption contract (awaitable + async-iterable).
  - `Period` value object with client-level scoping (`client.period(...)`).
  - Typed identifiers: `Sort` enum, generated `dayshape.dims` constants, typed filters.
  - Single-flight token refresh, per-client rate-limit gate, explicit date-window chunking.
  - Generated dimension catalogue via `scripts/generate_dims.py` (CI drift-checked).
