# Implementation Plan: Live Simulation Run Dashboard

**Branch**: `094-live-run-dashboard` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/094-live-run-dashboard/spec.md`

## Summary

Replace the run screen's raw per-employee "Event Stream" and the `[Real-time Performance Graph Placeholder]` with a live run dashboard (event counts by type, per-year progress, milestone activity feed, performance trend chart), and overhaul the unreliable WebSocket telemetry underneath it.

Technical approach: the current telemetry is regex-scraped from the `planalign simulate` subprocess stdout (`SimulationOutputParser` guesses stage/year/counts from log text), and the frontend hook has broken reconnect logic with no resync. The fix is a **structured telemetry channel**: orchestrator pipeline hooks emit single-line JSON records (sentinel-prefixed) on stdout at stage/year boundaries — including exact per-event-type counts queried in-process after each year's event generation — which the API parses deterministically, accumulates into a per-run `RunTelemetryState` (snapshot + milestone history + perf samples), and serves via (a) WebSocket with full-snapshot-on-connect and (b) a REST snapshot endpoint for polling fallback and refresh restore. The frontend hook is rewritten with correct backoff (refs, not stale state), snapshot/delta message handling, staleness detection, and automatic polling fallback.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator + FastAPI backend), TypeScript / React 18 (Vite frontend)
**Primary Dependencies**: FastAPI + Pydantic v2, asyncio (existing WS stack); Recharts 3.5.0 (already a frontend dep, used by feature 066), Tailwind CSS v4, Lucide icons
**Storage**: In-memory per-run telemetry state in the API process (per clarification, no persistence); DuckDB read only *in-process by the orchestrator* (its own connection) for year-boundary event counts — the API never opens the scenario DB mid-run
**Testing**: pytest (`-m fast` unit tests for parser/telemetry service/endpoint; fixtures from `tests/fixtures/`); frontend verified manually via quickstart (no existing React test harness — not adding one in this feature)
**Target Platform**: PlanAlign Studio (localhost web app: FastAPI :8000 + Vite :5173), corporate-firewall-friendly (no CDNs; WS may be blocked → polling fallback)
**Project Type**: Web application (backend + frontend) plus a small orchestrator emitter module
**Performance Goals**: Stats refresh ≤5s after each year boundary (SC-002); reconnect resync ≤10s after connectivity returns (SC-007); terminal state shown ≤30s in 100% of ended runs (SC-008); UI responsive for 10+ min runs (SC-006)
**Constraints**: No DB queries against the scenario DuckDB from the API while the simulation holds write locks; telemetry state in-memory only (lost on API restart — accepted per clarification); single active run at a time; event counts exact at year boundaries only (mid-year streaming out of scope)
**Scale/Scope**: 1 concurrent run, ≤~10 simulated years, ≤~50 milestones/run, ≤600 perf samples/run (capped ring buffer); 4 new frontend components, ~3 backend modules touched, 1 orchestrator emitter

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ Pass | Read-only consumer of `fct_yearly_events`; no event store changes. Counts derived from immutable events guarantee FR-011 (UI matches persisted results). |
| II. Modular Architecture | ✅ Pass | New code lands in focused modules (emitter, telemetry state, parser, hook, UI components); each well under 600 lines. `SimulationControl.tsx` (467 lines) is *split*, not grown. |
| III. Test-First Development | ✅ Pass | Structured-line parser, telemetry state accumulation, and snapshot endpoint get fast pytest units written first; deterministic JSON lines make the parser trivially testable (unlike the regex heuristics being replaced). |
| IV. Enterprise Transparency | ✅ Pass | Milestone feed *increases* run observability; structured telemetry lines also land in `simulation.log` for post-hoc audit. |
| V. Type-Safe Configuration | ✅ Pass | All new payloads are Pydantic v2 models (backend) with mirrored TS interfaces (frontend); discriminated `type` field on WS messages. |
| VI. Performance & Scalability | ✅ Pass | Telemetry emission is O(stage transitions), not O(events); in-process count query is one aggregate per year; bounded buffers prevent memory growth; no extra DB connections during runs. |

**Post-design re-check (after Phase 1)**: No violations introduced. No Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/094-live-run-dashboard/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── telemetry-stdout-protocol.md   # Orchestrator → API structured line format
│   ├── websocket-messages.md          # API → frontend WS message contract
│   └── rest-telemetry-snapshot.md     # Polling/restore REST endpoint
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── pipeline/
│   ├── telemetry_emitter.py        # NEW: structured JSON-line emitter (hook callbacks)
│   ├── hooks.py                    # EXISTING: HookManager (register emitter hooks)
│   └── year_executor.py            # EXISTING: reference for stage boundaries (no change expected)
└── pipeline_orchestrator.py        # MODIFIED: register telemetry hooks when env flag set

planalign_api/
├── models/
│   └── simulation.py               # MODIFIED: add Milestone, EventTypeCounts, PerformanceSample,
│                                   #           RunTelemetrySnapshot, WS message envelope models
├── services/
│   ├── telemetry_service.py        # MODIFIED: per-run state (milestones, counts, samples),
│   │                               #           snapshot-on-subscribe, terminal retention
│   └── simulation/
│       ├── output_parser.py        # MODIFIED: sentinel JSON fast path; regex kept as fallback
│       └── service.py              # MODIFIED: route parsed structured records into telemetry state;
│                                   #           guaranteed terminal telemetry on success/failure/cancel
├── websocket/
│   └── handlers.py                 # MODIFIED: send snapshot message on connect, then deltas
└── routers/
    └── simulations.py              # MODIFIED: GET .../run/telemetry snapshot endpoint;
                                    #           fix get_run_status to report real state

planalign_studio/
├── services/
│   ├── websocket.ts                # REWRITTEN: useRunTelemetry hook — correct backoff via refs,
│   │                               #           snapshot/delta handling, staleness, polling fallback
│   └── api.ts                      # MODIFIED: fetchRunTelemetrySnapshot(); updated TS types
└── components/
    ├── SimulationControl.tsx       # MODIFIED: slimmed to layout + controls; raw Event Stream removed
    └── simulation/
        ├── LiveStatsPanel.tsx      # NEW: event counts by type + per-year progress
        ├── ActivityFeed.tsx        # NEW: milestone feed (replaces Event Stream panel)
        ├── PerformanceTrendChart.tsx # NEW: Recharts throughput/memory trend (replaces placeholder)
        └── ConnectionStatusBadge.tsx # NEW: live / stale / degraded-polling indicator

tests/
├── test_telemetry_emitter.py       # NEW: fast — emitter output format, count query shape
├── test_output_parser_structured.py # NEW: fast — sentinel JSON parsing + regex fallback
├── test_telemetry_state.py         # NEW: fast — accumulation, snapshot replay, terminal retention
└── test_run_telemetry_endpoint.py  # NEW: fast — REST snapshot endpoint contract
```

**Structure Decision**: Follows the existing three-package layout (orchestrator / api / studio). The only cross-package surface is the stdout line protocol (contract #1), keeping the orchestrator free of any HTTP/WS knowledge and the API free of pipeline knowledge — matching how the subprocess boundary already works today.

## Complexity Tracking

No constitution violations — table not required.
