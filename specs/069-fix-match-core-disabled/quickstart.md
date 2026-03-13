# Quickstart: Fix DC Plan Match/Core Contributions When Disabled

**Feature**: 069-fix-match-core-disabled
**Estimated Changes**: 3 files, ~20 lines added/modified

## The Bug

The DC Plan UI has a "Match Enabled" toggle. Turning it off sends `match_enabled: false` to the API, but the orchestrator config export (`export.py`) never reads this field. The dbt match calculation model has no master on/off gate. Result: match is always calculated regardless of the toggle.

## Fix Summary

Two changes, mirroring the working `employer_core_enabled` pattern:

### 1. Config Export (`planalign_orchestrator/config/export.py`)

In `_export_employer_match_vars()`, inside the `dc_plan` processing block (~line 445), add:

```python
# Read match_enabled from dc_plan UI config
match_enabled = dc_plan_dict.get("match_enabled")
if match_enabled is not None:
    dbt_vars["employer_match_enabled"] = bool(match_enabled)
```

### 2. dbt Match Model (`dbt/models/intermediate/events/int_employee_match_calculations.sql`)

Add variable definition after line 73:

```sql
-- Master match enable/disable flag (mirrors employer_core_enabled pattern)
{% set employer_match_enabled = var('employer_match_enabled', true) %}
```

Wrap the `final_match` CTE output (lines 331-392) with an enabled gate. In the final SELECT, gate `employer_match_amount`:

```sql
{% if not employer_match_enabled %}
    0 AS employer_match_amount,
    0 AS capped_match_amount,
    'disabled' AS match_status,
    0 AS uncapped_match_amount,
    FALSE AS match_cap_applied,
{% else %}
    -- existing calculation logic unchanged
{% endif %}
```

## Verification

```bash
# Run simulation with match disabled via CLI
cd dbt
dbt run --select int_employee_match_calculations \
  --vars '{"simulation_year": 2025, "employer_match_enabled": false}' \
  --threads 1

# Verify all match amounts are $0
duckdb simulation.duckdb "SELECT COUNT(*), SUM(employer_match_amount) FROM int_employee_match_calculations WHERE simulation_year = 2025"
# Expected: count=N, sum=0.00

# Verify match enabled produces normal results (regression check)
dbt run --select int_employee_match_calculations \
  --vars '{"simulation_year": 2025, "employer_match_enabled": true}' \
  --threads 1

duckdb simulation.duckdb "SELECT COUNT(*), SUM(employer_match_amount) FROM int_employee_match_calculations WHERE simulation_year = 2025"
# Expected: count=N, sum>0
```

## Files to Change

| File | Change | Lines |
|------|--------|-------|
| `planalign_orchestrator/config/export.py` | Read `match_enabled` from dc_plan, export as `employer_match_enabled` | ~3 lines added after line 445 |
| `dbt/models/intermediate/events/int_employee_match_calculations.sql` | Add variable + master gate | ~10 lines added/modified |
| `tests/test_config_export.py` | Add test for `employer_match_enabled` export | ~15 lines |
