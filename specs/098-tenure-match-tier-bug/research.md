# Research: Tenure Match Tier Bug Fixes

**Branch**: `098-tenure-match-tier-bug`
**Date**: 2026-06-15

## Summary of Findings

Both bugs have confirmed root causes, verified through direct database queries and code inspection.
No NEEDS CLARIFICATION items remain.

---

## Bug 1: Year 1 Lowest-Tier Assignment

### Finding: var name mismatch between exporter and dbt model

**Decision**: Fix by exporting `simulation_start_year` alias AND renaming the var reference in
`int_workforce_snapshot_optimized`.

**Rationale**: The primary model (`int_workforce_snapshot_optimized`) uses
`var('simulation_start_year', 2025)` while `export.py` exports `"start_year"`. All other dbt models
in the project use `var('start_year', 2025)` — the snapshot model was written with a non-standard
key. Exporting both names ensures models using either name receive the correct value.

**Evidence**:
- `export.py:35-36`: `dbt_vars["start_year"] = int(cfg.simulation.start_year)`
- `int_workforce_snapshot_optimized.sql:13`: `var('simulation_start_year', 2025)` ← wrong key
- All other `start_year` usages across 16+ models use `var('start_year', 2025)`
- DuckDB query confirmed: `fct_employer_match_events.match_percentage_of_comp` max = 0.06 for Year
  2026 (all employees capped at lowest tier), vs 0.10 for Year 2027 (correct multi-tier assignment)

**Alternatives considered**:
- Fix only the model (rename var): sufficient for Year 1 bug, but `simulation_start_year` in other
  models (non-workflow) would still fail → dual export is safer
- Fix only the exporter (add alias export): fixes runtime without touching dbt model, but leaves
  non-standard naming in place → combine both for long-term clarity

### Finding: secondary models with same bug

Three models use `simulation_start_year` instead of `start_year`:
1. `int_workforce_pre_enrollment.sql:41` — **in the workflow** (EVENT_GENERATION stage, line 139 of
   `workflow.py`). Affects `is_from_census` flag logic in Year 1. Should be fixed.
2. `int_active_employees_by_year.sql:86` — NOT in the standard simulation workflow. Low priority.
3. `int_snapshot_base.sql:12` — NOT in the standard simulation workflow AND has no default value
   (would raise a `dbt.exceptions.UndefinedVariableError` if run standalone). Low priority but risky.

**Decision**: Fix 1 and 2 in this PR. Leave 3 (not in workflow, separate concern).

### Finding: `fct_workforce_snapshot` is immune to Bug 1

`fct_workforce_snapshot` reads from `int_baseline_workforce` directly (not via
`int_workforce_snapshot_optimized`), so it always has correct tenure for all years. This is why
Year 2+ match calculations work: they read `fct_workforce_snapshot.current_tenure + 1` via
`int_active_employees_prev_year_snapshot`, bypassing the broken snapshot model for Year 1.

---

## Bug 2: `None` Instead of `∞`

### Finding: Python `dict.get()` falsy-value gotcha

**Decision**: Replace `t.get('max_years', '∞')` with `t.get('max_years') or '∞'`.

**Rationale**: `dict.get(key, default)` only returns `default` when the key is **absent** from the
dict. When `max_years: null` is stored in the scenario JSON (parsed as Python `None`), the key IS
present with value `None` → `.get()` returns `None`. Using `or '∞'` treats any falsy value
(including `None`, `0`, empty string) as "not set".

**Edge cases**: `max_years=0` would also display as `∞`, but a tier starting at 0 years with a max
of 0 years is invalid configuration and cannot be produced by the UI. The `or` form is safe.

**Evidence**:
- Scenario JSON: `{"min_years": 10, "max_years": null, "match_rate": 1, "max_deferral_pct": 0.1}`
- Python `{"max_years": None}.get("max_years", "∞")` → `None` (confirmed)
- Simulation log (2026-06-15T23:32:05): `10–None yrs @ 100%`

**Affected lines**: `simulate.py:218, 228, 238` (tenure-based, graded-by-service, points-based
modes — all three use the same pattern in `_print_config_summary()`).

---

## Testing Strategy

### Bug 1 verification

The existing `tests/test_analytics_service.py` tests analytics queries. A new test that:
1. Creates a scenario with tenure-based tiers (0–5: 6%, 5–10: 8%, 10+: 10%)
2. Seeds employees with tenure 3, 7, 12 years
3. Runs Year 1 simulation
4. Asserts that `int_employee_match_calculations.applied_years_of_service` matches actual tenure
5. Asserts that employees with 12 years get `tier_max_deferral_pct = 0.10`

This test requires an integration setup. Existing `pytest -m fast` tests verify correct Python code
paths without running dbt. The simplest verifiable fast test: assert `export.py` now emits both
`start_year` and `simulation_start_year` vars.

### Bug 2 verification

Unit test for `_print_config_summary()` output: configure a mock tier with `max_years=None` and
assert the output contains `∞`, not `None`.
