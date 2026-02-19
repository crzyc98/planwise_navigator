# Implementation Plan: NDT ACP Testing

**Branch**: `050-ndt-acp-testing` | **Date**: 2026-02-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/050-ndt-acp-testing/spec.md`

## Summary

Add IRS ACP non-discrimination testing to PlanAlign Studio. The feature classifies employees as HCE/NHCE based on prior-year compensation, computes per-employee ACP from employer matching contributions, applies both IRS test methods (basic 1.25x and alternative lesser-of 2x/+2%), and displays pass/fail results with optional per-employee drill-down. All computation is performed at query time against completed simulation data — no new dbt models needed.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (API), React 18 + Vite (frontend), DuckDB 1.0.0 (analytics queries), Pydantic v2 (validation)
**Storage**: DuckDB (read-only queries against per-scenario `simulation.duckdb` via `DatabasePathResolver`)
**Testing**: pytest (backend service tests), manual UI testing
**Target Platform**: Linux server (API), modern web browser (frontend)
**Project Type**: Web application (backend + frontend)
**Performance Goals**: ACP test results returned within 5 seconds for a single scenario
**Constraints**: Read-only analytics — no writes to simulation database; no circular dbt dependencies
**Scale/Scope**: Supports 100K+ employee datasets; up to 6 simultaneous scenario comparisons

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Read-only analytics; no events created or modified |
| II. Modular Architecture | PASS | New router + service modules, each <600 lines; single-responsibility |
| III. Test-First Development | PASS | Service layer testable with mock DB; pytest fixtures available |
| IV. Enterprise Transparency | PASS | All test parameters and thresholds shown in results; HCE determination auditable |
| V. Type-Safe Configuration | PASS | Pydantic v2 response models; IRS limits from validated seed data |
| VI. Performance & Scalability | PASS | DuckDB analytical queries optimized for columnar scans; read-only connection |

**Post-Phase 1 Re-check**: PASS — No dbt intermediate models means no circular dependency risk. All computation in service layer with typed Pydantic responses.

## Project Structure

### Documentation (this feature)

```text
specs/050-ndt-acp-testing/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research findings
├── data-model.md        # Data model documentation
├── quickstart.md        # Developer quickstart guide
├── contracts/           # API contracts
│   └── ndt-api.yaml     # OpenAPI 3.0 specification
├── checklists/          # Quality checklists
│   └── requirements.md  # Specification quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
# Backend (Python/FastAPI)
planalign_api/
├── routers/
│   └── ndt.py                    # NEW: NDT testing router
├── services/
│   └── ndt_service.py            # NEW: NDT business logic + DuckDB queries
└── main.py                       # MODIFIED: register NDT router

# Frontend (React/TypeScript)
planalign_studio/
├── components/
│   ├── NDTTesting.tsx            # NEW: Main NDT testing page
│   ├── Layout.tsx                # MODIFIED: add NDT nav item
│   └── App.tsx                   # MODIFIED: add NDT route (if in App.tsx)
└── services/
    └── api.ts                    # MODIFIED: add NDT API functions

# Data (dbt seeds)
dbt/
└── seeds/
    └── config_irs_limits.csv     # MODIFIED: add hce_compensation_threshold column

# Tests
tests/
└── test_ndt_service.py           # NEW: NDT service unit tests
```

**Structure Decision**: Web application pattern — backend API service + frontend page. No new dbt models (avoids circular dependency). All NDT computation in the API service layer as DuckDB analytical queries.

## Complexity Tracking

No constitution violations. All principles satisfied without exceptions.

## Phase 0: Research Summary

All research documented in [research.md](./research.md). Key decisions:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ACP formula | Employer match only (MVP) | Standard IRS definition; after-tax not modeled yet |
| Test population | All plan-eligible employees | IRS requirement; non-participants at 0% ACP |
| Alternative test | Lesser of (NHCE x 2, NHCE + 2%) | Full IRS formula per Treas. Reg. 1.401(m)-2 |
| HCE determination | API query, not dbt model | Avoids circular int→fct dependency |
| IRS thresholds | Extend config_irs_limits.csv | Keeps all IRS limits centralized |
| API pattern | GET with query params | Matches existing analytics endpoint patterns |
| Frontend pattern | DCPlanAnalytics + VestingAnalysis hybrid | Scenario multi-select + year dropdown + explicit run button |

## Phase 1: Design Summary

### Data Model

Documented in [data-model.md](./data-model.md). Key entities:

1. **IRS Limits Seed** — Extended with `hce_compensation_threshold` column
2. **HCE Determination** — Computed at query time (prior-year comp vs IRS threshold)
3. **Per-Employee ACP** — Computed at query time (match / compensation)
4. **ACP Test Result** — Aggregated pass/fail with both test methods
5. **Per-Employee Detail** — Optional drill-down in API response

All entities are computed, not persisted. Read-only analytics.

### API Contracts

Documented in [contracts/ndt-api.yaml](./contracts/ndt-api.yaml). Two endpoints:

1. `GET /api/workspaces/{workspace_id}/analytics/ndt/acp` — Run ACP test
   - Query params: `scenarios` (comma-separated), `year`, `include_employees` (optional)
   - Returns: `ACPTestResponse` with per-scenario results

2. `GET /api/workspaces/{workspace_id}/analytics/ndt/available-years` — Get available years
   - Query params: `scenario_id`
   - Returns: `AvailableYearsResponse` with year list and default

### Implementation Approach

**Backend flow**:
1. Router validates workspace/scenario existence and completion status
2. Service resolves database path via `DatabasePathResolver`
3. Service executes analytical DuckDB query: HCE determination → ACP calculation → aggregation → test logic
4. Service returns typed Pydantic response

**Frontend flow**:
1. User selects test type (ACP), year, and scenario(s)
2. "Run Test" button triggers API call
3. Results displayed: pass/fail card → aggregate stats → expandable per-employee table
4. Multi-scenario mode shows side-by-side comparison cards

**SQL approach**: Single CTE-based analytical query per scenario (see quickstart.md for full query). No temporary tables or materialized views.
