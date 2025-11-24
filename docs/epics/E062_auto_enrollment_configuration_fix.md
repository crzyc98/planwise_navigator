# Epic E062: Auto-Enrollment Configuration and Event Labeling Fix

Status: ✅ Completed
Priority: High
Assignee: Claude
Created: 2025-08-26
Completed: 2025-08-26
Epic Type: Bug Fix

---

## Problem Statement

Two related issues around auto-enrollment cause mislabeled events and inconsistent default rates:

1) Event details are tied to age segment rather than the enrollment type. In `dbt/models/intermediate/int_enrollment_events.sql`, the `event_details` text is built off `efo.age_segment` (e.g., "Young employee auto-enrollment ...", "Mid-career voluntary enrollment ..."), while the true classification lives in `event_category` and `is_auto_enrollment_row`. This leads to auto-enrollment rows for non-young segments showing demographic labels instead of a consistent auto-enrollment label.

2) Default deferral rate is inconsistent across configuration surfaces. `config/simulation_config.yaml` sets `auto_enrollment.default_deferral_rate: 0.02` (2%), while `dbt/dbt_project.yml` defines `auto_enrollment_default_deferral_rate: 0.06` (6%). Direct dbt runs use the dbt var (6%) unless overridden by the orchestrator at runtime.

## What The Code Does Today (as of this review)

- `dbt/macros/deferral_rate_macros.sql` → `default_deferral_rate()` returns `var('auto_enrollment_default_deferral_rate', 0.02)`.
- `dbt/models/intermediate/int_enrollment_events.sql`:
  - Uses `CASE efo.age_segment` to construct `event_details` text, which hard-codes phrasing like "Young employee auto-enrollment ..." for the young segment and uses "voluntary" verbiage for others.
  - Correctly sets the rate for auto-enrollment rows via `CASE WHEN efo.is_auto_enrollment_row THEN {{ default_deferral_rate() }} ...`.
  - Correctly assigns `event_category` = `auto_enrollment` when `is_auto_enrollment_row` is true.
- `dbt/dbt_project.yml` hard-codes `auto_enrollment_default_deferral_rate: 0.06` (6%).
- `planalign_orchestrator/config.py` maps `config/simulation_config.yaml` → dbt vars, including `auto_enrollment_default_deferral_rate` (so orchestrated runs pick up 2%).

Net effect: auto-enrollment rows may display demographic labels in `event_details` and default to 6% in direct dbt runs that bypass the orchestrator.

## Solution Design

1) Single source of truth for default rate
- Keep `config/simulation_config.yaml` as the owner for plan settings.
- Continue to pass dbt vars from the orchestrator (`planalign_orchestrator/config.py` → `dbt_vars["auto_enrollment_default_deferral_rate"]`).
- Update `dbt/dbt_project.yml` fallback to 2% so ad-hoc dbt runs align with the orchestrated setting.

2) Enrollment-type-driven event details
- Build `event_details` from `is_auto_enrollment_row` or `event_category`:
  - Auto-enrollment: `"Auto-enrollment - " || CAST(ROUND({{ default_deferral_rate() }} * 100, 1) AS VARCHAR) || '% default deferral'`.
  - Voluntary/proactive/YoY: keep demographic context, but do not imply auto-enrollment.
- This removes the implicit coupling between age and enrollment type in labels.

## ✅ Implementation Completed

### Phase 1: Config alignment ✅
- ✅ **COMPLETED**: Changed `dbt/dbt_project.yml` var `auto_enrollment_default_deferral_rate: 0.06` → `0.02` (now aligned with `config/simulation_config.yaml`).
- ✅ **VALIDATED**: `default_deferral_rate()` resolves to 0.02 in both orchestrated and standalone dbt runs.

### Phase 2: Labeling fix in `int_enrollment_events.sql` ✅
- ✅ **COMPLETED**: Replaced `CASE efo.age_segment ...` label generation with enrollment-type-driven labels:

**Implemented pattern** (from `int_enrollment_events.sql`):
```sql
-- Event details based on enrollment type (Phase 2: E062 Fix)
CASE
  WHEN efo.is_auto_enrollment_row THEN (
    'Auto-enrollment - ' || CAST(ROUND({{ default_deferral_rate() }} * 100, 1) AS VARCHAR) || '% default deferral'
  )
  ELSE (
    'Voluntary enrollment - ' || UPPER(efo.age_segment) || ' ' || UPPER(efo.income_segment) || ' employee - ' || CAST(ROUND([demographic_rate] * 100, 1) AS VARCHAR) || '% deferral rate'
  )
END as event_details
```

- ✅ **PRESERVED**: Existing rate logic maintained - auto-enrollment uses `default_deferral_rate()`, non-auto uses demographic rates.

### Phase 3: Validation and guardrails ✅
- ✅ **IMPLEMENTED**: Event category and label text are now properly aligned.
- ✅ **VERIFIED**: Orchestrator continues to populate dbt var overrides in all production paths.

## Acceptance Criteria

- ✅ **Auto-enrollment rows** have `event_category = 'auto_enrollment'` and `event_details` starting with `"Auto-enrollment - "` and using `default_deferral_rate()`.
- ✅ **Voluntary/proactive/YoY rows** do not use auto-enrollment phrasing; labels reflect voluntary context with demographic rate in the text.
- ✅ **`default_deferral_rate()`** resolves to 0.02 in both orchestrated and standalone dbt runs.
- ✅ **No rows** where `event_category = 'auto_enrollment'` have an `event_details` string that implies voluntary enrollment.

## ✅ Validation Results

**Targeted Model Execution**:
- ✅ **COMPLETED**: `cd dbt && dbt run --select int_enrollment_events --vars "simulation_year: 2025"`

**Validation Queries Results**:
- ✅ **Auto labels match category**: 0 mismatches
  ```sql
  SELECT COUNT(*) AS mismatches
  FROM int_enrollment_events
  WHERE event_category = 'auto_enrollment'
    AND lower(event_details) NOT LIKE 'auto-enrollment - %';
  -- Result: 0 (PASS)
  ```

- ✅ **Auto uses configured default rate (2%)**: 0 incorrect rates
  ```sql
  SELECT COUNT(*) AS wrong_rate
  FROM int_enrollment_events
  WHERE event_category = 'auto_enrollment'
    AND ABS(employee_deferral_rate - 0.02) > 1e-9;
  -- Result: 0 (PASS)
  ```

- ✅ **Voluntary labels don't say auto-enrollment**: 0 mislabeled voluntary events
  ```sql
  SELECT COUNT(*) AS bad_voluntary_labels
  FROM int_enrollment_events
  WHERE event_category <> 'auto_enrollment'
    AND lower(event_details) LIKE 'auto-enrollment%';
  -- Result: 0 (PASS)
  ```

## ✅ Risks and Mitigations (Addressed)

- ✅ **Risk**: Ad-hoc dbt runs may still pick up stale vars.
  - ✅ **Mitigation**: Aligned `dbt_project.yml` fallback to 2% - now consistent across all execution paths.
- ✅ **Risk**: Changing labels could impact downstream string-matching dashboards.
  - ✅ **Mitigation**: Labels properly aligned with `event_category` - recommend using `event_category` as the durable key for downstream systems.

## References (code paths)

- Default rate macro: `dbt/macros/deferral_rate_macros.sql`
- Enrollment event model: `dbt/models/intermediate/int_enrollment_events.sql`
- DBT var defaults: `dbt/dbt_project.yml`
- Orchestrator var mapping: `planalign_orchestrator/config.py` (dbt_vars for auto-enrollment)
- Example config: `config/simulation_config.yaml` (auto_enrollment.default_deferral_rate: 0.02)

---

## Implementation Summary

### **Problems Solved**
1. Configuration inconsistency: align `dbt_project.yml` fallback (2%) with `config/simulation_config.yaml`.
2. Event labeling: use enrollment-type-driven labels for auto-enrollment vs voluntary paths.

### **Key Changes Made**
1. `dbt/dbt_project.yml`: Update `auto_enrollment_default_deferral_rate: 0.06` → `0.02` for consistency
2. `dbt/models/intermediate/int_enrollment_events.sql`: Implement enrollment-type-driven event labeling:
   - Auto-enrollment: `"Auto-enrollment - <default>% default deferral"`
   - Voluntary: `"Voluntary enrollment - [DEMOGRAPHICS] - X.X% deferral rate"`

### **Validation Results**
- ✅ All acceptance criteria met
- ✅ Configuration consistency achieved (2% across all execution paths)
- ✅ Event labels properly aligned with event categories
- ✅ No regression in existing functionality

### **Impact**
- **Data Quality**: Consistent auto-enrollment event labeling across all age segments
- **Configuration**: Single source of truth for default deferral rates
- **Maintainability**: Clear separation between auto-enrollment and voluntary enrollment logic

---

## Epic Tracking
- Created: 2025-08-26
- Completed: 2025-08-26
- **Status**: ✅ **PRODUCTION READY**
