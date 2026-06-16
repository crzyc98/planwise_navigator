# Quickstart: Implementing the Tenure Match Tier Bug Fixes

**Branch**: `098-tenure-match-tier-bug`
**Date**: 2026-06-15

## Changes Required

Four targeted edits across three files. All are 1–2 line changes.

---

## 1. `planalign_orchestrator/config/export.py`

After line 36 (the existing `start_year` export), add:

```python
# existing line
dbt_vars["start_year"] = int(cfg.simulation.start_year)
# add immediately after:
dbt_vars["simulation_start_year"] = int(cfg.simulation.start_year)
```

**Why**: Exports the alias so all models — regardless of which key name they use — receive the
correct simulation start year.

---

## 2. `dbt/models/intermediate/int_workforce_snapshot_optimized.sql`

Change line 13:

```sql
-- BEFORE:
{% set start_year = var('simulation_start_year', 2025) | int %}

-- AFTER:
{% set start_year = var('start_year', 2025) | int %}
```

**Why**: The primary root cause. Using the canonical var name ensures the Year-1 branch (`int_baseline_workforce`) is taken when `simulation_year == start_year`.

---

## 3. `dbt/models/intermediate/int_workforce_pre_enrollment.sql`

Change line 41:

```sql
-- BEFORE:
CASE WHEN simulation_year = {{ var('simulation_start_year', 2025) }} THEN true ELSE false END as is_from_census,

-- AFTER:
CASE WHEN simulation_year = {{ var('start_year', 2025) }} THEN true ELSE false END as is_from_census,
```

**Why**: Same var-name bug in a model that is part of the simulation workflow (EVENT_GENERATION stage). Affects the `is_from_census` flag in Year 1.

---

## 4. `planalign_cli/commands/simulate.py`

Three identical edits in `_print_config_summary()`:

```python
# BEFORE (all three occurrences at lines ~218, ~228, ~238):
f"{t.get('min_years', 0)}–{t.get('max_years', '∞')} yrs"

# AFTER:
f"{t.get('min_years', 0)}–{t.get('max_years') or '∞'} yrs"
```

**Why**: `dict.get(key, default)` returns `None` when the key exists but holds `None`. Using
`or '∞'` correctly treats any falsy value as "no upper bound".

---

## Verification

```bash
# 1. Run fast unit tests
source .venv/bin/activate
pytest -m fast -x

# 2. Start a simulation with tenure-based match configured
planalign simulate 2025-2026 --verbose

# 3. Check Config Summary output — should show ∞, not None
# In the terminal output look for: "Tenure tiers: 0–5 yrs @ 100%, 5–10 yrs @ 100%, 10–∞ yrs @ 100%"

# 4. Verify match amounts in Year 1 vary by employee tenure
duckdb <path-to-scenario>/simulation.duckdb \
  "SELECT applied_years_of_service, COUNT(*) n, ROUND(AVG(match_amount),0) avg_match
   FROM int_employee_match_calculations
   GROUP BY 1 ORDER BY 1"
# Expected: multiple distinct values of applied_years_of_service (not all 0)
```

---

## Test Coverage

- `tests/test_analytics_service.py` — existing; run to confirm no regressions
- New fast unit test for `export.py`: assert both `start_year` and `simulation_start_year` appear
  in the exported dbt vars dict
- New fast unit test for `_print_config_summary()`: assert `None` tier bound renders as `∞`
