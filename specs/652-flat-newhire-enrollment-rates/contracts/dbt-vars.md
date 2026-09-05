# Contract: dbt Variables

**Feature**: 652-flat-newhire-enrollment-rates

## Variables

### `voluntary_enrollment_rate` (repurposed)

- **Type**: float in `[0, 1]`, or absent
- **Before**: multiplier on demographic enrollment probabilities; defaulted to `1.0` in `dbt/dbt_project.yml:261`
- **After**: the exact fraction of eligible hire-year new hires who voluntarily enroll
- **Absent**: demographic new-hire enrollment applies, unchanged
- **Breaking**: yes. The `dbt_project.yml` default is **removed**, so `var('voluntary_enrollment_rate', none)` resolves to `none` when the analyst has not set it. Any model reading this variable must handle `none`.

### `new_hire_opt_out_rate` (new)

- **Type**: float in `[0, 1]`, or absent
- **Meaning**: the exact fraction of auto-enrolled hire-year new hires who opt out
- **Absent**: the demographic opt-out model applies, unchanged
- **Scope**: hire-year new hires only. Continuing employees keep `opt_out_rate_*` (derived from `opt_out_rates.target`).

## Consumer requirements

| Model | Must |
|---|---|
| `int_voluntary_enrollment_decision` | Branch on set/unset. When set, apply the flat rate to hire-year new hires only; continuing employees keep the demographic probability with the multiplier term removed. |
| `int_proactive_voluntary_enrollment` | When set, produce no enrollment decision (the single-decision requirement, FR-004). When unset, behave as today minus the inert multiplier. |
| `int_enrollment_events` | Branch the opt-out CTE on `new_hire_opt_out_rate` for hire-year new hires. Remove the inert multiplier from the year-over-year CTE. |

## Unchanged variables

`opt_out_rate_young`, `opt_out_rate_mid`, `opt_out_rate_mature`, `opt_out_rate_senior`, `opt_out_rate_low_income`, `opt_out_rate_moderate`, `opt_out_rate_high`, `opt_out_rate_executive`, all `voluntary_enrollment_base_rates_by_age_*`, `voluntary_enrollment_income_multipliers_*`, `voluntary_enrollment_job_level_multipliers_*`, and all `voluntary_enrollment_deferral_rates_demographic_base_rates_*`.

The deferral-rate variables in particular stay in force for voluntarily enrolled new hires — the flat rate governs *whether* they enroll, never *at what rate* (FR-006).

## Compatibility note

A scenario that sets no rate exports neither variable, and every expression that consumed the old multiplier is removed rather than defaulted. Because the old default was `1.0` and multiplication by `1.0` is inert, this is provably equivalent to today's behavior (research R1).
