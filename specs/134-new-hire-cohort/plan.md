# Implementation Plan: New-Hire Cohort Isolation for Cost Comparison

**Branch**: `134-new-hire-cohort` | **Date**: 2026-08-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/134-new-hire-cohort/spec.md` (GitHub issue #512)

## Summary

Add a `cohort` query parameter (`all` | `new_hires` | `baseline`) to the two DC Plan analytics endpoints, threaded through `AnalyticsService.get_dc_plan_analytics` into the two SQL-producing methods that back the Cost Comparison view's per-year cost, participation, and rate figures. A "new hire" is anyone whose `employee_hire_date` falls on/after that scenario's own `MIN(simulation_year)` (cross-checked, warning-only, against the `run_metadata` table). The React Cost Comparison view gets a segmented cohort control next to the existing Annual/Cumulative toggle, a persistent badge on cohort-filtered charts/tables, an updated methodology panel, cohort-aware TSV export, and cohort persisted in the existing localStorage prefs blob.

## Technical Context

**Language/Version**: Python 3.11 (API router/service); TypeScript/React (Studio UI)
**Primary Dependencies**: FastAPI + Pydantic v2 (`planalign_api`), `duckdb` Python client (read-only connections), React 18 + Tailwind CSS v4 + Recharts (`planalign_studio`)
**Storage**: DuckDB — reads only `fct_workforce_snapshot` and (for the warning-only cross-check) `run_metadata`, both already present in per-scenario `.duckdb` files resolved via `DatabasePathResolver`. No new tables, no writes.
**Testing**: pytest + Starlette `TestClient` (existing API contract-test pattern from feature 115); manual Studio verification per `quickstart.md`
**Target Platform**: Existing PlanAlign API (FastAPI, loopback-bound by default) + PlanAlign Studio (Vite/React)
**Project Type**: Web application (backend `planalign_api` + frontend `planalign_studio`, existing split)
**Performance Goals**: No new query pattern — cohort predicate is a single indexed-free `WHERE`/`AND` clause fragment added to queries that already scan `fct_workforce_snapshot` once; must not measurably regress the existing `<2s` (95th percentile) dashboard query goal (Constitution VI).
**Constraints**: `cohort=all` (the default and the only value used by existing callers) MUST be byte-identical to current behavior — this is both a functional requirement (FR-007) and the mechanism that keeps this a low-risk, additive change.
**Scale/Scope**: Two API endpoints, one service module, one Pydantic model, one TS API-client module, one React component. No dbt model changes, no new database tables, no migration.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Event Sourcing & Immutability | ✅ N/A for writes — this feature is entirely read-path (analytics query filtering). No event is created, modified, or reinterpreted; `fct_workforce_snapshot` and `fct_yearly_events` are unchanged. |
| II. Modular Architecture | ✅ Change is confined to `AnalyticsService` (already under 600 lines: 617 including this addition's ~2 new small helper methods and ~40 line diff — stays well under the module-size ceiling) and one router file. No new module needed; no circular dependency risk (`planalign_api` reads `fct_*` marts, doesn't touch staging/intermediate). |
| III. Test-First Development | ✅ Plan includes contract tests for both endpoints (valid cohort values, 422 on invalid, `all`-regression byte-identity, new_hires+baseline=all invariant) before/alongside implementation, per Phase 2 tasks. |
| IV. Enterprise Transparency | ✅ The `run_metadata` cross-check mismatch is logged with context (scenario/workspace ids, both year values) rather than silently resolved, satisfying the "log all security/config-drift-adjacent events" spirit already established by Feature 109. |
| V. Type-Safe Configuration | ✅ `cohort` is a Pydantic/FastAPI `Literal` at the API boundary — invalid values are rejected before reaching business logic, no raw string cohort values flow through the service layer. |
| VI. Performance & Scalability | ✅ No new full-table scan — the cohort predicate rides on the same `GROUP BY simulation_year` scan `_get_contribution_by_year` already performs; adds a `WHERE`/`AND` clause DuckDB evaluates during the same pass, not a second query per year. |

No violations. Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/134-new-hire-cohort/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   ├── api-contract.md   # Phase 1 output
│   └── ui-contract.md    # Phase 1 output
└── tasks.md              # Phase 2 output (/speckit.tasks — not created by this command)
```

### Source Code (repository root)

Existing web-application split (`planalign_api` backend + `planalign_studio` frontend) — no new top-level directories.

```text
planalign_api/
├── routers/
│   └── analytics.py                 # MODIFIED: add `cohort` Query param, 2 endpoints
├── services/
│   └── analytics_service.py         # MODIFIED: cohort predicate + first-year resolution
├── models/
│   └── analytics.py                 # MODIFIED: DCPlanAnalytics.resolved_first_simulation_year

planalign_studio/
├── services/
│   └── api.ts                       # MODIFIED: cohort param on getDCPlanAnalytics / compareDCPlanAnalytics
└── components/
    └── ScenarioCostComparison.tsx   # MODIFIED: cohort control, badge, methodology copy, TSV, prefs

tests/
├── test_analytics_service.py            # MODIFIED (exists): cohort predicate unit tests
└── api/
    └── test_dc_plan_analytics_contract.py   # NEW: contract tests, matches tests/api/test_*_contract.py convention (feature 115)
```

**Structure Decision**: No structural change — this feature adds parameters and fields to four existing files plus tests; it does not introduce new services, routers, or frontend modules. Kept intentionally minimal per the issue's own scoping ("same shape as the existing `active_only` flag and rides the same path").

## Complexity Tracking

*No Constitution Check violations — table not needed.*
