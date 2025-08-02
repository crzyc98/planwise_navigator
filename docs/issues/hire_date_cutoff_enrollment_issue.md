# Auto-Enrollment Hire Date Cutoff Issue

## Problem Statement

**Issue**: Auto-enrollment hire date cutoff is not working correctly. Employees are either being enrolled when they shouldn't be, or no enrollment events are being generated at all.

**Original Problem**: Employee `EMP_2024_000010` was getting enrolled in auto-enrollment despite hire date cutoff configuration that should have excluded them.

**Current Status**: After implementing the hire date cutoff logic, no enrollment events are being generated at all.

---

## Implementation Details

### Configuration Added
```yaml
# config/simulation_config.yaml
enrollment:
  auto_enrollment:
    enabled: true
    scope: "all_eligible_employees"  # Was "new_hires_only"
    hire_date_cutoff: "2020-01-01"  # Was "2025-01-01"
```

### dbt Variables Added
```yaml
# dbt/dbt_project.yml
vars:
  auto_enrollment_hire_date_cutoff: null
  auto_enrollment_scope: "new_hires_only"
```

### Models Updated
1. **`int_auto_enrollment_window_determination.sql`** - Added hire date cutoff to scope checking logic
2. **`int_enrollment_decision_matrix.sql`** - Added hire date cutoff to scope checking logic
3. **`int_enrollment_events.sql`** - Added both hire date cutoff AND scope checking logic (this was the key missing piece)

### Orchestration Updated
1. **`multi_year_orchestrator.py`** - Now passes both `auto_enrollment_hire_date_cutoff` and `auto_enrollment_scope` to dbt
2. **`common_workflow.py`** - Updated to pass enrollment configuration variables

---

## Technical Investigation Findings

### Root Cause #1: Missing Scope Logic in `int_enrollment_events`
The `int_enrollment_events` model was only checking:
- ✅ Tenure >= 1 year
- ✅ Not already enrolled
- ✅ Hire date cutoff (after implementation)
- ❌ **MISSING**: Scope check for `"new_hires_only"` vs `"all_eligible_employees"`

### Root Cause #2: Configuration Logic Issue
Original configuration was double-filtering:
- `scope: "new_hires_only"` → Only employees hired on/after `2025-01-01` (simulation year)
- `hire_date_cutoff: "2025-01-01"` → Only employees hired on/after `2025-01-01`

This meant both filters were doing the same thing, and with baseline workforce containing pre-2025 employees, **nobody was eligible**.

### Root Cause #3: Data Mismatch
- **Event data**: `EMP_2024_000010` (the problematic employee)
- **Baseline data**: `EMP_2024_000345` with hire date `2017-12-26`
- These are different employees, making direct comparison difficult

---

## Current Implementation Status

### Fixed Components ✅
1. **Configuration**: Added `hire_date_cutoff` to YAML and dbt variables
2. **Model Logic**: All enrollment models now include hire date cutoff filtering
3. **Orchestration**: Both orchestrators pass enrollment config to dbt
4. **Jinja Logic**: Proper null-safe handling with `{% if var(...) %}` blocks
5. **Testing**: Added dbt tests for hire date cutoff validation

### Current Configuration ⚠️
```yaml
scope: "all_eligible_employees"
hire_date_cutoff: "2020-01-01"
```

### Current Problem ❌
**Still no enrollment events being generated** despite the configuration appearing correct.

---

## Debugging Analysis Performed

### SQL Logic Tests
Created multiple analysis models to test:
1. **Eligibility breakdown** - Check each filter individually
2. **Configuration combinations** - Test different scope/cutoff combinations
3. **Employee-specific queries** - Look for specific problem employees
4. **Realistic config tests** - Test with various cutoff dates

### Key SQL Logic
```sql
-- Current eligibility check in int_enrollment_events.sql
CASE
  WHEN current_tenure >= 1
    AND employee_enrollment_date IS NULL
    AND (
      {% if var("auto_enrollment_hire_date_cutoff", null) %}
        employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff") }}'::DATE
      {% else %}
        true
      {% endif %}
    )
    AND (
      -- Scope check: new_hires_only vs all_eligible_employees
      CASE
        WHEN '{{ var("auto_enrollment_scope", "new_hires_only") }}' = 'new_hires_only'
          THEN employee_hire_date >= CAST(simulation_year || '-01-01' AS DATE)
        WHEN '{{ var("auto_enrollment_scope", "new_hires_only") }}' = 'all_eligible_employees'
          THEN true
        ELSE false
      END
    )
    THEN true
  ELSE false
END as is_eligible
```

---

## Outstanding Questions

### Data Questions
1. **What is the actual hire date for `EMP_2024_000010`?** (Need to query baseline data)
2. **How many employees should be eligible with current config?** (Need count verification)
3. **Are there any employees with hire dates after 2020-01-01?** (Verify data exists)

### Configuration Questions
1. **What is the intended behavior?**
   - Exclude employees hired before specific date?
   - Only auto-enroll new hires in current simulation year?
   - Combination of both?

2. **What should the realistic configuration be?**
   - Current: `scope: "all_eligible_employees"` + `hire_date_cutoff: "2020-01-01"`
   - Alternative: `scope: "new_hires_only"` + `hire_date_cutoff: null`

### Technical Questions
1. **Are the dbt variables being passed correctly from orchestrator?** (Need variable tracing)
2. **Is the baseline workforce data correct for the simulation year?** (2025 simulation using what baseline?)
3. **Are there any database locks or caching issues?** (Several failed dbt runs due to locks)

---

## Next Steps for Investigation

### Immediate Actions
1. **Query baseline workforce data** - Find actual employees and hire dates
2. **Trace variable passing** - Verify orchestrator → dbt variable flow
3. **Test with simple configuration** - Try just one filter at a time
4. **Check enrollment events count** - Verify if any events are generated

### Data Verification
```sql
-- Check baseline workforce for eligible employees
SELECT
  COUNT(*) as total_employees,
  COUNT(CASE WHEN employee_hire_date >= '2020-01-01' THEN 1 END) as after_cutoff,
  COUNT(CASE WHEN employee_enrollment_date IS NULL THEN 1 END) as not_enrolled,
  COUNT(CASE WHEN current_tenure >= 1 THEN 1 END) as tenure_eligible
FROM int_baseline_workforce
WHERE employment_status = 'active' AND simulation_year = 2025;
```

### Configuration Testing
Test these configurations individually:
1. **No filters**: All eligible employees
2. **Hire date cutoff only**: `hire_date_cutoff: "2015-01-01"`, `scope: "all_eligible_employees"`
3. **Scope only**: `scope: "new_hires_only"`, `hire_date_cutoff: null`

---

## Files Modified

### Configuration
- `config/simulation_config.yaml` - Added `hire_date_cutoff` field
- `dbt/dbt_project.yml` - Added `auto_enrollment_hire_date_cutoff` variable

### dbt Models
- `dbt/models/intermediate/int_auto_enrollment_window_determination.sql`
- `dbt/models/intermediate/int_enrollment_decision_matrix.sql`
- `dbt/models/intermediate/int_enrollment_events.sql`
- `dbt/models/intermediate/schema.yml` - Added tests

### Orchestration
- `orchestrator_mvp/core/multi_year_orchestrator.py`
- `orchestrator_mvp/core/common_workflow.py`

---

## Test Commands

```bash
# Test enrollment events generation
dbt run --select int_enrollment_events --vars '{"simulation_year": 2025, "auto_enrollment_hire_date_cutoff": "2020-01-01", "auto_enrollment_scope": "all_eligible_employees"}'

# Debug eligibility
dbt run --select debug_enrollment_eligibility --vars '{"simulation_year": 2025, "auto_enrollment_hire_date_cutoff": "2020-01-01", "auto_enrollment_scope": "all_eligible_employees"}'

# Check baseline data
dbt run-operation run_query --args '{query: "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = '\''active'\'' AND simulation_year = 2025"}'
```

---

## Issue Status: **UNRESOLVED**

The hire date cutoff logic has been implemented but enrollment events are still not being generated. Need to investigate why the eligibility logic is not identifying any eligible employees despite what appears to be correct configuration.
