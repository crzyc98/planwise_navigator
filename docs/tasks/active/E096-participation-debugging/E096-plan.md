# E096: Participation Debugging - Complete Analysis

**Branch:** `feature/E096-participation-debugging-dashboard`
**Created:** 2025-12-09
**Last Updated:** 2025-12-09
**Status:** COMPLETED - All 5 Bugs Fixed (3 dbt + 2 Polars pipeline)

## Problem Statement
1. **New hires** have blank enrollment/eligibility fields despite auto-enrollment at 2%
2. **Census employees** (93% participating at year-end) show 0% participation in 2025

## Implementation Results

### Before Fix
- Census employees: 0% participation in 2025 simulation
- New hires: blank enrollment/eligibility fields

### After Fix
- **Census Employees**: 96.6% participation rate for continuous_active employees
- **New Hires**: 86.9% participation rate for new_hire_active (with auto-enrollment)
- **Participation Detail**:
  - Census enrollment: 6,336 employees (7.57% avg deferral rate)
  - Auto enrollment: 831 employees (2.0% avg deferral rate)
  - Voluntary enrollment: 541 employees (6.56% avg deferral rate)
  - Opted out of AE: 276 employees
  - Not auto enrolled: 132 employees

## Bugs Fixed

### BUG #1: Event Type Mismatch [FIXED - Previous Commit]
**File:** `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql`
**Lines:** 60-61, 140-141

**Issue:** Filtered for `'benefit_enrollment'` but `int_enrollment_events` generates `'enrollment'` events.

**Fix Applied:**
```sql
-- FROM:
WHERE LOWER(event_type) = 'benefit_enrollment'
-- TO:
WHERE LOWER(event_type) IN ('enrollment', 'benefit_enrollment')
```

**Commit:** `daee4d6` - "fix(E096): Fix participation bug - event type mismatch in deferral accumulator"

---

### BUG #2: New Hire Eligibility Wrong Join Order [FIXED]
**File:** `dbt/models/marts/fct_workforce_snapshot.sql`
**Lines:** 377-413

**Issue:** The new hires section started FROM `int_enrollment_state_accumulator` and LEFT JOINed to hire events. If new hires don't have enrollment events, they don't appear in the accumulator, so they're excluded entirely.

**Fix Applied:** Reversed join order - start from hire events (source of truth), LEFT JOIN to enrollment accumulator.

```sql
-- E096 FIX: Start from hire events (source of truth for new hires)
FROM (
    SELECT employee_id, effective_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND event_type = 'hire'
      AND employee_id LIKE 'NH_{{ simulation_year }}_%'
) he
LEFT JOIN (
    SELECT employee_id, enrollment_date, enrollment_status AS is_enrolled
    FROM {{ ref('int_enrollment_state_accumulator') }}
    WHERE simulation_year = {{ simulation_year }}
) accumulator ON he.employee_id = accumulator.employee_id
```

---

### BUG #3: Census Participation Not Flowing Through [FIXED]
**File:** `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql`
**Lines:** 270-299, 331-351

**Issue:** The `first_year_state` CTE had a restrictive filter `WHERE he.employee_id IS NOT NULL` that excluded employees not in `first_year_enrolled_employees`. Also, non-enrolled employees were getting fallback rates instead of 0.

**Fixes Applied:**

1. **Relaxed filter** to include ALL workforce employees:
```sql
-- FROM:
WHERE he.employee_id IS NOT NULL
-- TO:
WHERE COALESCE(w.employee_id, he.employee_id) IS NOT NULL
```

2. **Fixed deferral rate logic** for non-enrolled employees:
```sql
-- Non-enrolled employees (he.employee_id IS NULL) now get 0, not fallback rate
CASE
    WHEN oo.employee_id IS NOT NULL THEN 0.00  -- Opted out
    WHEN he.employee_id IS NULL THEN 0.00      -- Not enrolled (no enrollment event)
    ELSE COALESCE(...)                         -- Enrolled employees use normal logic
END as current_deferral_rate
```

3. **Added 'not_enrolled' rate_source** for tracking:
```sql
CASE
    WHEN oo.employee_id IS NOT NULL THEN 'opt_out'
    WHEN he.employee_id IS NULL THEN 'not_enrolled'  -- Track non-enrolled employees
    ...
END as rate_source
```

---

### BUG #4: Polars State Pipeline Table Name Mismatch [FIXED]
**Files:**
- `planalign_orchestrator/polars_state_pipeline.py`
- `planalign_orchestrator/pipeline/year_executor.py`

**Issue:** When Polars state accumulation mode is enabled, the pipeline:
1. Wrote to `polars_*` prefixed tables (e.g., `polars_deferral_state`) instead of the table names dbt expects (e.g., `int_deferral_rate_state_accumulator_v2`)
2. Used `get_database_path()` which returns the default dbt database, not the scenario-specific database
3. Only ran 3 post-processing models, skipping models that depend on Polars output

**Fixes Applied:**

1. **Changed Polars to write to dbt-expected table names** (`polars_state_pipeline.py`):
```python
# FROM: polars_enrollment_state, polars_deferral_state, polars_contributions
# TO: int_enrollment_state_accumulator, int_deferral_rate_state_accumulator_v2, int_employee_contributions
```

2. **Use scenario-specific database path** (`year_executor.py`):
```python
# FROM:
database_path=get_database_path()
# TO:
db_path = getattr(self.db_manager, 'db_path', None) or get_database_path()
database_path=db_path
```

3. **Updated post-processing to run all non-replaced models** (`year_executor.py`):
```python
# Models that Polars replaces (should NOT run via dbt)
polars_replaced_models = {
    "int_enrollment_state_accumulator",
    "int_deferral_rate_state_accumulator_v2",
    "int_employee_contributions",
}
# All other stage models now run via dbt post-processing
models_to_run = [model for model in stage.models if model not in polars_replaced_models]
```

---

### BUG #5: Polars Missing Auto-Enrollment for New Hires [FIXED]
**File:** `planalign_orchestrator/polars_event_factory.py`

**Issue:** The Polars event factory did NOT generate auto-enrollment events for new hires:
- 811 new hires in 2025, ZERO enrollment events
- `generate_enrollment_events()` only did voluntary enrollment (probability-based)
- New hires only got enrolled in year 2026+ via voluntary path

**Root Cause (discovered after initial fix attempt):**
- Initial fix filtered `cohort` for `NH_{year}_` prefix
- But the cohort only contains census/previous-year employees
- New hires are generated by `generate_hire_events()` and stored separately in `hire_events_df`
- The auto-enrollment method needs to use `hire_events_df`, not filter the cohort

**Fixes Applied:**

1. **Changed `generate_auto_enrollment_events()` signature** to accept `hire_events`:
```python
def generate_auto_enrollment_events(self, hire_events: pl.DataFrame, simulation_year: int) -> pl.DataFrame:
    """Generate automatic enrollment events for new hires."""
    # Uses hire_events DataFrame directly (not cohort)
    # Generate enrollment events with event_category='auto_enrollment'
    # Use 2% default deferral rate, 45-day window
```

2. **Moved auto-enrollment call** out of main event loop to run AFTER hire events:
```python
# Generate events that depend on hire_events_df (must run after hire events)
if hire_events_df is not None and hire_events_df.height > 0:
    # E096 FIX: Generate auto-enrollment events for new hires
    auto_enroll_events = self.generate_auto_enrollment_events(hire_events_df, simulation_year)
    # ... then generate new_hire_terminations
```

3. **Added default parameters**:
```python
'auto_enrollment_enabled': True,
'auto_enrollment_default_deferral_rate': 0.02,  # 2%
'auto_enrollment_window_days': 45,
```

---

## Test Updates

Updated two tests to account for census-sourced enrollments:

1. `dbt/tests/intermediate/test_s042_source_of_truth.sql`
   - Added `census_enrolled` CTE
   - Updated `enrolled_without_events` to also check for census enrollment
   - Updated validation summary to include census enrolled count

2. `dbt/tests/analysis/test_deferral_rate_source_of_truth.sql`
   - Added `census_enrolled` CTE
   - Updated coverage test to include census enrollment
   - Updated count consistency check to include census + events vs state
   - Fixed NH_2025_000007 test to use `rate_source` instead of `escalation_source`

---

## Test Results

**Before E096 fixes:** 13 test failures
**After E096 fixes:** 11 test failures (2 fixed)

Tests now passing:
- `test_s042_source_of_truth` - PASS
- `test_deferral_rate_source_of_truth` - PASS

Remaining test failures are pre-existing and unrelated to E096 scope.

---

## Files Modified

1. `dbt/models/marts/fct_workforce_snapshot.sql` - Bug #2 fix
2. `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql` - Bug #1 and #3 fix
3. `dbt/tests/intermediate/test_s042_source_of_truth.sql` - Test update
4. `dbt/tests/analysis/test_deferral_rate_source_of_truth.sql` - Test update
5. `planalign_orchestrator/polars_state_pipeline.py` - Bug #4 fix (table names)
6. `planalign_orchestrator/pipeline/year_executor.py` - Bug #4 fix (database path, post-processing)
7. `planalign_orchestrator/polars_event_factory.py` - Bug #5 fix (auto-enrollment for new hires)

---

## Validation Queries

```sql
-- Check participation by rate source
SELECT rate_source, COUNT(*) as employee_count,
       SUM(CASE WHEN current_deferral_rate > 0 THEN 1 ELSE 0 END) as participating
FROM int_deferral_rate_state_accumulator_v2
WHERE simulation_year = 2025
GROUP BY rate_source;

-- Results:
-- census_rate: 5732 employees, 5732 participating (100%)
-- enrollment_event: 1976 employees, 1976 participating (100%)
-- opt_out: 276 employees, 0 participating
-- not_enrolled: 132 employees, 0 participating

-- Check workforce snapshot participation
SELECT participation_status, COUNT(*) as count
FROM fct_workforce_snapshot
WHERE simulation_year = 2025
GROUP BY participation_status;

-- Results:
-- participating: 7,708 employees (95%)
-- not_participating: 408 employees (5%)
```
