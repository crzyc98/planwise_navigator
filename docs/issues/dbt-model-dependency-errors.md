# dbt Model Dependency Errors - Work Machine Resolution Plan

**Created**: 2025-08-13
**Status**: In Progress
**Branch**: `fix/dbt-model-dependencies`

## Overview

Four specific dbt model errors are blocking the navigator orchestrator on the work machine. These errors are due to schema mismatches between model outputs and test expectations, likely caused by differences between development environments.

## Error Analysis

### 1. Escalation Registry Column Missing
**File**: `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql`
**Error**: References `r.in_auto_escalation_program`, but JOINed table `deferral_escalation_registry` has no such column.

**Root Cause**: Model references a column that doesn't exist in the registry schema.

**Fix Strategy**: Replace the missing column reference with a default value or correct column name.

### 2. Merit Events Model Contract Mismatch
**Model**: `int_merit_events`
**Errors**:
- `not_null_int_merit_events_compensation_amount`: "compensation_amount" column not found
- `accepted_values_int_merit_events_event_type__RAISE`: At least one row has unexpected event_type

**Root Cause**: Model output schema doesn't match test expectations for downstream consumption by `fct_yearly_events`.

**Fix Strategy**: Align model output with expected schema:
- Map `new_salary` → `compensation_amount`
- Ensure `event_type` = 'RAISE' (uppercase)
- Add required columns for event sourcing

### 3. Enrollment Event Category Outside Accepted Set
**Model**: `int_enrollment_events`
**Error**: `accepted_values` test expects `['proactive_enrollment', 'auto_enrollment', 'voluntary_enrollment', 'enrollment_opt_out']`, but model emits `'executive_enrollment'`.

**Root Cause**: Model produces event categories not in the accepted test values.

**Fix Strategy**: Normalize 'executive_enrollment' to 'voluntary_enrollment' to stay within accepted categories.

### 4. Test Schema Misalignment
**Impact**: Multiple tests reference columns that don't exist in actual model outputs.

**Root Cause**: Test definitions were created for a different version of the models than what exists.

## Implementation Plan

### Phase 1: Fix Column References

1. **Update Escalation Events Model**
   ```sql
   -- Replace missing column reference
   COALESCE(r.is_eligible_for_escalation, true) as in_auto_escalation_program
   -- OR simply default to true if no registry logic needed
   ```

2. **Update Merit Events Schema**
   ```sql
   SELECT
     employee_id,
     employee_ssn,
     'RAISE' as event_type,  -- Uppercase required
     simulation_year,
     effective_date,
     event_details,
     new_salary as compensation_amount,  -- Map column
     previous_salary as previous_compensation,  -- Map column
     -- ... other required columns
   FROM merit_calculations
   ```

3. **Normalize Enrollment Categories**
   ```sql
   CASE
     WHEN event_category = 'executive_enrollment' THEN 'voluntary_enrollment'
     ELSE event_category
   END as event_category
   ```

### Phase 2: Test and Validate

Run targeted commands to verify fixes:

```bash
# Test model compilation and execution
dbt run --select int_deferral_rate_escalation_events int_enrollment_events int_merit_events

# Run specific tests that were failing
dbt test --select int_merit_events int_enrollment_events

# Full pipeline test
dbt build --select int_deferral_rate_escalation_events+ --fail-fast
```

## Success Criteria

- [ ] All 4 identified errors resolved
- [ ] No new contract/test regressions introduced
- [ ] Models align with `fct_yearly_events` consumption requirements
- [ ] Event-sourced lineage maintained
- [ ] Uppercase conventions preserved for event types

## Risk Mitigation

- **Minimal Changes**: Keep diffs small to avoid introducing new issues
- **No Circular Dependencies**: Ensure registry fixes don't create dependency loops
- **Schema Contracts**: Maintain column contracts required by downstream marts
- **Test Coverage**: Validate fixes don't break existing functionality

## Validation Commands

```bash
# Development validation
dbt compile --select int_deferral_rate_escalation_events int_enrollment_events int_merit_events

# Execution validation
dbt run --select int_deferral_rate_escalation_events int_enrollment_events int_merit_events --vars '{"simulation_year": 2025}'

# Test validation
dbt test --select int_merit_events int_enrollment_events --vars '{"simulation_year": 2025}'

# Integration validation (if time permits)
dbt run --select +fct_yearly_events --vars '{"simulation_year": 2025}'
```

## Next Steps

1. Implement the three model fixes
2. Run validation commands
3. Test navigator orchestrator end-to-end
4. Commit fixes to `fix/dbt-model-dependencies` branch
5. Create PR to merge fixes to main

## Notes

These errors are likely due to schema drift between the local development environment (which has accumulated changes over time) and the clean work environment (building from scratch). The fixes ensure both environments can build successfully with the current model definitions.
