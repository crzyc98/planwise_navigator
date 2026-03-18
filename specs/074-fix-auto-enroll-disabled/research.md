# Research: Fix Auto Enrollment Runs Despite Being Disabled

**Feature Branch**: `074-fix-auto-enroll-disabled`
**Date**: 2026-03-18

## Research Question 1: Where is `auto_enrollment_enabled` exported but not consumed?

### Decision
The variable is correctly exported from Python but not gated in 2 of 3 key dbt enrollment models.

### Rationale
Code trace reveals a complete pipeline break:

| Layer | File | Status |
|-------|------|--------|
| Python export | `planalign_orchestrator/config/export.py:98` | Exports `auto_enrollment_enabled` correctly |
| dbt window model | `int_auto_enrollment_window_determination.sql:263-264` | Correctly gates with `WHERE auto_enrollment_enabled = true` |
| dbt enrollment model | `int_enrollment_events.sql:214-220` | Sets `is_auto_enrollment_row` based on scope ONLY — never checks enabled flag |
| dbt proactive model | `int_proactive_voluntary_enrollment.sql:34-73` | Generates events within auto-enrollment window without checking enabled flag |

### Alternatives Considered
- **Fix at macro level** (`enrollment_eligibility.sql`): Rejected because the macros handle scope/eligibility logic, not feature-level enablement. Mixing concerns would make the macros harder to reason about.
- **Fix at Python orchestrator level** (skip enrollment dbt models entirely): Rejected because it would require the orchestrator to know about individual model semantics, breaking separation of concerns.
- **Fix only in `int_enrollment_events.sql`**: Insufficient — `int_proactive_voluntary_enrollment.sql` also needs gating.

---

## Research Question 2: What is the correct fix location and pattern?

### Decision
Add `auto_enrollment_enabled` gate in two dbt models, following the pattern already used in `int_auto_enrollment_window_determination.sql`.

### Rationale
The window determination model already demonstrates the correct pattern at lines 263-264:
```sql
WHERE auto_enrollment_enabled = true
  AND in_auto_enrollment_scope = true
```

Apply the same pattern to:

1. **`int_enrollment_events.sql` (line 214-220)**: Add enabled check to `is_auto_enrollment_row` CASE expression:
   ```sql
   CASE
     WHEN NOT {{ var('auto_enrollment_enabled', true) }} THEN false
     WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'all_eligible_employees' THEN true
     WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'new_hires_only'
          AND ({{ is_eligible_for_auto_enrollment('aw.employee_hire_date', 'aw.simulation_year') }})
       THEN true
     ELSE false
   END AS is_auto_enrollment_row,
   ```

2. **`int_proactive_voluntary_enrollment.sql`**: Add enabled check to the WHERE clause of the initial CTE or wrap the entire model output.

### Alternatives Considered
- **Add the check to the WHERE clause at line 355 instead of the CASE**: Both would work, but modifying the CASE is more semantically correct — it marks the row as not auto-enrollment rather than filtering it out, which preserves the row for potential voluntary enrollment processing.

---

## Research Question 3: What is the test gap?

### Decision
Need both dbt tests and Python integration tests to verify the fix.

### Rationale
- **Python tests** (`tests/unit/orchestrator/test_config_export.py`): Verify export of `auto_enrollment_enabled` but don't test dbt-level consumption.
- **dbt tests**: No existing tests validate that `auto_enrollment_enabled = false` prevents enrollment event generation.
- **Existing correct model** (`int_auto_enrollment_window_determination.sql`): Already gates correctly but downstream models ignore it.

### Test Plan
1. **dbt test**: Add a custom test that verifies zero auto-enrollment events when `auto_enrollment_enabled` is false
2. **Python test**: Add integration test that runs a simulation with auto-enrollment disabled and asserts zero auto-enrollment events in output

---

## Research Question 4: Impact on voluntary enrollment

### Decision
Voluntary enrollment is independent and should not be affected.

### Rationale
- Voluntary enrollment uses `int_proactive_voluntary_enrollment.sql` which generates events based on demographic participation rates
- However, the current model's new-hire CTE uses `is_eligible_for_auto_enrollment` macro to filter its population — this conflates auto-enrollment eligibility with voluntary enrollment targeting
- The fix must ensure that when auto-enrollment is disabled, voluntary enrollment can still function for the same population (they just won't get auto-enrolled)

### Key Insight
The `int_proactive_voluntary_enrollment.sql` model may need to be restructured so that:
- When auto-enrollment is enabled: proactive events augment auto-enrollment (opt-up rates)
- When auto-enrollment is disabled: proactive voluntary enrollment can still generate events based on demographic rates (these become the primary enrollment path)
