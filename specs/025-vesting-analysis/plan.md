# Implementation Plan: Vesting Analysis

**Branch**: `025-vesting-analysis` | **Date**: 2026-01-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/025-vesting-analysis/spec.md`

## Summary

Add a Vesting Analysis feature to PlanAlign Studio that enables plan sponsors to compare current vs proposed vesting schedules and project forfeiture differences for terminated employees. This is a query-time projection tool that calculates vesting percentages and forfeitures based on existing simulation data without modifying the simulation engine.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (backend API), React 18 + Vite (frontend), Pydantic v2 (validation), Recharts (visualization)
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`) - read-only access to `fct_workforce_snapshot`
**Testing**: pytest (backend), vitest (frontend)
**Target Platform**: Web application (PlanAlign Studio)
**Project Type**: Web application (backend API + frontend SPA)
**Performance Goals**: Analysis completes in <5 seconds for 10,000 terminated employees; page-to-results in <30 seconds
**Constraints**: Read-only database access; no simulation modifications; single-threaded queries
**Scale/Scope**: Handles up to 10,000 terminated employees per analysis

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Feature is read-only projection; does not create or modify events |
| II. Modular Architecture | PASS | New router, service, and models follow existing patterns; each file <600 lines |
| III. Test-First Development | PASS | Unit tests for vesting calculation logic planned; follows existing test patterns |
| IV. Enterprise Transparency | PASS | Analysis results include employee-level detail for audit; tenure band breakdowns |
| V. Type-Safe Configuration | PASS | All models use Pydantic v2; vesting schedules are type-safe enums |
| VI. Performance & Scalability | PASS | Targets <5s for 10k employees; uses existing DatabasePathResolver pattern |

**Database Access Patterns**: Uses `DatabasePathResolver` from existing analytics service pattern; read-only DuckDB connections with explicit close.

## Project Structure

### Documentation (this feature)

```text
specs/025-vesting-analysis/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI spec)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_api/
├── models/
│   └── vesting.py           # NEW: Pydantic models for vesting analysis
├── services/
│   └── vesting_service.py   # NEW: Vesting calculation and query logic
├── routers/
│   └── vesting.py           # NEW: FastAPI endpoints
└── main.py                  # MODIFY: Register vesting router

planalign_studio/
├── services/
│   └── api.ts               # MODIFY: Add vesting types and API functions
├── components/
│   └── VestingAnalysis.tsx  # NEW: React component
├── App.tsx                  # MODIFY: Add route
└── components/
    └── Layout.tsx           # MODIFY: Add navigation link

tests/
├── unit/
│   └── test_vesting_service.py  # NEW: Unit tests for vesting calculations
└── integration/
    └── test_vesting_api.py      # NEW: API integration tests
```

**Structure Decision**: Follows existing web application pattern with backend API in `planalign_api/` and React frontend in `planalign_studio/`. New feature adds 3 backend files and 1 frontend component, modifying 4 existing files for integration.

## Complexity Tracking

No constitution violations to justify.
