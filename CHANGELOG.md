# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial implementation of the async Dayshape Reporting Service SDK (plan.md Rev 3).
  - `DayshapeClient` with resource façades (`workers`, `jobs`, `bookings`, …),
    `audit`/`timeseries` namespaces, and the raw `reports` escape hatch.
  - Single lazy `ReportQuery[T]` consumption contract (awaitable + async-iterable).
  - `Period` value object with client-level scoping (`client.period(...)`).
  - Typed identifiers: `Sort` enum, generated `dayshape.dims` constants, typed filters.
  - Single-flight token refresh, per-client rate-limit gate, explicit date-window chunking.
  - Generated dimension catalogue via `scripts/generate_dims.py` (CI drift-checked).
