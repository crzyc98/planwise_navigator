# Contract: Design-Keyed Relations and Model Output

## `plan_design_parameters` — one row per design

Emitted by `{{ get_plan_design_parameters(plan_design_parameters) }}`.

| Guarantee | Statement |
|---|---|
| R-01 | Exactly one row per design in the run's design set. Cardinality is asserted by `dbt/tests/test_plan_design_parameter_relations.sql`. |
| R-02 | `match_formula_family` is non-NULL and is one of the four supported values for every row. |
| R-02a | `core_formula_family` is non-NULL and is one of `flat`, `graded_by_service`, `points_based`, `age_banded` for every row. |
| R-02b | The four `core_integration_*` columns are present for every row; `core_integration_level_value` is nullable, the other three are not. |
| R-03 | With an empty design map the relation yields zero rows with the full typed column list, including every new column added by this feature. |
| R-04 | Column order and types are stable; models join on `plan_design_id` and never on position. |

## `plan_design_match_tiers` — schedule rows per design and family

Emitted by `{{ get_plan_design_match_tiers(plan_design_parameters) }}`. Unchanged by this feature.

| Guarantee | Statement |
|---|---|
| R-05 | Every row's `formula_family` matches one of the four supported values. |
| R-06 | For a design `d` with family `f`, joining on `plan_design_id = d AND formula_family = f` yields that design's live schedule and nothing else. |

## `plan_design_core_age_schedule` — new

Emitted by `{{ get_plan_design_core_age_schedule(plan_design_parameters) }}`.

| Guarantee | Statement |
|---|---|
| R-15 | Rows exist only for designs whose core family is `age_banded`. |
| R-16 | Bands are half-open, `min_age <= age < max_age`, with `max_age IS NULL` meaning open-ended — identical semantics to `get_age_banded_core_rate.sql:7-9`, so conversion from the Jinja macro is behaviour-preserving. |
| R-17 | `rate` is a decimal rate. The YAML carries percentages; conversion happens once, at export, exactly as the macro's `tier['rate'] / 100.0` does today. |
| R-18 | Within a design, bands do not overlap and joining an age to them yields at most one row. Violations abort per R-21. |

## `plan_design_core_points_schedule` — new

Emitted by `{{ get_plan_design_core_points_schedule(plan_design_parameters) }}`. Same guarantees as
R-15 through R-18, with `min_points`/`max_points` and points defined as
`FLOOR(current_age) + FLOOR(years_of_service)`, matching `int_employer_core_contributions.sql:64`.

## Exported-variable disposition

| Guarantee | Statement |
|---|---|
| R-19 | `DBT_VAR_DEFERRED` is empty. `employer_core_points_schedule` and `employer_core_age_schedule` are members of `DBT_VAR_PER_DESIGN`. |
| R-20 | `dbt_var_disposition()` keeps its three-way return and every exported var still resolves to a disposition; `tests/test_dbt_var_coverage.py` passes unchanged in shape. |

## Core rate dispatch

| Guarantee | Statement |
|---|---|
| R-21 | For every core-**eligible** `(employee_id, plan_design_id, simulation_year)`, the core rate resolves from exactly one source: a matched band for a band-based family, or the flat rate for `flat`. Zero matched bands, or more than one, aborts the model build with a diagnostic naming the invocation/stage correlation identifier, employee, design, year, family, age/service/points value, observed multiplicity, and the schedule field to correct. |
| R-22 | Core-ineligible rows are exempt from R-21 and carry `core_contribution_rate = 0.00`, exactly as today. |
| R-23 | The `CASE` branches compiled equal the set of distinct `core_formula_family` values across the run's designs. No other family appears in the compiled SQL. |
| R-24 | When that set has one element, the compiled expression is row-identical to the pre-feature `core_rate_expr` branch for that family. |
| R-25 | The deduplicating `ROW_NUMBER()` partitions by `(employee_id, plan_design_id, simulation_year)`. Multiplicity is asserted *before* deduplication, so the dedup can no longer mask an overlapping-band error. |

## `int_employer_core_contributions` — output schema

| Guarantee | Statement |
|---|---|
| R-26 | The output column list is unchanged by this feature. In particular the integration columns (`integration_level_applied`, `excess_compensation`, `base_core_amount`, `disparity_core_amount`) are always projected, taking the `NULL`/`0.00`/passthrough values the current `{% else %}` branch produces for designs with integration disabled. |
| R-27 | `core_contribution_rate`, `contribution_method`, `standard_core_rate`, and `applied_years_of_service` now vary per row by the employee's design core family, where they were previously run-global constants. |
| R-28 | Grain is one row per `(employee_id, plan_design_id, simulation_year)` regardless of how many core families the run uses. |

## Arm dispatch

| Guarantee | Statement |
|---|---|
| R-07 | For every `(employee_id, plan_design_id, simulation_year)` reaching match calculation, exactly one family arm produces a row. Zero or more than one aborts the model build with a diagnostic naming the invocation/stage correlation identifier, employee, design, year, family, observed arm count/value, and the schedule field to correct. |
| R-08 | The set of arms compiled equals the set of distinct `match_formula_family` values across the run's designs. No other family appears in the compiled SQL. |
| R-09 | When that set has one element, the compiled SQL is a one-arm union whose results are row-identical to the pre-feature single-branch model. |

## `int_employee_match_calculations` — output schema

| Guarantee | Statement |
|---|---|
| R-10 | The output column list is unchanged by this feature. No column is added, removed, renamed, or retyped. |
| R-11 | `formula_type`, `formula_id`, and `formula_name` now vary per row by the employee's design family, where they were previously run-global constants. |
| R-12 | `applied_years_of_service` is populated for `graded_by_service`, `tenure_graded`, and `points_based` rows and NULL for `deferral_based` rows. `applied_points` is populated only for `points_based` rows. This matches the existing per-mode behavior exactly. |
| R-13 | `match_cap_applied` is TRUE only for `deferral_based` rows; the other families report FALSE, as today. |
| R-14 | Grain is one row per `(employee_id, plan_design_id, simulation_year)` regardless of how many families the run uses. |

## Downstream consumers

`fct_employer_match_events` and `fct_workforce_snapshot` read `int_employee_match_calculations`;
`fct_workforce_snapshot` also reads `int_employer_core_contributions`. Because R-10 and R-26 hold,
neither requires a change. Their correctness under multiple families follows from R-07/R-14 on the
match side and R-21/R-28 on the core side.
