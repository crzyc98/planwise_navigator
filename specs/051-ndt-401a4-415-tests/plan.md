# Implementation Plan: NDT 401(a)(4) & 415 Tests

**Branch**: `051-ndt-401a4-415-tests` | **Date**: 2026-02-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/051-ndt-401a4-415-tests/spec.md`

## Summary

Add two IRS compliance tests to the existing NDT suite: a **401(a)(4) general nondiscrimination test** (employer contribution rate fairness between HCE/NHCE groups) and a **415 annual additions limit test** (per-participant total contribution cap). Both tests extend the existing `NDTService` class, reuse the ACP test's data access and HCE determination patterns, and are exposed through new API endpoints following the same router conventions. A `annual_additions_limit` column is added to the `config_irs_limits` seed. The frontend `NDTTesting.tsx` component gains a test-type selector to support all three test types.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (API), Pydantic v2 (models), React 18 + Vite (frontend), DuckDB 1.0.0 (queries)
**Storage**: DuckDB (`dbt/simulation.duckdb`) — read-only queries via `DatabasePathResolver`
**Testing**: pytest (backend unit tests), manual verification (frontend)
**Target Platform**: Linux server (on-premises analytics)
**Project Type**: Web application (backend API + frontend)
**Performance Goals**: Same response time as existing ACP test (<2s for 100K employees)
**Constraints**: Read-only database access; single-threaded DuckDB queries; no schema changes to `fct_workforce_snapshot`
**Scale/Scope**: 100K+ employee datasets, up to 12 simulation years, multi-scenario comparison

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Read-only analytical queries; no events created or modified |
| II. Modular Architecture | PASS | New methods added to existing `NDTService`; no new modules exceed 600 lines |
| III. Test-First Development | PASS | Unit tests planned for both test calculations with hand-verified examples |
| IV. Enterprise Transparency | PASS | All test results include audit fields (thresholds used, applied test, margins) |
| V. Type-Safe Configuration | PASS | Pydantic v2 response models for all test results; IRS limits from validated seed |
| VI. Performance & Scalability | PASS | Single SQL query per test per scenario; <2s target for 100K employees |

**Post-Phase 1 Re-check**: All gates still pass. No circular dependencies introduced. Service method count stays within 6-8 public methods guideline (adding 2 methods: `run_401a4_test`, `run_415_test`).

## Project Structure

### Documentation (this feature)

```text
specs/051-ndt-401a4-415-tests/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: technical research
├── data-model.md        # Phase 1: response model schemas
├── quickstart.md        # Phase 1: usage examples
├── contracts/           # Phase 1: OpenAPI contract
│   └── ndt-401a4-415-api.yaml
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
# Modified files
dbt/seeds/config_irs_limits.csv                    # Add annual_additions_limit column
planalign_api/services/ndt_service.py              # Add 401a4 + 415 test methods + Pydantic models
planalign_api/routers/ndt.py                       # Add 2 new endpoints
planalign_studio/components/NDTTesting.tsx          # Add test-type selector + result views
planalign_studio/services/api.ts                   # Add 2 API client functions

# New files
tests/test_ndt_401a4.py                            # 401(a)(4) unit tests
tests/test_ndt_415.py                              # 415 unit tests
```

**Structure Decision**: Web application pattern — extends existing backend (`planalign_api/`) and frontend (`planalign_studio/`) packages. No new packages or modules created; all changes fit within existing module boundaries.

## Implementation Approach

### 1. Seed Data (config_irs_limits.csv)

Add `annual_additions_limit` column to `dbt/seeds/config_irs_limits.csv`:

| Year | Limit |
|------|-------|
| 2024 | 69000 |
| 2025 | 70000 |
| 2026 | 70000 |
| 2027-2035 | Projected (+$1K/yr) |

Update `_ensure_seed_current()` in `NDTService` to check for the new column and auto-reload if missing.

### 2. Backend — Pydantic Response Models

Add to `ndt_service.py` (following existing `ACPEmployeeDetail` / `ACPScenarioResult` pattern):

- `Section401a4EmployeeDetail` — per-participant contribution rate detail
- `Section401a4ScenarioResult` — scenario-level pass/fail with ratio, margin, service risk flag
- `Section401a4TestResponse` — wrapper with `test_type="401a4"`
- `Section415EmployeeDetail` — per-participant annual additions detail
- `Section415ScenarioResult` — scenario-level pass/fail with breach/at-risk counts
- `Section415TestResponse` — wrapper with `test_type="415"`

### 3. Backend — Service Methods

Add two methods to `NDTService`:

**`run_401a4_test()`** — Core logic:
1. Reuse HCE determination (same query pattern as ACP: prior-year comp vs threshold)
2. Query `fct_workforce_snapshot` joined with prior-year data
3. Calculate employer contribution rate: `(employer_core_amount + employer_match_amount if include_match) / prorated_annual_compensation`
4. Separate into HCE/NHCE groups, compute averages and medians
5. Apply ratio test (NHCE avg >= 70% of HCE avg)
6. If ratio fails, apply general test (NHCE median >= 70% of HCE median)
7. Detect service-based NEC risk: check config for `employer_core_status='graded_by_service'`, compute average tenure by group
8. Return `Section401a4ScenarioResult`

**`run_415_test()`** — Core logic:
1. Query `config_irs_limits` for `annual_additions_limit` and `base_limit` for the test year
2. Query `fct_workforce_snapshot` for eligible participants
3. Calculate base deferrals: `LEAST(prorated_annual_contributions, base_limit)` (excludes catch-up)
4. Calculate total annual additions: `base_deferrals + employer_match_amount + employer_core_amount`
5. Calculate applicable 415 limit: `LEAST(annual_additions_limit, current_compensation)` (uncapped gross)
6. Classify: breach (total > limit), at_risk (total >= threshold * limit), pass
7. Return `Section415ScenarioResult`

### 4. Backend — Router Endpoints

Add to `ndt.py`:

- `GET /{workspace_id}/analytics/ndt/401a4` — params: `scenarios`, `year`, `include_employees`, `include_match`
- `GET /{workspace_id}/analytics/ndt/415` — params: `scenarios`, `year`, `include_employees`, `warning_threshold`

Both follow the identical multi-scenario loop pattern as the existing ACP endpoint.

### 5. Frontend — API Client

Add to `planalign_studio/services/api.ts`:

- `run401a4Test(workspaceId, scenarioIds, year, includeEmployees, includeMatch)`
- `run415Test(workspaceId, scenarioIds, year, includeEmployees, warningThreshold)`
- TypeScript interfaces matching Pydantic response models

### 6. Frontend — UI Component

Extend `NDTTesting.tsx`:

- Add test-type selector (tabs or dropdown): ACP | 401(a)(4) | 415
- Conditional parameter controls per test type (include_match toggle for 401(a)(4), warning_threshold slider for 415)
- Result rendering specific to each test type:
  - 401(a)(4): ratio display, pass/fail badge, service risk warning, optional employee table
  - 415: breach/at-risk/pass counts, max utilization gauge, optional participant table
- Comparison mode works for all test types (reuses existing scenario selection)

### 7. Tests

**`tests/test_ndt_401a4.py`**:
- Ratio test pass (NHCE avg >= 70% of HCE avg)
- Ratio test fail → general test pass (median comparison)
- Ratio test fail → general test fail
- Service-based risk flag triggered
- NEC-only vs NEC+match modes
- Edge cases: all HCE, all NHCE, no employer contributions, zero comp excluded

**`tests/test_ndt_415.py`**:
- No breaches (all under limit)
- Breach detected (total > IRS limit)
- Breach detected (total > 100% of comp)
- At-risk flagging at default 95%
- Custom warning threshold
- Catch-up exclusion (total contributions capped at base_limit for deferral component)
- Edge cases: zero comp excluded, missing IRS limits year

## Complexity Tracking

> No constitution violations. All changes fit within existing module boundaries.

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| No new modules | Methods added to existing `NDTService` | Single-responsibility maintained — NDT service handles all non-discrimination tests |
| No schema changes to `fct_workforce_snapshot` | Derive catch-up exclusion at query time | Avoids touching critical mart model; `LEAST(contributions, base_limit)` is sufficient |
| Seed column addition only | `annual_additions_limit` added to existing CSV | Follows established IRS limits pattern; auto-reload handles backward compatibility |
