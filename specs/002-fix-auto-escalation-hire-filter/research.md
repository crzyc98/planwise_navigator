# Research: Auto-Escalation Hire Date Filter Bug

**Date**: 2025-12-12
**Feature**: 002-fix-auto-escalation-hire-filter

## Executive Summary

The auto-escalation hire date cutoff filter is not working as documented. The configuration states employees hired "ON OR AFTER" the cutoff date should be eligible for escalation, but the implementation uses strictly greater than (`>`) comparison, which excludes employees hired ON the cutoff date.

## Root Cause Investigation

### Configuration Documentation

**File**: `config/simulation_config.yaml` (line 645)
```yaml
hire_date_cutoff: "2020-01-01"  # Optional YYYY-MM-DD; Only escalate employees hired ON OR AFTER this date
```

The comment clearly states "ON OR AFTER", meaning the comparison should be inclusive (`>=`).

### Implementation Analysis

#### SQL Path (dbt model)

**File**: `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql`

**Lines 81-83**:
```sql
{%- if esc_hire_cutoff is not none %}
    AND w.employee_hire_date > '{{ esc_hire_cutoff }}'::DATE
{%- endif %}
```

**Line 27 comment**:
```sql
-- Toggle inclusion based on hire date
```

**Issue**: Uses `>` (strictly greater than), not `>=` (greater than or equal to)

#### Polars Path (Python)

**File**: `planalign_orchestrator/polars_event_factory.py`

**Lines 1158-1159 comment**:
```python
# E102 FIX: Get hire date cutoff for filtering employees
# Only employees hired AFTER this date are eligible for escalation
```

**Lines 1176-1178**:
```python
eligible = eligible.filter(
    pl.col('employee_hire_date') > pl.lit(cutoff_date)
)
```

**Issue**: Uses `>` (strictly greater than), not `>=`. Comment incorrectly says "AFTER" instead of "ON OR AFTER".

### Comment/Code Discrepancy

The Polars code has an E102 FIX comment that actually codified the wrong behavior. The comment says "hired AFTER this date" which contradicts the configuration documentation that says "ON OR AFTER this date".

## Decision

**Decision**: Change comparison operator from `>` to `>=` in both SQL and Polars code paths

**Rationale**:
1. The configuration documentation clearly states "ON OR AFTER"
2. This is standard industry practice for cutoff date semantics (inclusive lower bound)
3. Users expect employees hired on the cutoff date to be included

**Alternatives Considered**:

| Alternative | Rejected Because |
|-------------|------------------|
| Keep `>` and update documentation | Would change documented behavior; users may have relied on "ON OR AFTER" wording |
| Add configuration option for inclusive/exclusive | Over-engineering for a simple fix; no user has requested this flexibility |
| Only fix SQL path | Would create parity issues between SQL and Polars modes |

## Impact Analysis

### Files to Modify

1. `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql` - Line 82
2. `planalign_orchestrator/polars_event_factory.py` - Line 1177

### Behavioral Changes

| Scenario | Before | After |
|----------|--------|-------|
| Employee hired on cutoff date | NOT escalated | Escalated |
| Employee hired before cutoff | NOT escalated | NOT escalated (unchanged) |
| Employee hired after cutoff | Escalated | Escalated (unchanged) |

### Backward Compatibility

The fix is backward compatible for:
- `hire_date_cutoff: null` (all employees) - no change
- `hire_date_cutoff: "1900-01-01"` (effectively all) - no change
- `hire_date_cutoff: "2999-01-01"` (effectively none) - no change

The only behavioral change is for employees hired exactly ON the cutoff date, which aligns with the documented behavior.

## Verification Plan

1. **Unit test**: Create test for boundary condition (employee hired on cutoff date)
2. **Integration test**: Run both `ae_all_eligible` and `ae_new_hires` scenarios
3. **Parity test**: Verify SQL and Polars modes produce identical results

## References

- Epic E035: Automatic Annual Deferral Rate Escalation
- Epic E102: Polars Event Factory Hire Date Filter
- Configuration: `config/simulation_config.yaml` line 645
