# Contract: Command Schedule

**Feature**: 132-collapse-dbt-invocations

The schedule is this feature's only intended output change. This contract states its exact expected shape at each step, and is what `tests/test_workflow_schedule.py` asserts against in the fast suite.

## Baseline — 20 commands

**Year 1 (8)**

| # | Verb | Selection | Full refresh | Source |
|---|---|---|---|---|
| 1 | `seed` | — | no | `pipeline_orchestrator.py:711` |
| 2 | `run` | `staging.*` | no | `pipeline_orchestrator.py:721` |
| 3 | `run` | `int_effective_parameters` | **yes** | `hazard_cache_manager.py:403` |
| 4 | `build` | `dim_*_hazards`, `hazard_cache_metadata` | **yes** | `hazard_cache_manager.py:429` |
| 5 | `run` | `int_baseline_workforce` | no | INITIALIZATION, `workflow.py:120` |
| 6 | `run` | `int_baseline_workforce`, `int_new_hire_compensation_staging`, … | **yes** | FOUNDATION, `workflow.py:130` |
| 7 | `run` | `tag:EVENT_GENERATION` | no | `stage_execution_strategies.py:33` |
| 8 | `run` | `int_workforce_state_accumulator` … `fct_workforce_snapshot` | no | `year_executor.py:320` |

**Years 2–5 (3 each)** — INITIALIZATION+FOUNDATION merged (Tier B, `workflow.py:171-173`), then `tag:EVENT_GENERATION`, then state accumulation.

## After Step 1a — 19 commands

Command 5 is **removed**. Year 1 INITIALIZATION contributes no command.

- **Assert**: `int_baseline_workforce` appears in exactly one command in year 1 (invariant CS-1).
- **Assert**: it is still built with `full_refresh=true` (invariant CS-2) — the FOUNDATION command is unchanged.
- **Assert**: no INITIALIZATION validation was lost, because none was ever dispatched (`stage_validator.py:57-83`).

## After Step 1b — 18 commands

Commands 3 and 4 become one:

```
build --select int_effective_parameters dim_*_hazards hazard_cache_metadata --full-refresh
```

- **Assert**: `hazard_params_hash` is present in the merged command's `extra_vars` (invariant CS-5). This is the silent-failure risk from research Finding 4.
- **Assert**: every model previously full-refreshed is still full-refreshed (CS-2).
- **Note**: `int_effective_parameters` moves from `run` to `build`, newly executing its schema tests. Confirm they pass at 60k before keeping the step.

## After Step 2 — 14 commands

For each year after the start year, the merged INITIALIZATION+FOUNDATION command is folded into event generation:

```
run --select tag:EVENT_GENERATION int_active_employees_prev_year_snapshot \
    int_prev_year_workforce_summary int_prev_year_workforce_by_level \
    int_employee_compensation_by_year int_effective_parameters \
    int_workforce_needs int_workforce_needs_by_level
```

- **Assert**: exactly two commands per year after the start year (invariant CS-3).
- **Assert**: neither side carries a rebuild flag after the start year, so CS-2 holds trivially (`_should_full_refresh_foundation` is start-year-only, `year_executor.py:424`).
- **Assert**: FOUNDATION's validation rules still execute against the built tables even though the stage issues no command — the property Tier B already relies on.
- **Assert**: a failure inside the merged command still names a year and stage (`FR-015`).

## Final shape

| | Baseline | After 1a | After 1b | After 2 |
|---|---|---|---|---|
| Year 1 | 8 | 7 | 6 | 6 |
| Each later year | 3 | 3 | 3 | 2 |
| **Total (5y)** | **20** | **19** | **18** | **14** |

Matches `SC-006`: 14 with both steps kept, 18 with Story 1 only.

## What this contract does not permit

- Removing a model from the build entirely (as opposed to removing a *duplicate* build of it).
- Merging across differing rebuild flags.
- Merging event generation with state accumulation (`FR-004`).
- Changing the resolved set of full-refreshed models in either direction.
