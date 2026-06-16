# Data Model: Tenure Match Tier Bug Fixes

**Branch**: `098-tenure-match-tier-bug`
**Date**: 2026-06-15

## No Schema Changes

Both fixes are logic-only. No database tables are added, removed, or altered. No migration is
needed.

---

## Affected Data Flows

### Bug 1: Workforce Snapshot → Match Calculations pipeline (Year 1)

```
int_baseline_workforce
  └─► int_workforce_snapshot_optimized  ← FIXED: now takes Year-1 branch correctly
        └─► int_employee_match_calculations
              └─► fct_employer_match_events
```

**Before fix**: `int_workforce_snapshot_optimized` took the Year 2+ branch in Year 1, reading from
`int_active_employees_prev_year_snapshot` (empty on fresh runs). Match calculations received
`current_tenure = NULL` → COALESCE to 0 → lowest tier for all.

**After fix**: Year 1 correctly reads `int_baseline_workforce.current_tenure` (accurate decimal
tenure from census hire dates). Match calculations receive correct tenure values.

### Key entities and their `current_tenure` sources

| Model | Year 1 tenure source | Year 2+ tenure source |
|---|---|---|
| `int_baseline_workforce` | `calculate_tenure(hire_date, Dec 31, simulation_year)` | N/A |
| `int_workforce_snapshot_optimized` | `int_baseline_workforce.current_tenure` (**after fix**) | `fct_workforce_snapshot.current_tenure + 1` |
| `fct_workforce_snapshot` | `int_baseline_workforce.current_tenure` (direct, not via snapshot) | `int_active_employees_prev_year_snapshot.current_tenure + 1` |
| `int_employee_match_calculations` | `int_workforce_snapshot_optimized.current_tenure` | same |

### Tenure tier resolution (unchanged)

| Field | Type | Description |
|---|---|---|
| `years_of_service` | INT | `FLOOR(COALESCE(snap.current_tenure, 0))::INT` |
| `tier_rate` | DECIMAL | Match rate for employee's tier (e.g., 1.0 for 100%) |
| `tier_max_deferral_pct` | DECIMAL | Max deferral % for employee's tier (e.g., 0.06) |
| `applied_years_of_service` | INT | Alias of `years_of_service` in final output |
| `formula_type` | VARCHAR | `'tenure_based'` for this mode |

### Bug 2: Config Summary display (no data-model impact)

Bug 2 is a display-only fix in the CLI layer. The `max_years` field in tier dicts is unchanged; only
the string formatting expression is corrected.

| Field | Stored as | Displayed before fix | Displayed after fix |
|---|---|---|---|
| `max_years` (open-ended) | `None` (Python) / `null` (JSON) | `"10–None yrs"` | `"10–∞ yrs"` |
| `max_years` (bounded) | integer, e.g. `5` | `"0–5 yrs"` | `"0–5 yrs"` (unchanged) |
