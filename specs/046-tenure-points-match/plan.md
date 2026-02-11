# Implementation Plan: Tenure-Based and Points-Based Employer Match Modes

**Branch**: `046-tenure-points-match` | **Date**: 2026-02-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/046-tenure-points-match/spec.md`

## Summary

Add two new employer match calculation modes — `tenure_based` and `points_based` — to the existing match formula system. The `tenure_based` mode determines match rates by employee years-of-service tiers (reusing existing macro infrastructure). The `points_based` mode introduces a new concept where points = FLOOR(age) + FLOOR(tenure), with match rates varying by configurable point thresholds. Both modes follow the same formula pattern as the existing `graded_by_service` mode: `tier_rate × min(deferral%, tier_max_deferral_pct) × capped_compensation`.

## Technical Context

**Language/Version**: Python 3.11 (backend), SQL/Jinja2 (dbt models), TypeScript 5.x (frontend)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Pydantic v2.7.4, FastAPI, React 18 + Vite
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`) — immutable event store
**Testing**: pytest (Python), dbt test (SQL), manual verification (dbt query)
**Target Platform**: Linux server / work laptop
**Project Type**: Web application (backend orchestrator + dbt pipeline + frontend studio)
**Performance Goals**: Match calculations complete within existing simulation time budget; no regression
**Constraints**: Single-threaded dbt execution (`--threads 1`); 100K+ employee capacity
**Scale/Scope**: 4 match modes total; ~3 dbt files modified/created; ~3 Python files modified; optional UI

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Event Sourcing & Immutability** | PASS | Match calculations produce output columns in `int_employee_match_calculations` (intermediate model). No modification to `fct_yearly_events`. Audit fields (`applied_points`, `applied_years_of_service`) ensure traceability. |
| **II. Modular Architecture** | PASS | New points macro in separate file (`get_points_based_match_rate.sql`). Tenure mode reuses existing macros. No circular dependencies — intermediate model reads from other intermediates only. Changes to `int_employee_match_calculations.sql` are additive Jinja branches. |
| **III. Test-First Development** | PASS | Plan includes dbt tests for tier assignment and match calculation correctness. Python unit tests for Pydantic validation. Regression tests for existing modes. |
| **IV. Enterprise Transparency** | PASS | `applied_points` audit field provides full visibility into points-based tier assignment. `formula_type` extended to include new mode values. Existing audit fields unchanged. |
| **V. Type-Safe Configuration** | PASS | New `TenureMatchTier` and `PointsMatchTier` Pydantic models with contiguity validators. All tier configs validated at load time before reaching dbt. |
| **VI. Performance & Scalability** | PASS | Points calculation is a simple integer addition per employee (O(n)). Tier lookup is a SQL CASE expression — no joins or subqueries. No performance regression expected. |

**Post-Phase 1 Re-check**: All gates remain PASS. Design adds two Jinja conditional branches and one new macro file — minimal complexity increase.

## Project Structure

### Documentation (this feature)

```text
specs/046-tenure-points-match/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: Research findings
├── data-model.md        # Phase 1: Entity definitions
├── quickstart.md        # Phase 1: Developer quick reference
├── contracts/           # Phase 1: Interface contracts
│   ├── dbt-variables.md # dbt variable schemas
│   └── api-endpoints.md # API endpoint contracts
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
dbt/
├── macros/
│   ├── get_tiered_match_rate.sql              # EXISTING - reused for tenure_based
│   └── get_points_based_match_rate.sql        # NEW - points tier CASE macros
├── models/intermediate/events/
│   └── int_employee_match_calculations.sql    # MODIFY - add tenure/points branches
└── dbt_project.yml                            # VERIFY - variable defaults

planalign_orchestrator/
└── config/
    ├── workforce.py                           # MODIFY - add tier Pydantic models
    └── export.py                              # MODIFY - export new dbt variables

config/
└── simulation_config.yaml                     # MODIFY - add tier config examples

planalign_api/
└── storage/
    └── workspace_storage.py                   # MODIFY - default config for new modes

planalign_studio/
└── src/components/                            # MODIFY (P3) - tier editor UI

tests/
└── test_match_modes.py                        # NEW - validation and integration tests
```

**Structure Decision**: This feature extends the existing web application structure. No new directories required — all changes fit within established module boundaries.

## Implementation Details

### Phase 1: dbt Layer — New Macros (P1)

**File**: `dbt/macros/get_points_based_match_rate.sql` (NEW)

Two macros following the pattern of `get_tiered_match_rate.sql`:

1. `get_points_based_match_rate(points_col, points_schedule, default_rate)` — generates CASE expression returning match rate decimal for a given points value. Tiers sorted descending by `min_points`.

2. `get_points_based_max_deferral(points_col, points_schedule, default_pct)` — generates CASE expression returning max deferral decimal for a given points value.

### Phase 2: dbt Layer — Match Calculation Model (P1)

**File**: `dbt/models/intermediate/events/int_employee_match_calculations.sql` (MODIFY)

Add two new Jinja branches in the conditional compilation:

```
{% if employer_match_status == 'graded_by_service' %}
  -- existing service-based calculation
{% elif employer_match_status == 'tenure_based' %}
  -- NEW: same formula as graded_by_service, reads tenure_match_tiers
  -- Uses get_tiered_match_rate() and get_tiered_match_max_deferral() with tenure_match_tiers
  -- Populates applied_years_of_service
{% elif employer_match_status == 'points_based' %}
  -- NEW: calculates applied_points = FLOOR(ec.current_age) + years_of_service
  -- Uses get_points_based_match_rate() and get_points_based_max_deferral()
  -- Populates both applied_points and applied_years_of_service
{% else %}
  -- existing deferral-based calculation
{% endif %}
```

New output column: `applied_points` (INTEGER, NULL for non-points modes).

### Phase 3: Python Configuration (P1)

**File**: `planalign_orchestrator/config/workforce.py` (MODIFY)
- Add `TenureMatchTier(BaseModel)` with fields: min_years, max_years, match_rate, max_deferral_pct
- Add `PointsMatchTier(BaseModel)` with fields: min_points, max_points, match_rate, max_deferral_pct
- Add `validate_tier_contiguity()` function for shared tier validation
- Extend `EmployerMatchSettings` to accept `tenure_match_tiers` and `points_match_tiers`

**File**: `planalign_orchestrator/config/export.py` (MODIFY)
- Extend `_export_employer_match_vars()` to export `tenure_match_tiers` and `points_match_tiers`
- Apply field name transformation (UI → dbt) with percentage conversion
- Handle `employer_match_status` extended values

**File**: `config/simulation_config.yaml` (MODIFY)
- Add commented example configurations for both new modes

### Phase 4: Testing (P1/P2)

- dbt tests: Verify tier assignment at boundaries, match calculation correctness, audit field population
- Python tests: Pydantic validation (gaps, overlaps, start-at-zero, valid ranges)
- Regression tests: Run existing deferral_based and graded_by_service simulations and verify identical output
- Multi-year tests: Verify points/tenure tier transitions across simulation years

### Phase 5: API & Studio (P3)

- Extend workspace default config to include empty tier arrays
- Add mode selector to match config UI
- Dynamic tier editor with columns adapting to selected mode
- Inline validation feedback for tier configurations

## Complexity Tracking

> No Constitution Check violations — table not required.
