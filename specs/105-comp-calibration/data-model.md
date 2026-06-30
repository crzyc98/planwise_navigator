# Phase 1 Data Model: Fast Compensation Calibration Mode

No new persistent tables are introduced (Design 1). The entities below are **in-memory / transport** structures (Pydantic models + the existing dbt marts they read from).

## Entity: CalibrationParameterSet

The tunable compensation levers — a subset/reuse of the existing `CompensationSettings` plus the new-hire mix and target growth. Shared identically with the full simulation.

| Field | Type | Validation | Source |
|-------|------|------------|--------|
| `target_growth_pct` | Decimal | 0 ≤ x ≤ 0.25 (sane band); used for delta only | calibration-specific |
| `cola_rate` | Decimal | ≥ 0 | `CompensationSettings.cola_rate` |
| `merit_budget` | Decimal | ≥ 0 | `CompensationSettings.merit_budget` |
| `promotion_increase` | Decimal | ≥ 0 | `CompensationSettings.promotion_increase` |
| `new_hire_mix` | mapping(level → weight) | weights ≥ 0 and sum > 0 | new-hire age/level distribution seeds |
| `comp_ranges` | mapping(level → {min,max}) | min ≤ max | per-level compensation range config |

**Notes**: Reuses existing Pydantic validation; `to_dbt_vars()` is the single serialization point to dbt `--vars`. `target_growth_pct` does not affect the build — it is only used to compute the per-year delta.

## Entity: CalibrationRun

One execution over a year range under a parameter set against a target database.

| Field | Type | Validation |
|-------|------|------------|
| `start_year` | int | ≥ 2000 |
| `end_year` | int | ≥ `start_year` |
| `config_path` | path \| None | exists if provided |
| `database_path` | path \| None | None → isolated default DB |
| `interactive` | bool | — |
| `params` | CalibrationParameterSet | see above |

**State / lifecycle**: `validate → guard(prerequisites) → per-year comp-only build → read mart → assemble results`. On guard failure the run terminates before any build (fail-fast, FR-011).

## Entity: PerYearCompensationResult

One row per simulation year in the run output. Sourced from `fct_compensation_growth` (+ headcount/new-hire gap from `fct_workforce_snapshot`).

| Field | Type | Source column |
|-------|------|---------------|
| `simulation_year` | int | `fct_compensation_growth.simulation_year` |
| `avg_compensation` | Decimal | `avg_compensation` (methodology A, prorated) |
| `yoy_growth_pct` | Decimal \| None | `yoy_growth_pct` (None for first year) |
| `target_growth_pct` | Decimal | from params |
| `growth_delta_pct` | Decimal \| None | `yoy_growth_pct − target_growth_pct` |
| `headcount` | int | active count from snapshot |
| `new_hire_avg_comp` | Decimal | snapshot, `new_hire_active` |
| `existing_avg_comp` | Decimal | snapshot, `continuous_active` |
| `new_hire_gap` | Decimal | `new_hire_avg_comp − existing_avg_comp` |

**Validation rule**: `yoy_growth_pct` and `growth_delta_pct` MUST be null/blank for the first year of the range (Edge Case: single-year / first-year growth undefined).

## Read-only dependencies (existing artifacts)

| Artifact | Role |
|----------|------|
| `fct_compensation_growth` | Primary metric source (S051; built by calibration) |
| `fct_workforce_snapshot` | Headcount + new-hire/existing comp gap (rebuilt; Design 1 stale DC refs) |
| `fct_yearly_events` | Event source feeding the snapshot (rebuilt) |
| DC tables (`int_employee_contributions`, etc.) | Prerequisite presence only — never read into comp columns |

## Prerequisite guard contract

Before any build, verify the target DB contains the DC tables that `fct_workforce_snapshot`/`fct_yearly_events` `ref()`. If any are missing → raise a `ConfigurationError`-style failure with an actionable message ("run a full `planalign simulate` against this DB first") and exit non-zero. No partial build is attempted.
