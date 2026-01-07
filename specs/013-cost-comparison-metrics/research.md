# Research: Employer Cost Ratio Metrics

**Date**: 2026-01-07
**Feature**: 013-cost-comparison-metrics

## Research Summary

All technical decisions are resolved. The feature extends existing patterns with no unknowns.

## Decision 1: Data Source for Total Compensation

**Decision**: Use `prorated_annual_compensation` from `fct_workforce_snapshot`

**Rationale**:
- Field already exists and is populated for all active employees
- Verified in `fct_workforce_snapshot.sql` at line 1039
- Prorated calculation accounts for mid-year hires/terminations correctly
- Consistent with existing compensation metrics used elsewhere

**Alternatives Considered**:
- `current_compensation`: Rejected - doesn't account for proration
- `full_year_equivalent_compensation`: Rejected - would overstate for partial-year employees

## Decision 2: API Extension Pattern

**Decision**: Extend existing `_get_contribution_by_year()` query to include total compensation

**Rationale**:
- Single query aggregation is more efficient than separate queries
- Existing query already joins `fct_workforce_snapshot` with necessary filters
- Adding `SUM(prorated_annual_compensation)` is minimal change
- Follows existing patterns in `analytics_service.py`

**Alternatives Considered**:
- Separate endpoint for compensation data: Rejected - additional network round-trip, unnecessary complexity
- Pre-computed dbt model: Rejected - over-engineering for simple aggregation

## Decision 3: Employer Cost Rate Calculation Location

**Decision**: Calculate in backend API; return pre-computed `employer_cost_rate` field

**Rationale**:
- Ensures consistency between API consumers
- Avoids division-by-zero in frontend (backend handles edge cases)
- Follows existing pattern where `participation_rate` is calculated server-side
- Enables backend validation and logging of edge cases

**Alternatives Considered**:
- Frontend calculation: Rejected - duplicates logic, harder to validate edge cases

## Decision 4: Edge Case Handling

**Decision**: Return `0.0` for zero compensation scenarios; backend logs warning

**Rationale**:
- Zero compensation is theoretically possible but indicates data quality issue
- Returning 0.0% is more user-friendly than error or N/A
- Backend logging enables monitoring for data quality issues
- Follows existing pattern in `_get_participation_summary()` for zero-division handling

**Alternatives Considered**:
- Return `null`/`N/A`: Rejected - complicates variance calculations in frontend
- Throw error: Rejected - disrupts user workflow for edge case

## Decision 5: Frontend Component Pattern

**Decision**: Add new MetricCard for summary; extend existing table row pattern for year-by-year

**Rationale**:
- MetricCard component already exists and handles variance display
- Year-by-year table already has established row pattern
- Minimizes frontend changes; reuses existing UI patterns
- Consistent visual language with existing metrics

**Alternatives Considered**:
- New tab/section for cost metrics: Rejected - fragments the comparison view
- Inline display without card: Rejected - inconsistent with other summary metrics

## No Outstanding Unknowns

All research questions resolved. Ready for Phase 1: Design & Contracts.
