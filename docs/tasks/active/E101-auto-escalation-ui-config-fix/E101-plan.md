# E101: Fix Auto-Escalation UI Config Not Being Applied

## Problem Summary

User ran 3 scenarios with different auto-escalation settings through the UI:
1. No auto-escalate
2. Auto-escalate for new hires after 1/1/2026
3. Auto-escalate for all eligible employees

All 3 scenarios produced the **same number of employees with escalation** because the UI configuration is being overwritten by legacy YAML settings.

## Root Cause Analysis

### The Bug Location
In `/workspace/planalign_orchestrator/config/export.py`, the function `to_dbt_vars()` (line 645) calls export functions in this order:

```python
dbt_vars.update(_export_enrollment_vars(cfg))  # Line 657 - Sets dc_plan (UI) settings
dbt_vars.update(_export_legacy_vars(cfg))      # Line 658 - OVERWRITES with legacy YAML!
```

### Configuration Flow
1. **UI** sends `dc_plan.escalation_hire_date_cutoff` (e.g., "2026-01-01")
2. **API** stores in `scenario.config_overrides`
3. **Config Merge** combines workspace `base_config` + scenario `config_overrides`
4. **Merged config** contains BOTH:
   - `dc_plan.escalation_hire_date_cutoff` = "2026-01-01" (UI setting)
   - `deferral_auto_escalation.hire_date_cutoff` = "2020-01-01" (from base YAML)
5. **to_dbt_vars()** exports both, but legacy wins because it runs LAST

### Affected Variables
| UI Field | dc_plan key | dbt var | Legacy YAML key |
|----------|-------------|---------|-----------------|
| dcAutoEscalation | auto_escalation | deferral_escalation_enabled | deferral_auto_escalation.enabled |
| dcEscalationRate | escalation_rate_percent | deferral_escalation_increment | deferral_auto_escalation.increment_amount |
| dcEscalationCap | escalation_cap_percent | deferral_escalation_cap | deferral_auto_escalation.maximum_rate |
| dcEscalationEffectiveDay | escalation_effective_day | deferral_escalation_effective_mmdd | deferral_auto_escalation.effective_day |
| dcEscalationDelayYears | escalation_delay_years | deferral_escalation_delay_years | deferral_auto_escalation.first_escalation_delay_years |
| **dcEscalationHireDateCutoff** | **escalation_hire_date_cutoff** | **deferral_escalation_hire_date_cutoff** | **deferral_auto_escalation.hire_date_cutoff** |

## Fix Implementation

### Recommended: Swap Export Order
Change the order in `to_dbt_vars()` so UI (dc_plan) settings take precedence:

**File**: `/workspace/planalign_orchestrator/config/export.py`
**Lines**: 654-662

```python
def to_dbt_vars(cfg: "SimulationConfig") -> Dict[str, Any]:
    dbt_vars: Dict[str, Any] = {}
    dbt_vars.update(_export_simulation_vars(cfg))
    dbt_vars.update(_export_legacy_vars(cfg))       # Run legacy FIRST (lowest priority)
    dbt_vars.update(_export_enrollment_vars(cfg))   # Run UI export LAST (highest priority)
    dbt_vars.update(_export_employer_match_vars(cfg))
    dbt_vars.update(_export_compensation_vars(cfg))
    dbt_vars.update(_export_threading_vars(cfg))
    dbt_vars.update(_export_core_contribution_vars(cfg))
    return dbt_vars
```

**Rationale:**
- Minimal code change (swap 2 lines)
- Clear semantic: "UI settings override YAML settings"
- Consistent with principle that scenario-specific settings override defaults
- Backward compatible: YAML-only scenarios still work

## Validation SQL

After fix, run this query to verify escalation behavior differs by scenario:

```sql
SELECT
    scenario_id,
    COUNT(*) as escalation_event_count,
    MIN(employee_hire_date) as earliest_hire,
    MAX(employee_hire_date) as latest_hire
FROM fct_yearly_events
WHERE event_type = 'deferral_escalation'
GROUP BY scenario_id;
```
