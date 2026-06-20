# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Upgraded the report/dimension catalogue from the Reporting Service Detail
  workbook **v25.7.0.0** to **v26.3.0** (`SPEC_VERSION["workbook"]`, regenerated
  `dims.py` + `reports/_catalogue.py`). The catalogue now covers **42 reports**
  (up from 38), and `dayshape.dims` gains the new v26.3 dimensions
  (e.g. `ApprovedBudgetGrossMargin`, `JobRateCardName`, `RateRoleName`,
  `TaskStatisticsTotalHours`, `TaskPhaseName`, `UnavailabilityMappingId`,
  `UserIsRemoteSyncEnabled`).
- Where the live v26.3 server's `/v2/metadata` diverges from the workbook, typed
  models continue to follow the live server (verified for the new reports too).

### Added

- Four new v26.3 reports, exposed idiomatically:
  - `client.audit.grades()` → `LogListingGrade`
  - `client.audit.suggestions()` → `LogListingSuggestion`
  - `client.audit.custom_members()` → `LogListingCustomMember`
  - `client.job_task_phases` → `JobTaskPhaseListing`, returning the new
    `JobTaskPhase` model (dimensions verified against live `/v2/metadata`).
  All four are also reachable as `ReportId` members and via the raw
  `client.reports` escape hatch.
- Initial implementation of the async Dayshape Reporting Service SDK (plan.md Rev 3).
  - `DayshapeClient` with resource façades (`workers`, `jobs`, `bookings`, …),
    `audit`/`timeseries` namespaces, and the raw `reports` escape hatch.
  - Single lazy `ReportQuery[T]` consumption contract (awaitable + async-iterable).
  - `Period` value object with client-level scoping (`client.period(...)`).
  - Typed identifiers: `Sort` enum, generated `dayshape.dims` constants, typed filters.
  - Single-flight token refresh, per-client rate-limit gate, explicit date-window chunking.
  - Generated dimension catalogue via `scripts/generate_dims.py` (CI drift-checked).
