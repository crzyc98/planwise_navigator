# Phase 1 Data Model: Explicit New-Hire Enrollment Rates

**Feature**: 652-flat-newhire-enrollment-rates | **Date**: 2026-09-04

No new tables or models. This documents the configuration fields, the columns they drive, and the decision flow they replace.

## Configuration entities

### `AutoEnrollmentSettings` (`planalign_orchestrator/config/workforce.py`)

| Field | Type | Default | Change | Meaning |
|---|---|---|---|---|
| `voluntary_enrollment_rate` | `Optional[float]`, `ge=0, le=1` | `None` | **Repurposed** | Unset: demographic new-hire enrollment, unchanged. Set: the exact fraction of eligible new hires who voluntarily enroll in their hire year. |
| `new_hire_opt_out_rate` | `Optional[float]`, `ge=0, le=1` | `None` | **New** | Unset: demographic opt-out for auto-enrolled new hires, unchanged. Set: the exact fraction of auto-enrolled new hires who opt out. |
| `opt_out_rates.target` | `float`, `ge=0, le=1` | `0.09` | Unchanged | Demographic opt-out target. Continues to govern continuing employees (R5). |

The type of `voluntary_enrollment_rate` does not change — only its description and its meaning downstream. `Optional` with a `None` default is what makes the set/unset convention expressible without a sentinel value.

## dbt variables

| Variable | Source | Default when unset | Consumed by |
|---|---|---|---|
| `voluntary_enrollment_rate` | `config/export.py` via `_set_if_not_none` | **Absent** (the `1.0` in `dbt_project.yml:261` is removed) | `int_voluntary_enrollment_decision`, `int_proactive_voluntary_enrollment` |
| `new_hire_opt_out_rate` | `config/export.py` via `_set_if_not_none` | Absent | `int_enrollment_events` opt-out CTE |

Removing the `dbt_project.yml` default is what lets the SQL distinguish set from unset. With the default present, `var('voluntary_enrollment_rate', none)` would always resolve to `1.0` and the convention would be unexpressible.

## Decision flow

### Today — new hire under auto-enrollment

```
                  ┌─ int_voluntary_enrollment_decision  (seed '-voluntary-enroll-')
                  │     p = base(age) x income x level x multiplier
  eligible new ───┤
  hire            ├─ int_proactive_voluntary_enrollment (seed '-proactive-voluntary-')
                  │     p = same formula, independent draw
                  │
                  └─ int_enrollment_events auto-enrollment (unconditional)
                        + demographic opt-out draw (seed '-optout-')
                              │
                              v
                  dedup priority: voluntary > proactive > yoy > auto
```

Two independent draws at probability `p` produce `1 - (1-p)^2`, not `p` — compounding the demographic ceiling (R3).

### After — flat rate set

```
  eligible new hire
        │
        ├── hash draw vs P ── enrolls ──> voluntary_enrollment
        │                                 (deferral rate still demographic)
        │
        └── otherwise ──> auto_enrollment
                              │
                              └── hash draw vs Q ──> enrollment_opt_out
```

One draw decides voluntary; the complement auto-enrolls; a second independent draw decides opt-out within the auto-enrolled set. `int_proactive_voluntary_enrollment` contributes no enrollment decision in this mode.

### After — flat rate unset

Unchanged from today. The demographic path is retained (spec Assumptions).

## Affected columns

| Model | Column | Change |
|---|---|---|
| `int_voluntary_enrollment_decision` | `final_enrollment_probability` | Becomes the flat `P` when set; multiplier term removed in both modes |
| | `will_enroll` | Now driven by the flat draw when set |
| | `selected_deferral_rate` | **Unchanged** — demographic selection is preserved (FR-006) |
| `int_proactive_voluntary_enrollment` | `will_enroll_proactively` | Forced false when the flat rate is set |
| `int_enrollment_events` | `event_probability` (opt-out CTE) | Becomes flat `Q` for hire-year new hires when set |
| | `event_category` | Values unchanged; `proactive_voluntary` stops being produced when the flat rate is set |
| `int_enrollment_state_accumulator` | `enrollment_method` | Alias list gains `proactive_voluntary` (R4 bug fix) |
| `fct_workforce_snapshot` | `participation_status_detail` | No code change; the four existing buckets become the acceptance measurement |

## Validation rules

| Rule | Enforced at | From |
|---|---|---|
| Both rates in `[0, 1]` | Pydantic field constraints | FR-008 |
| Error names the offending field | Pydantic default behavior | FR-008 |
| Unset is distinct from `0.0` | `_set_if_not_none` treats `0.0` as set | FR-012, existing test `test_voluntary_enrollment_rate_zero` |
| Selection deterministic for a seed | Hash idiom over `employee_id` and year | FR-005, SC-005 |

## State transitions

An eligible new hire ends the hire year in exactly one state:

| State | `participation_status_detail` | Reached when |
|---|---|---|
| Voluntarily enrolled | `participating - voluntary enrollment` | Flat voluntary draw succeeds |
| Auto-enrolled, participating | `participating - auto enrollment` | Voluntary draw fails, in auto-enrollment scope, opt-out draw fails |
| Opted out | `not_participating - opted out of AE` | Voluntary draw fails, auto-enrolled, opt-out draw succeeds |
| Not enrolled | `not_participating - not auto enrolled` | Outside auto-enrollment scope, ineligible, **or terminated before the auto-enrollment date (R6)** |

The last clause is the residual behind Risk 1, and is the reason SC-004 needs the Phase A verification before it can be treated as a target.
