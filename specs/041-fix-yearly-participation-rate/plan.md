# Implementation Plan: Fix Yearly Participation Rate Consistency

**Branch**: `041-fix-yearly-participation-rate` | **Date**: 2026-02-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/041-fix-yearly-participation-rate/spec.md`

## Summary

Fix the per-year participation rate calculation in `AnalyticsService._get_contribution_by_year()` to filter to active employees only (matching `_get_participation_summary()`), resolving the inconsistency where per-year rates included terminated employees in the denominator, producing artificially lower values than the top-level rate. Add unit tests since none currently exist for this service.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI, Pydantic v2, DuckDB 1.0.0
**Storage**: DuckDB (`dbt/simulation.duckdb`) — read-only access in analytics service
**Testing**: pytest (unit tests with in-memory DuckDB)
**Target Platform**: Linux/macOS server (on-premises analytics)
**Project Type**: Web application (FastAPI backend + React frontend)
**Performance Goals**: N/A — single SQL subexpression change, no measurable performance impact
**Constraints**: Backward compatible — no API schema changes
**Scale/Scope**: 1 file changed, 1 test file created

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Event Sourcing & Immutability | **PASS** | Read-only analytics query; no event mutation |
| II. Modular Architecture | **PASS** | Change scoped to single method in single file |
| III. Test-First Development | **PASS** | New unit tests created for previously untested service |
| IV. Enterprise Transparency | **PASS** | Fix improves data consistency/transparency |
| V. Type-Safe Configuration | **PASS** | No config changes; Pydantic models unchanged |
| VI. Performance & Scalability | **PASS** | CASE WHEN in SQL — negligible performance impact |

**Post-Phase 1 Re-check**: All gates still PASS. No schema changes, no new dependencies, no architectural changes.

## Project Structure

### Documentation (this feature)

```text
specs/041-fix-yearly-participation-rate/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api-unchanged.md # No API contract changes
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_api/
└── services/
    └── analytics_service.py   # Fix participation rate SQL (1 line change)

tests/
└── test_analytics_service.py  # New: unit tests for analytics service
```

**Structure Decision**: Backend-only fix. Single file modification + new test file. No frontend changes. No new modules or dependencies.

## Implementation Details

### Phase 1: Fix the SQL Query

**File**: `planalign_api/services/analytics_service.py`
**Method**: `_get_contribution_by_year()` (line 185)

**Change**: Replace the participation rate subexpression to scope both numerator and denominator to active employees:

```sql
-- Before (includes all employees):
COUNT(CASE WHEN is_enrolled_flag THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)

-- After (active employees only):
COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' AND is_enrolled_flag THEN 1 END) * 100.0
  / NULLIF(COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' THEN 1 END), 0)
```

All other aggregations in the same query remain unchanged (contribution totals, avg deferral rate, participant_count use full population).

### Phase 2: Create Unit Tests

**File**: `tests/test_analytics_service.py` (new)

**Test cases**:
1. **test_participation_rate_active_only**: Seed data with active and terminated employees. Verify per-year participation rate excludes terminated from denominator.
2. **test_final_year_matches_top_level**: Verify the final-year `ContributionYearSummary.participation_rate` matches `DCPlanAnalytics.participation_rate`.
3. **test_contribution_totals_include_all**: Verify contribution sums still include terminated employees' contributions.
4. **test_zero_active_employees**: Verify participation rate is 0.0 when a year has no active employees.
5. **test_all_active_enrolled**: Verify participation rate is 100.0 when all active employees are enrolled.
6. **test_single_year_simulation**: Verify per-year rate equals top-level rate for single-year data.

**Test approach**: In-memory DuckDB with a `fct_workforce_snapshot` table seeded with controlled data. Mock `DatabasePathResolver` to return the in-memory database path.

## Complexity Tracking

No complexity violations. This is a minimal, targeted fix.
