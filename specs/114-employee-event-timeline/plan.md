# Implementation Plan: Employee Event Timeline (Storyline) View

**Branch**: `114-employee-event-timeline` | **Date**: 2026-07-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/114-employee-event-timeline/spec.md`

## Summary

Add a read-only "Employee Timeline" page to PlanAlign Studio: find an employee within a scenario (ID autocomplete or attribute filter), render their full event history from `fct_yearly_events` merged with `fct_employer_match_events` as a year-grouped vertical timeline, show a per-year state strip from `fct_workforce_snapshot`, and optionally place the same employee's timeline from a second scenario side by side. Backend is a new FastAPI router + service following the existing workspace-scoped pattern (`WorkspaceStorage` + `DatabasePathResolver`, read-only DuckDB queries). Frontend is a new React route (`/timeline/...`) using HashRouter paths for shareable deep links. No schema changes, no writes, no new tables.

## Technical Context

**Language/Version**: Python 3.11 (API service/router), TypeScript/React (Studio UI)
**Primary Dependencies**: FastAPI + Pydantic v2 (existing `planalign_api`), duckdb Python client (read-only connections), React 18 + react-router-dom (HashRouter) + Tailwind CSS v4 (existing `planalign_studio`)
**Storage**: DuckDB — reads `fct_yearly_events`, `fct_employer_match_events`, `fct_workforce_snapshot` from per-scenario databases resolved via `DatabasePathResolver`. No new tables, no writes.
**Testing**: pytest (`-m fast` unit tests for the service with fixture DBs; integration tests against an isolated `DATABASE_PATH` DB per §8 of CLAUDE.md). Frontend verified via the running Studio app.
**Target Platform**: PlanAlign Studio (local FastAPI on 127.0.0.1:8000 + Vite frontend), on-prem analytics servers
**Project Type**: Web application (existing backend `planalign_api/` + frontend `planalign_studio/`)
**Performance Goals**: First page (one simulation year) renders < 3s (SC-004); autocomplete responses feel instant (< 500ms); dashboard-query constitution bound < 2s p95 applies to the per-year queries
**Constraints**: Strictly read-only (`duckdb.connect(..., read_only=True)`); never hold connections across requests; per-year pagination bounds result size; works against 100K-employee scenario databases
**Scale/Scope**: 1 new router + 1 new service (backend), 1 new page component + small subcomponents (frontend), ~4 API endpoints' worth of surface expressed as 2 endpoints, no schema/dbt changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ PASS | Feature is a pure read over the immutable event store; FR-012 forbids any mutation surface. Reinforces the principle by making the audit trail visible. |
| II. Modular Architecture | ✅ PASS | One new service module (`timeline_service.py`, target < 600 lines, ≤ 8 public methods) + one new router; no cross-layer reads (API reads marts only, as every existing service does). |
| III. Test-First Development | ✅ PASS | Service unit tests written against fixture DuckDB databases before implementation; integration test seeds a known employee history and asserts endpoint payloads. |
| IV. Enterprise Transparency | ✅ PASS | Read-only; standard API logging applies. The feature itself is a transparency tool (audit reconstruction per employee). |
| V. Type-Safe Configuration | ✅ PASS | All request/response models are Pydantic v2; queries use parameter binding (no string concatenation of user input — employee_id, years, filters all bound). |
| VI. Performance & Scalability | ✅ PASS | Per-year pagination; indexed-by-nature columnar scans filtered on `employee_id` + `simulation_year`; read_only connections opened per request and closed promptly. |

**Post-design re-check (after Phase 1)**: All gates still pass. No violations to justify; Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/114-employee-event-timeline/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── timeline-api.md  # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
planalign_api/
├── routers/
│   └── timeline.py            # NEW: employee search/filter + timeline endpoints
├── services/
│   └── timeline_service.py    # NEW: read-only DuckDB queries, merge + pagination logic
├── models/
│   └── timeline.py            # NEW: Pydantic v2 request/response models
└── main.py                    # MODIFIED: include_router(timeline_router, prefix="/api/workspaces")

planalign_studio/
├── App.tsx                    # MODIFIED: add /timeline routes
├── components/
│   └── timeline/              # NEW directory
│       ├── EmployeeTimelinePage.tsx   # Page: search box, filters, timeline, compare picker
│       ├── EmployeeSearch.tsx         # ID autocomplete + attribute filter list (US1/US4)
│       ├── TimelineYear.tsx           # One year's events + state strip (US1/US2)
│       └── TimelineColumn.tsx         # A single scenario's timeline column (reused 2x in compare, US5)
└── services/
    └── api.ts                 # MODIFIED: timeline API client functions + interfaces

tests/
├── test_timeline_service.py       # NEW: fast unit tests (fixture DBs)
└── test_timeline_api.py           # NEW: router/integration tests (isolated DATABASE_PATH DB)
```

**Structure Decision**: Web application layout using the two existing top-level packages. Backend follows the exact pattern of `analytics.py`/`winners_losers_service.py` (workspace-scoped router → service → `DatabasePathResolver` → read-only duckdb). Frontend follows the existing component-per-page pattern with a `timeline/` subdirectory (precedent: `components/config`, `components/imports`).

## Complexity Tracking

No constitution violations — table intentionally empty.
