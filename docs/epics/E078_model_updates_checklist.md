# E078 Model Update Checklist

## Epic Context
When `event_mode = 'polars'`, SQL event models (`int_*_events`, `int_employer_eligibility`) are **skipped entirely**. Models that reference these tables fail with "table does not exist" errors. This checklist tracks all models that need to be updated to read from `fct_yearly_events` instead.

## Pattern to Apply
Replace: `FROM {{ ref('int_*_events') }}` or `FROM {{ ref('int_employer_eligibility') }}`
With: `FROM {{ ref('fct_yearly_events') }} WHERE event_type = '...' AND simulation_year = {{ var('simulation_year') }}`

## Event Type Mapping
- `int_hiring_events` → `WHERE event_type = 'hire'`
- `int_termination_events` → `WHERE event_type = 'termination'`
- `int_promotion_events` → `WHERE event_type = 'promotion'`
- `int_merit_events` → `WHERE event_type = 'raise'` (or 'merit' if exists)
- `int_enrollment_events` → `WHERE event_type IN ('enrollment', 'enrollment_change')`
- `int_deferral_rate_escalation_events` → `WHERE event_type IN ('enrollment_change', 'deferral_escalation')`
- `int_synthetic_baseline_enrollment_events` → `WHERE event_type = 'enrollment'` (and filter for synthetic/baseline)
- `int_new_hire_termination_events` → `WHERE event_type = 'termination' AND event_details LIKE '%new_hire%'`
- `int_employer_eligibility` → `WHERE event_type = 'eligibility_determination'` (if tracked as events)
- `int_workforce_active_for_events` → Check if model exists in Polars mode; may need alternative approach

---

## Models Already Fixed (Before E078)
- ✅ **int_enrollment_state_accumulator.sql** → Reads from `fct_yearly_events` with `event_type IN ('enrollment', 'enrollment_change')`

---

## Models Needing Updates (Intermediate Layer)

### 1. int_proactive_voluntary_enrollment.sql
- **Current Reference**: Line 47: `FROM {{ ref('int_hiring_events') }}`
- **CTE Name**: `new_hires_current_year`
- **Event Type**: `event_type = 'hire'`
- **Status**: ❌ Not started

### 2. int_deferral_rate_state_accumulator_v2.sql
- **Current References**:
  - Line 76: `FROM {{ ref('int_deferral_rate_escalation_events') }}`
  - Line 134: `FROM {{ ref('int_synthetic_baseline_enrollment_events') }}`
- **CTE Names**: `current_year_escalation_events`, `baseline_enrollment_source`
- **Event Types**:
  - Escalation events: `event_type IN ('enrollment_change', 'deferral_escalation')`
  - Baseline enrollment: `event_type = 'enrollment'` (with filter for baseline source)
- **Status**: ⚠️ Epic claims fixed, but references still found - needs verification

### 3. int_deferral_rate_state_accumulator.sql
- **Current References**:
  - Line 83: `FROM {{ ref('int_hiring_events') }}`
  - Line 116: `FROM {{ ref('int_deferral_rate_escalation_events') }}`
  - Line 128: `FROM {{ ref('int_enrollment_events') }}`
- **CTE Names**: `current_year_hires`, `all_escalation_events`, `enrollment_source`
- **Event Types**:
  - Hires: `event_type = 'hire'`
  - Escalations: `event_type IN ('enrollment_change', 'deferral_escalation')`
  - Enrollments: `event_type IN ('enrollment', 'enrollment_change')`
- **Status**: ❌ Not started

### 4. int_deferral_escalation_state_accumulator.sql
- **Current Reference**: Line 54: `FROM {{ ref('int_deferral_rate_escalation_events') }}`
- **CTE Name**: `escalation_events`
- **Event Type**: `event_type IN ('enrollment_change', 'deferral_escalation')`
- **Status**: ❌ Not started

### 5. int_employer_core_contributions.sql
- **Current Reference**: Line 172: `FROM {{ ref('int_employer_eligibility') }}`
- **CTE Name**: `eligibility_check`
- **Event Type**: `event_type = 'eligibility_determination'` (or read from snapshot if not tracked as events)
- **Status**: ❌ Not started
- **Note**: May need special handling if eligibility is not tracked as events in Polars mode

### 6. int_workforce_pre_enrollment.sql
- **Current Reference**: Line 48: `FROM {{ ref('int_workforce_active_for_events') }}`
- **CTE Name**: Main select
- **Event Type**: N/A - This references a foundation model, not an event model
- **Status**: ❌ Needs investigation - `int_workforce_active_for_events` may still exist in Polars mode
- **Note**: Tagged with 'foundation' and 'event_generation' - verify if model exists in Polars mode

---

## Models in Events Directory (Event Generators - No Updates Needed)
These models are only run in SQL mode and are skipped entirely in Polars mode:
- ✅ int_deferral_rate_escalation_events.sql (in events/)
- ✅ int_employee_contributions.sql (in events/)
- ✅ int_employee_match_calculations.sql (in events/) - **NOTE**: This model references `int_employer_eligibility` at line 97, needs review
- ✅ int_hiring_events.sql (in events/)
- ✅ int_merit_events.sql (in events/)
- ✅ int_new_hire_termination_events.sql (in events/)
- ✅ int_promotion_events.sql (in events/)
- ✅ int_synthetic_baseline_enrollment_events.sql (in events/)
- ✅ int_termination_events.sql (in events/)
- ✅ int_enrollment_events.sql (tagged EVENT_GENERATION)
- ✅ int_employer_eligibility.sql (tagged EVENT_GENERATION)

---

## Models Referencing int_employee_match_calculations
**Special Case**: `int_employee_match_calculations.sql` is in the events/ directory (event generator) but references `int_employer_eligibility`:
- Line 97: `LEFT JOIN {{ ref('int_employer_eligibility') }}`
- **Status**: ❓ Needs investigation - Should this model also be updated, or is it okay since it's only run in SQL mode?

---

## Validation/Analysis Models (Lower Priority - Can Skip for Now)
- validate_s042_01_source_of_truth_fix.sql
- validate_enrollment_deferral_consistency_v2.sql
- validate_escalation_bug_fix.sql (in analysis/)
- test_census_enrollment_events_completeness.sql (in analysis/)
- data_quality_census_enrollment_audit_trail.sql (in analysis/)
- And others in analysis/ and data_quality/ directories

---

## Marts Models That May Need Updates
- **fct_yearly_events.sql** - Already handles both SQL and Polars modes ✅
- **fct_workforce_snapshot.sql** - May reference event models, needs verification ❓
- **dq_new_hire_termination_match_validation.sql** - References event models, lower priority ⚠️

---

## Testing Procedure for Each Model

After updating each model:
```bash
cd dbt

# Test individual model
dbt run --select <model_name> --vars "simulation_year: 2025" --threads 1

# Verify output
duckdb simulation.duckdb "SELECT COUNT(*) FROM <model_name> WHERE simulation_year = 2025"

# Update checklist with ✅
```

---

## Summary
- **Total Models Identified**: 6 intermediate models + 1 investigation needed
- **Already Fixed**: 1 model (int_enrollment_state_accumulator)
- **Needs Verification**: 1 model (int_deferral_rate_state_accumulator_v2 - claimed fixed but references found)
- **Needs Investigation**: 2 models (int_workforce_pre_enrollment, int_employee_match_calculations)
- **Clear Updates Needed**: 4 models

---

**Last Updated**: 2025-10-10
**Epic**: E078 Complete Polars Mode Integration
**Story**: E078-01 Model Identification Complete
