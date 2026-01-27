# Implementation Plan: Fix Workforce Snapshot Performance Regression

**Branch**: `028-fix-snapshot-perf-regression` | **Date**: 2026-01-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/028-fix-snapshot-perf-regression/spec.md`

## Summary

Fix 5.6x performance regression in `fct_workforce_snapshot.sql` (45 min → target <15 min for 5-year Windows simulation) by:
1. Replacing 4 O(n²) scalar subqueries (lines 971-1025) with a single O(n) JOIN + CASE expression
2. Adding missing `simulation_year` filters at 3 locations to prevent full table scans

## Technical Context

**Language/Version**: SQL (DuckDB 1.0.0) with Jinja2 templating (dbt-core 1.8.8)
**Primary Dependencies**: dbt-duckdb 1.8.1, DuckDB 1.0.0
**Storage**: DuckDB database at `dbt/simulation.duckdb`
**Testing**: dbt tests (schema tests, custom tests), manual performance benchmarking
**Target Platform**: Windows, Linux, macOS (all platforms benefit; Windows most impacted)
**Project Type**: dbt SQL project (single model modification)
**Performance Goals**: 5-year simulation <15 min (from 45 min); single-year model <30 sec
**Constraints**: No functional behavior change; 100% data consistency required
**Scale/Scope**: 10K-100K employees, 5-year simulations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Event Sourcing & Immutability | ✅ PASS | No changes to fct_yearly_events; read-only optimization |
| II. Modular Architecture | ✅ PASS | Single file change; no new modules; no circular dependencies |
| III. Test-First Development | ✅ PASS | Existing dbt tests validate data consistency |
| IV. Enterprise Transparency | ✅ PASS | No logging changes; compensation_quality_flag preserved |
| V. Type-Safe Configuration | ✅ PASS | No config changes; uses existing `{{ var('simulation_year') }}` |
| VI. Performance & Scalability | ✅ PASS | This fix directly addresses performance regression |

**dbt Development Patterns Check**:
- ✅ Changes use `{{ var('simulation_year') }}` filter (adding missing filters)
- ✅ No circular dependencies introduced (int_baseline_workforce → fct_workforce_snapshot)
- ✅ Using `{{ ref() }}` for all table references

## Project Structure

### Documentation (this feature)

```text
specs/028-fix-snapshot-perf-regression/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 research findings
├── data-model.md        # Phase 1 output (N/A - no schema changes)
├── quickstart.md        # Phase 1 output
└── checklists/
    └── requirements.md  # Specification validation checklist
```

### Source Code (repository root)

```text
dbt/
└── models/
    └── marts/
        └── fct_workforce_snapshot.sql  # MODIFIED: Primary optimization target
```

**Structure Decision**: Single dbt model modification. No new files required. This is a pure SQL refactoring within an existing model.

## Implementation Details

### Fix 1: Replace Scalar Subqueries with JOIN (Lines 971-1025)

**Before** (O(n²) - 4 scalar subqueries):
```sql
WHEN (
    SELECT CASE WHEN b.current_compensation > 0 AND
         (current_compensation / b.current_compensation) > 100.0 THEN true ELSE false END
    FROM {{ ref('int_baseline_workforce') }} b
    WHERE b.employee_id = final_workforce_with_contributions.employee_id
      AND b.simulation_year = {{ var('simulation_year') }}
    LIMIT 1
) = true THEN 'CRITICAL_INFLATION_100X'
-- Repeated 3 more times for 50X, 10X, 5X
```

**After** (O(n) - single JOIN + CASE):

1. Add new CTE before `final_output`:
```sql
baseline_comp_for_quality AS (
    SELECT
        employee_id,
        current_compensation AS baseline_compensation
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('simulation_year') }}
),
```

2. Add LEFT JOIN in `final_output` CTE:
```sql
LEFT JOIN baseline_comp_for_quality bcq
    ON final_workforce_with_contributions.employee_id = bcq.employee_id
```

3. Replace 4 scalar subqueries with single CASE:
```sql
CASE
    WHEN bcq.baseline_compensation IS NULL THEN 'NORMAL'
    WHEN bcq.baseline_compensation <= 0 THEN 'NORMAL'
    WHEN (current_compensation / bcq.baseline_compensation) > 100.0 THEN 'CRITICAL_INFLATION_100X'
    WHEN (current_compensation / bcq.baseline_compensation) > 50.0 THEN 'CRITICAL_INFLATION_50X'
    WHEN (current_compensation / bcq.baseline_compensation) > 10.0 THEN 'SEVERE_INFLATION_10X'
    WHEN (current_compensation / bcq.baseline_compensation) > 5.0 THEN 'WARNING_INFLATION_5X'
    ELSE 'NORMAL'
END AS compensation_quality_flag,
```

### Fix 2: Add Missing simulation_year Filters

**Location 1 - Line 373** (Year 1 baseline eligibility):
```sql
-- BEFORE
FROM {{ ref('int_baseline_workforce') }} baseline
-- AFTER
FROM {{ ref('int_baseline_workforce') }} baseline
WHERE baseline.simulation_year = {{ var('simulation_year') }}
  AND baseline.employment_status = 'active'
```

**Location 2 - Line 423** (NOT IN subquery):
```sql
-- BEFORE
WHERE he.employee_id NOT IN (
    SELECT employee_id FROM {{ ref('int_baseline_workforce') }} WHERE employment_status = 'active'
)
-- AFTER
WHERE he.employee_id NOT IN (
    SELECT employee_id FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('simulation_year') }}
      AND employment_status = 'active'
)
```

**Location 3 - Line 472** (baseline fallback):
```sql
-- BEFORE
FROM {{ ref('int_baseline_workforce') }}
WHERE employment_status = 'active'
-- AFTER
FROM {{ ref('int_baseline_workforce') }}
WHERE simulation_year = {{ var('simulation_year') }}
  AND employment_status = 'active'
```

## Verification Plan

### Pre-Implementation Baseline
1. Run 5-year simulation and record: total time, event counts, workforce counts
2. Export `fct_workforce_snapshot` data for regression comparison

### Post-Implementation Validation
1. Run identical 5-year simulation with same seed
2. Compare total execution time (target: <15 min, minimum 3x improvement)
3. Verify 100% data match with pre-optimization baseline
4. Run all dbt tests: `dbt test --select fct_workforce_snapshot`

### Acceptance Criteria Verification

| Criterion | Verification Method |
|-----------|-------------------|
| SC-001: <15 min 5-year | `time planalign simulate 2025-2029` |
| SC-002: <30 sec single-year | `time dbt run --select fct_workforce_snapshot --vars "simulation_year: 2025"` |
| SC-003: 100% data consistency | SQL diff of pre/post snapshot data |
| SC-004: All dbt tests pass | `dbt test --threads 1` |
| SC-005: Zero division errors | Verify no null/error compensation_quality_flag values |

## Complexity Tracking

> No constitution violations. No complexity justification required.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Data mismatch after optimization | Low | High | Pre/post data comparison; git revert if issues |
| Edge case not handled | Low | Medium | Explicit NULL/zero checks in CASE expression |
| Other models affected | Very Low | Low | Single model change; no schema changes |

## Phase 1 Artifacts

- **data-model.md**: N/A - no schema changes
- **contracts/**: N/A - no API changes
- **quickstart.md**: See below
