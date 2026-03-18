# Data Model: Fix Auto Enrollment Runs Despite Being Disabled

**Feature Branch**: `074-fix-auto-enroll-disabled`
**Date**: 2026-03-18

## Entities

### DC Plan Configuration (existing — no schema changes)

| Field | Type | Description |
|-------|------|-------------|
| auto_enroll | boolean | Master toggle for auto-enrollment feature |
| auto_enroll_scope | string | "all_eligible_employees" or "new_hires_only" |
| default_deferral_percent | decimal | Default deferral rate for auto-enrolled employees |
| auto_enrollment_window_days | integer | Days after hire for auto-enrollment eligibility |

### dbt Variables (existing — no new variables)

| Variable | Type | Default | Used In |
|----------|------|---------|---------|
| `auto_enrollment_enabled` | boolean | `true` | `int_auto_enrollment_window_determination` (correct), `int_enrollment_events` (MISSING), `int_proactive_voluntary_enrollment` (MISSING) |
| `auto_enrollment_scope` | string | `"all_eligible_employees"` | `int_enrollment_events` |
| `auto_enrollment_default_deferral_rate` | float | `0.02` | `deferral_rate_macros` |

### Enrollment Event (existing — no schema changes)

| Field | Type | Description |
|-------|------|-------------|
| employee_id | string | Employee identifier |
| event_type | string | "DC_PLAN_ENROLLMENT" |
| enrollment_category | string | "auto_enrollment" or "voluntary" |
| is_auto_enrollment_row | boolean | Flag set by enrollment model |
| simulation_year | integer | Year of the event |

## State Transitions

No new state transitions. The fix ensures the existing `auto_enrollment_enabled = false` state correctly prevents auto-enrollment event generation.

```
auto_enrollment_enabled: true  → Auto-enrollment events generated per scope
auto_enrollment_enabled: false → Zero auto-enrollment events; voluntary enrollment unaffected
```

## Data Flow (corrected)

```
DC Plan Config (UI)
  → scenario.config_overrides["dc_plan"]["auto_enroll"]
    → SimulationConfig.enrollment.auto_enrollment.enabled
      → dbt var: auto_enrollment_enabled
        → int_auto_enrollment_window_determination (already gates ✅)
        → int_enrollment_events (NEEDS gate ❌ → fix)
        → int_proactive_voluntary_enrollment (NEEDS gate ❌ → fix)
```
