# E101: Context and Key Files

## Last Updated
2024-12-11

## Key Files

### Primary File to Modify
- `/workspace/planalign_orchestrator/config/export.py` - Lines 654-662 (`to_dbt_vars()` function)

### Related Files (Read-Only Context)
- `/workspace/planalign_studio/components/ConfigStudio.tsx` - UI form fields (lines 230-265, 993-1000)
- `/workspace/planalign_api/storage/workspace_storage.py` - Config merge logic (line 407-440)
- `/workspace/dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql` - Uses the dbt vars

## Configuration Flow Trace

```
UI (ConfigStudio.tsx)
  ↓ dcEscalationHireDateCutoff
API (scenarios.py)
  ↓ config_overrides.dc_plan.escalation_hire_date_cutoff
Storage (workspace_storage.py)
  ↓ _deep_merge(base_config, config_overrides)
Simulation Service
  ↓ writes merged config.yaml
CLI → Orchestrator
  ↓ load_simulation_config()
export.py
  ↓ to_dbt_vars() - BUG: legacy overwrites dc_plan
dbt models
  ↓ var('deferral_escalation_hire_date_cutoff')
int_deferral_rate_escalation_events.sql
```

## Key Decisions
1. **Fix approach**: Swap export order rather than conditional checks (simpler, cleaner)
2. **Priority**: UI (dc_plan) settings override legacy YAML settings
3. **Backward compatibility**: YAML-only workflows unaffected (legacy exports first, UI exports second)

## Test Scenarios
1. UI sets hire_date_cutoff to 2026-01-01, base YAML has 2020-01-01 → Should use 2026-01-01
2. UI doesn't set hire_date_cutoff, base YAML has 2020-01-01 → Should use 2020-01-01
3. Neither sets hire_date_cutoff → Should use dbt default (none)
