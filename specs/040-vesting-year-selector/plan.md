# Implementation Plan: Vesting Year Selector

**Branch**: `040-vesting-year-selector` | **Date**: 2026-02-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/040-vesting-year-selector/spec.md`

## Summary

Add a year selector dropdown to the Vesting Analysis page so users can choose which simulation year to analyze instead of being locked to the final year. The backend already supports an optional `simulation_year` parameter — this feature primarily adds a frontend dropdown, a new backend endpoint to list available years, and wires the selected year into the existing analysis request.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (backend API), React 18 + Vite (frontend), Pydantic v2 (validation), DuckDB 1.0.0 (storage)
**Storage**: DuckDB (`dbt/simulation.duckdb`) — read-only queries via `DatabasePathResolver`
**Testing**: pytest (backend), manual (frontend — no frontend test framework in project)
**Target Platform**: Linux server (API), modern browsers (frontend)
**Project Type**: Web application (frontend + backend)
**Performance Goals**: Year list endpoint responds in <500ms; no regression in existing analysis latency
**Constraints**: Read-only database access for year queries; single-threaded DuckDB connections
**Scale/Scope**: Typically 1-5 simulation years per scenario; 1 new API endpoint, 1 modified component, 1 modified API client

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No events created; read-only queries only |
| II. Modular Architecture | PASS | New endpoint in existing vesting router; no new modules needed |
| III. Test-First Development | PASS | Backend endpoint will have integration tests |
| IV. Enterprise Transparency | PASS | Selected year visible in results banner; no new audit needs |
| V. Type-Safe Configuration | PASS | Year uses existing Pydantic-validated `simulation_year` field |
| VI. Performance & Scalability | PASS | Lightweight `SELECT DISTINCT` query; <500ms target |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/040-vesting-year-selector/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api-contracts.md
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_api/
├── routers/
│   └── vesting.py              # Add GET years endpoint
└── services/
    └── vesting_service.py      # Add get_available_years() method

planalign_studio/
├── components/
│   └── VestingAnalysis.tsx     # Add year selector dropdown + state
└── services/
    └── api.ts                  # Add getScenarioYears() function

tests/
└── integration/
    └── test_vesting_api.py     # Add year list endpoint tests
```

**Structure Decision**: Web application structure. All changes fit within existing file locations — no new files needed except the API contract doc. The feature modifies 4 existing files and adds tests to 1 existing test file.
