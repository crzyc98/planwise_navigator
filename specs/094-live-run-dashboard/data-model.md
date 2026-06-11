# Data Model: Live Simulation Run Dashboard

**Feature**: 094-live-run-dashboard | **Date**: 2026-06-10

All entities are in-memory (Pydantic v2 models in `planalign_api/models/simulation.py`, mirrored as TypeScript interfaces in `planalign_studio/services/api.ts`). No DuckDB schema changes. The orchestrator-side telemetry record is a plain dict serialized to the stdout protocol (see contracts/telemetry-stdout-protocol.md).

## TelemetryMilestone

A timestamped record of a significant run occurrence (spec: Milestone Entry).

| Field | Type | Notes |
|-------|------|-------|
| sequence | int | Monotonic per run; client dedup/order key |
| timestamp | datetime (UTC) | When the milestone occurred |
| kind | Literal["run_started", "stage_started", "stage_completed", "year_completed", "warning", "error", "terminal"] | Discriminator |
| severity | Literal["info", "warning", "error"] | Drives feed styling (FR-005) |
| year | int \| None | Simulation year, when applicable |
| stage | str \| None | Workflow stage name, when applicable |
| message | str | Human-readable feed text |
| detail | dict \| None | Structured payload (e.g., year counts + duration for `year_completed`) |

Validation: `sequence ≥ 1`; `year_completed` requires `detail.event_counts` and `detail.duration_seconds`. Cap: 200 per run (oldest dropped; warnings rate-limited to ~20/run).

## EventTypeCounts

Cumulative and per-year event counts (spec: Live Event Statistics). Exact at year boundaries only (clarification 2026-06-10).

| Field | Type | Notes |
|-------|------|-------|
| by_type | dict[str, int] | Keys: HIRE, TERMINATION, PROMOTION, RAISE, ENROLLMENT (+ any registered event type) |
| by_year | dict[int, dict[str, int]] | year → type → count |
| total | int | Sum of by_type |
| as_of_year | int \| None | Last fully counted year (None until first year closes) |

Source: emitter's year-boundary query against `fct_yearly_events` (orchestrator's own connection). FR-011: final values must equal persisted aggregates.

## PerformanceSample

One point for the trend chart (spec: Performance Sample).

| Field | Type | Notes |
|-------|------|-------|
| timestamp | datetime (UTC) | |
| elapsed_seconds | float | |
| events_per_second | float | |
| memory_mb | float | |

Cap: ring buffer of 600 per run server-side; client downsamples beyond 600.

## RunTelemetrySnapshot

The full restorable state of a run — sent as the WS `snapshot` message body and as the REST endpoint response (FR-009/FR-013/FR-014). Extends today's `SimulationTelemetry` (which stays for incremental updates).

| Field | Type | Notes |
|-------|------|-------|
| run_id | str | |
| scenario_id | str | |
| status | Literal["pending", "running", "completed", "failed", "cancelled"] | Terminal states retained in memory (FR-015) |
| progress | int (0–100) | |
| current_stage | str | |
| current_year | int | |
| total_years | int | |
| start_year | int | Enables "Year N of M" rendering |
| performance_metrics | PerformanceMetrics (existing model) | Instantaneous values |
| event_counts | EventTypeCounts | |
| milestones | list[TelemetryMilestone] | Full history, ordered by sequence |
| performance_samples | list[PerformanceSample] | Ring buffer contents |
| last_update_at | datetime (UTC) | Staleness computation input (FR-008) |

## WebSocket message envelope

Discriminated union on `type` (contracts/websocket-messages.md):

- `snapshot` → `{ type, data: RunTelemetrySnapshot }` — sent once per (re)connect
- `update` → `{ type, data: SimulationTelemetry-shaped delta + event_counts }` — throttled live updates
- `milestone` → `{ type, data: TelemetryMilestone }` — appended feed entries
- `heartbeat` → `{ type }` — existing 30s keepalive (unchanged)

## RunTelemetryState (server-side container, not serialized)

Internal `TelemetryService` bookkeeping per run: snapshot fields above + listener queue set + warning rate-limit counters. Lifecycle/state transitions:

```
(run start)         pending → running
(structured records) running → running   [stage/year/sample/milestone accumulation]
(process exit 0)    running → completed  [terminal milestone + final counts]
(process exit ≠0)   running → failed     [terminal milestone, error message]
(user cancel)       running → cancelled  [terminal milestone]
(new run, same scenario) any terminal → state discarded, fresh state created
(API restart)       all state lost — accepted per clarification
```

Invariants:
- Terminal states are never cleared by run completion itself (fixes "stuck on running").
- `sequence` strictly increasing within a run; snapshot + subsequent deltas never regress.
- All datetimes UTC (`timezone.utc`), serialized ISO-8601.

## Frontend connection state machine (useRunTelemetry)

```
idle → connecting → live ⇄ stale → reconnecting → polling → live (on WS recovery)
any state → terminal (status from snapshot/update/poll is terminal)
```

- `stale`: no WS message (incl. heartbeat) for 15s while socket open (FR-008)
- `reconnecting`: socket closed unexpectedly; backoff 2s·2^n, n held in a ref, max 5 attempts (FR-012)
- `polling`: REST snapshot every 5s + WS upgrade retry every 30s (FR-014)
- `terminal`: freeze display, stop timers (FR-010, FR-015)
