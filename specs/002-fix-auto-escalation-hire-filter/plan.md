# Implementation Plan: Fix Auto-Escalation Hire Date Filter

**Branch**: `002-fix-auto-escalation-hire-filter` | **Date**: 2025-12-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-fix-auto-escalation-hire-filter/spec.md`

## Summary

Fix the auto-escalation hire date cutoff filter bug where employees hired before the configured cutoff date are incorrectly receiving escalation events. The root cause is the use of strictly greater than (`>`) comparison instead of greater than or equal to (`>=`) in both the SQL (dbt) and Polars event generation code paths. The fix requires changing the comparison operator from `>` to `>=` in two locations.

## Technical Context

**Language/Version**: Python 3.11, SQL (DuckDB 1.0.0)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Polars
**Storage**: DuckDB (dbt/simulation.duckdb)
**Testing**: pytest (unit tests), dbt tests (data quality)
**Target Platform**: Linux/macOS server, work laptop deployment
**Project Type**: Single monorepo with dbt project and Python orchestrator
**Performance Goals**: No performance impact (filter change only)
**Constraints**: Backward compatibility required, single-threaded stability
**Scale/Scope**: 5,000+ employees, multi-year simulations (2026-2030)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Fix corrects event generation filter; does not modify existing events |
| II. Modular Architecture | PASS | Changes confined to 2 existing modules, no new modules created |
| III. Test-First Development | PASS | Will add tests for boundary conditions before fix implementation |
| IV. Enterprise Transparency | PASS | Filter logic already logged; no additional audit impact |
| V. Type-Safe Configuration | PASS | Configuration parsing unchanged; only comparison operator fix |
| VI. Performance & Scalability | PASS | Filter change has negligible performance impact |

**Gate Status**: PASSED - All principles satisfied. No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/002-fix-auto-escalation-hire-filter/
├── plan.md              # This file
├── research.md          # Root cause analysis
├── data-model.md        # Not applicable (bug fix, no new entities)
├── quickstart.md        # Testing quickstart
├── contracts/           # Not applicable (no API changes)
└── tasks.md             # Implementation tasks
```

### Source Code (repository root)

```text
# Affected files (bug fix - no new files)
dbt/
└── models/
    └── intermediate/
        └── events/
            └── int_deferral_rate_escalation_events.sql  # Line 82: > to >=

planalign_orchestrator/
└── polars_event_factory.py                              # Line 1177: > to >=

tests/
└── test_escalation_hire_date_filter.py                  # NEW: boundary tests

scenarios/
├── ae_all_eligible.yaml                                 # Existing test scenario
└── ae_new_hires.yaml                                    # Existing test scenario
```

**Structure Decision**: Bug fix within existing structure. Only 2 files modified, 1 new test file created.

## Complexity Tracking

> No Constitution Check violations. This table is empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |

## Root Cause Analysis

### Bug Location 1: SQL (dbt model)

**File**: `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql`
**Line**: 82
**Current Code**:
```sql
{%- if esc_hire_cutoff is not none %}
    AND w.employee_hire_date > '{{ esc_hire_cutoff }}'::DATE
{%- endif %}
```
**Issue**: Uses `>` (strictly greater than) instead of `>=` (greater than or equal to)
**Impact**: Employees hired ON the cutoff date are excluded when they should be included

### Bug Location 2: Polars (Python)

**File**: `planalign_orchestrator/polars_event_factory.py`
**Line**: 1177
**Current Code**:
```python
eligible = eligible.filter(
    pl.col('employee_hire_date') > pl.lit(cutoff_date)
)
```
**Issue**: Uses `>` (strictly greater than) instead of `>=` (greater than or equal to)
**Impact**: Same as SQL - employees hired ON the cutoff date are excluded

### Comment Documentation

Both locations have misleading comments stating "hired AFTER this date" when the configuration documentation says "hired ON OR AFTER this date". Comments should be corrected to match the intended behavior.

## Implementation Steps

### Step 1: Add Test for Boundary Condition (TDD)

Create test that verifies employees hired ON the cutoff date receive escalation events.

### Step 2: Fix SQL Filter (dbt model)

Change line 82 from:
```sql
AND w.employee_hire_date > '{{ esc_hire_cutoff }}'::DATE
```
To:
```sql
AND w.employee_hire_date >= '{{ esc_hire_cutoff }}'::DATE
```

### Step 3: Fix Polars Filter (Python)

Change line 1177 from:
```python
pl.col('employee_hire_date') > pl.lit(cutoff_date)
```
To:
```python
pl.col('employee_hire_date') >= pl.lit(cutoff_date)
```

### Step 4: Update Comments

Fix misleading comments in both files to say "ON OR AFTER" instead of "AFTER".

### Step 5: Validation Testing

Run scenarios to verify:
1. Employees hired before cutoff are NOT escalated
2. Employees hired ON cutoff ARE escalated
3. Employees hired after cutoff ARE escalated
4. Backward compatibility with null/past cutoff dates

## Test Plan

### Unit Tests

| Test Case | Input | Expected Output |
|-----------|-------|-----------------|
| Employee hired day before cutoff | hire_date=2025-12-31, cutoff=2026-01-01 | NOT escalated |
| Employee hired ON cutoff date | hire_date=2026-01-01, cutoff=2026-01-01 | Escalated |
| Employee hired day after cutoff | hire_date=2026-01-02, cutoff=2026-01-01 | Escalated |
| No cutoff configured | hire_date=any, cutoff=null | Escalated |
| Cutoff in past (1900-01-01) | hire_date=any, cutoff=1900-01-01 | Escalated |

### Integration Tests

1. Run `ae_all_eligible` scenario (cutoff: 1900-01-01) - all enrolled should escalate
2. Run `ae_new_hires` scenario (cutoff: 2026-01-01) - only new hires should escalate
3. Compare escalation event counts between scenarios

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Backward compatibility break | Low | Medium | Test with existing scenarios |
| Polars/SQL parity mismatch | Low | High | Test both paths with same data |
| Configuration parsing issues | Very Low | Medium | No config changes needed |

## Estimated Effort

- Test creation: 30 minutes
- Code fix: 10 minutes (2 lines changed)
- Comment updates: 5 minutes
- Validation: 30 minutes
- Total: ~1.5 hours
