# Implementation Plan: Tenure Match Tier Bug Fixes

**Branch**: `098-tenure-match-tier-bug` | **Date**: 2026-06-15 | **Spec**: [spec.md](spec.md)

## Summary

Fix two independent bugs in the tenure-based employer match feature: (1) all employees are assigned
the lowest match tier in Year 1 because `int_workforce_snapshot_optimized` reads the wrong dbt var
name for `start_year`, causing it to skip the baseline-workforce branch and return empty tenure
data; (2) the Config Summary panel displays `None` for open-ended tier upper bounds because
`dict.get('max_years', '∞')` returns the stored `None` rather than the fallback.

## Technical Context

**Language/Version**: Python 3.11 (CLI + orchestrator), SQL / Jinja2 (dbt-core 1.8.8 + dbt-duckdb 1.8.1)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, DuckDB 1.0.0, Pydantic v2
**Storage**: DuckDB (`simulation.duckdb` per scenario) — no schema changes needed
**Testing**: pytest (fast unit tests, integration), dbt tests
**Target Platform**: macOS dev / Linux server
**Project Type**: data-pipeline (dbt SQL) + CLI (Python)
**Constraints**: Must not alter correct Year 2+ tier assignment; existing tests must pass

## Root-Cause Analysis

### Bug 1 — Year 1 lowest-tier assignment

**Causal chain (confirmed via database query):**

1. `export.py:35-36` exports the simulation start year under the key `"start_year"`:
   ```python
   dbt_vars["start_year"] = int(cfg.simulation.start_year)
   ```

2. `int_workforce_snapshot_optimized.sql:13` reads it under a **different** key:
   ```sql
   {% set start_year = var('simulation_start_year', 2025) | int %}
   ```
   `simulation_start_year` is never exported → `start_year` defaults to **2025** regardless of the
   actual simulation start year.

3. For a run starting at Year 2026: `simulation_year == start_year` → `2026 == 2025` → **False**.
   The model takes the **else branch**, reading from `int_active_employees_prev_year_snapshot`
   instead of `int_baseline_workforce`.

4. `int_active_employees_prev_year_snapshot` reads `fct_workforce_snapshot WHERE simulation_year = 2025`.
   On a fresh run there is no 2025 data → **snapshot is empty for Year 1**.

5. `int_employee_match_calculations` LEFT JOINs to the empty snapshot → `snap.current_tenure = NULL`
   → `COALESCE(NULL, 0) = 0` → `years_of_service = 0` for every employee → **everyone lands in the
   lowest tenure tier** (0–5 years, 6% max deferral cap).

**Why Year 2+ works:** Year 2 (2027) reads `fct_workforce_snapshot WHERE simulation_year = 2026`.
That data exists because `fct_workforce_snapshot` reads directly from `int_baseline_workforce`
(not from the optimized snapshot), so it has correct tenure regardless of Bug 1. Year 2 snapshot is
therefore non-empty and correct.

**Secondary affected models (also use `simulation_start_year`):**
- `int_workforce_pre_enrollment.sql:41` — in the workflow; wrong branch logic for Year 1
- `int_active_employees_by_year.sql:86` — NOT in the main workflow
- `int_snapshot_base.sql:12` — NOT in the main workflow, and has no default (would error if run)

### Bug 2 — `None` instead of `∞` in Config Summary

`simulate.py` uses `t.get('max_years', '∞')` to display the upper bound of each tier. Python's
`dict.get(key, default)` only returns the default when the **key is absent**. When `max_years=None`
is explicitly stored in the dict, `get` returns `None` — not `'∞'`.

The scenario JSON stores the final tier as `{"min_years": 10, "max_years": null, ...}` (YAML `null`
becomes Python `None`). The key IS present with value `None` → fallback never fires.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| Cognitive complexity ≤ 15 | ✅ PASS | Both fixes are 1-line changes |
| Parameter limit ≤ 13 | ✅ PASS | No new functions introduced |
| No bare `except:` | ✅ PASS | No new exception handling |
| No dead code | ✅ PASS | No new code paths added |
| Return type hints match | ✅ PASS | No new functions |
| No CDN scripts in HTML | ✅ PASS | No frontend changes |
| No mutable defaults | ✅ PASS | No new Python functions |

## Project Structure

### Documentation (this feature)

```text
specs/098-tenure-match-tier-bug/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
dbt/models/intermediate/
└── int_workforce_snapshot_optimized.sql     # Bug 1 primary fix (line 13)

dbt/models/intermediate/
└── int_workforce_pre_enrollment.sql          # Bug 1 secondary fix (line 41)

planalign_cli/commands/
└── simulate.py                               # Bug 2 fix (lines 218, 228, 238)

planalign_orchestrator/config/
└── export.py                                 # Bug 1 hardening (export both var names)

tests/
└── test_analytics_service.py                 # May need new test for Bug 1 (Year 1 correct tier)
```

**Structure Decision**: Single-project. No new files required; all changes are targeted edits to
existing files.

## Implementation Plan

### Fix 1A — Primary: export `simulation_start_year` alias (export.py)

Add a second export alongside the existing `start_year` so all models — regardless of which key
name they use — receive the correct value:

```python
# planalign_orchestrator/config/export.py, after line 36
dbt_vars["simulation_start_year"] = int(cfg.simulation.start_year)
```

This is a hardening measure. The primary fix is 1B (rename the var in the model), but exporting
both ensures any other model that uses `simulation_start_year` also works correctly.

### Fix 1B — Primary: rename var reference in `int_workforce_snapshot_optimized` (dbt model)

```sql
-- Line 13: BEFORE
{% set start_year = var('simulation_start_year', 2025) | int %}

-- Line 13: AFTER
{% set start_year = var('start_year', 2025) | int %}
```

This is the minimal fix for the confirmed root cause. With Fix 1A in place, both `start_year` and
`simulation_start_year` are exported with the same value, so either name works — but using the
canonical name (`start_year`) matches all other models.

### Fix 1C — Secondary: rename var in `int_workforce_pre_enrollment` (dbt model)

```sql
-- Line 41: BEFORE
CASE WHEN simulation_year = {{ var('simulation_start_year', 2025) }} THEN true ELSE false END as is_from_census,

-- Line 41: AFTER
CASE WHEN simulation_year = {{ var('start_year', 2025) }} THEN true ELSE false END as is_from_census,
```

### Fix 2 — `None` → `∞` in Config Summary (simulate.py)

Three locations in `_print_config_summary()` use `t.get('max_years', '∞')`. Change each to use
`or '∞'` so that an explicitly stored `None` is treated as absent:

```python
# Lines 218, 228, 238 — BEFORE
f"{t.get('min_years', 0)}–{t.get('max_years', '∞')} yrs"

# AFTER
f"{t.get('min_years', 0)}–{t.get('max_years') or '∞'} yrs"
```
