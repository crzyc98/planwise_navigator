# Phase 1 Data Model: Per-Design Contribution Formula Families

Nothing in this feature adds a table or changes a grain in either the match or the core output. On
the match side it adds one config field, one relation column, and one derived column. On the core
side it adds one config field, two new design-keyed schedule relations, four relocated integration
columns, and one derived provenance column.

Two axes, resolved independently per design:

| Axis | Selector | Families | Dispatch |
|---|---|---|---|
| Match | `MatchParameterSet.family` | `deferral_based`, `graded_by_service`, `tenure_graded`, `points_based` | union of row-producing arms (D7) |
| Core | `CoreParameterSet.family` | `flat`, `graded_by_service`, `points_based`, `age_banded` | `CASE` over a scalar rate expression (D7) |

## Configuration entities

### `MatchParameterSet` (modified)

`planalign_orchestrator/config/plan_design.py`

| Field | Type | Status | Rules |
|---|---|---|---|
| `family` | `Literal["deferral_based", "graded_by_service", "tenure_graded", "points_based"]` | **new** | Defaults to the run-global `employer_match_status`, after the legacy `tenure_based` → `tenure_graded` migration. Determines which schedule below must be non-empty. |
| `match_template` | `str` | **new** | Audit label for the deferral-based arm. Defaults to the run-global `match_template`. Descriptive only; never affects an amount. |
| `cap_percent` | `float` 0–1 | existing | Applied only when `family == "deferral_based"`. |
| `tiers` | `list[MatchTier]` | existing | Required non-empty iff `family == "deferral_based"`. |
| `graded_schedule` | `list[ServiceMatchBand]` | existing | Required non-empty iff `family == "graded_by_service"`. |
| `tenure_graded_bands` | `list[TenureGradedBand]` | existing | Required non-empty iff `family == "tenure_graded"`. |
| `points_tiers` | `list[ServiceMatchBand]` | existing | Required non-empty iff `family == "points_based"`. |

**Validation rules** (enforced in `SimulationConfig.validated_plan_design_parameters`,
`planalign_orchestrator/config/loader.py`):

1. Every design in `get_plan_design_set()` has exactly one entry in `plan_design_parameters` —
   unchanged from #632.
2. For each design, the schedule named by that design's `family` is non-empty. This replaces the
   current check, which applies the *run-global* family to every design.
3. `family` must be one of the four supported values. The legacy `tenure_based` alias is accepted at
   the boundary and normalized before validation (FR-011).
4. Schedules for families other than the design's own are permitted but ignored, and are not emitted
   into any arm. (Kept permissive so a config can carry an alternative schedule while switching
   families, matching how `MatchParameterSet` already behaves.)

Rules 2 and 3 are the source of FR-007: a design whose `family` names a schedule it does not have is
rejected at load, before the simulation starts.

### Unchanged config entities

`PlanDesignAssignmentSettings`, `HireDateCutoffRule`, `MatchTier`, `ServiceMatchBand`,
`TenureGradedBand`, `AutoEnrollmentParameterSet`, `EscalationParameterSet`,
`EligibilityParameterSet`, `PlanDesignParametersMap` are untouched. In particular the sticky
employee→design assignment owned by #631 is consumed, never modified.

### `CoreParameterSet` (modified)

`planalign_orchestrator/config/plan_design.py`

| Field | Type | Status | Rules |
|---|---|---|---|
| `family` | `Literal["flat", "graded_by_service", "points_based", "age_banded"]` | **new** | Defaults to the run-global `employer_core_status`. Determines which schedule below must be non-empty. |
| `contribution_rate` | `float` 0–1 | existing | The flat rate for `family == "flat"`; also the documented fallback for band-based families, now only reachable when the guard permits it (D8). |
| `graded_schedule` | `list[ServiceCoreBand]` | existing | Required non-empty iff `family == "graded_by_service"`. |
| `age_schedule` | `list[AgeCoreBand]` | **newly per-design** | Required non-empty iff `family == "age_banded"`. Previously run-global via `DBT_VAR_DEFERRED` (D9). |
| `points_schedule` | `list[PointsCoreBand]` | **newly per-design** | Required non-empty iff `family == "points_based"`. Previously run-global via `DBT_VAR_DEFERRED` (D9). |
| `integration_enabled` | `bool` | **newly per-design** | Permitted disparity on/off for this design (D10, FR-018). |
| `integration_level_mode` | `Literal["ss_wage_base", "explicit"]` | **newly per-design** | |
| `integration_level_value` | `int \| None` | **newly per-design** | Required when `integration_level_mode == "explicit"`. |
| `integration_disparity_rate` | `float` 0–1 | **newly per-design** | |

**Validation rules** (same loader pass as the match rules above):

5. For each design, the core schedule named by that design's core `family` is non-empty (FR-007).
6. `family` must be one of the four supported core values.
7. A config that supplies a per-design core schedule the run cannot honor per-design is rejected
   rather than flattened (FR-017). After D9 this condition is unreachable by construction; the check
   remains as a regression guard on the disposition taxonomy.
8. Match family and core family are validated independently. No rule constrains their combination.

## dbt relations

### `plan_design_parameters` (inline relation, modified)

Produced by `dbt/macros/get_plan_design_parameters.sql`, one row per design.

| Column | Type | Status |
|---|---|---|
| `plan_design_id` | `VARCHAR` | existing |
| `match_formula_family` | `VARCHAR` | **new** — the design's family; the dispatch key |
| `match_template` | `VARCHAR` | **new** — audit label |
| `match_cap_percent` | `DECIMAL(10,6)` | existing |
| `employer_core_contribution_rate` | `DECIMAL(10,6)` | existing |
| `auto_enrollment_default_deferral_rate` | `DECIMAL(10,6)` | existing |
| `auto_enrollment_window_days` | `INTEGER` | existing |
| `auto_enrollment_scope` | `VARCHAR` | existing |
| `deferral_escalation_increment` | `DECIMAL(10,6)` | existing |
| `deferral_escalation_cap` | `DECIMAL(10,6)` | existing |
| `eligibility_waiting_period_days` | `INTEGER` | existing |
| `core_formula_family` | `VARCHAR` | **new** — the design's core family; the core dispatch key |
| `core_integration_enabled` | `BOOLEAN` | **new** — D10 |
| `core_integration_level_mode` | `VARCHAR` | **new** — D10 |
| `core_integration_level_value` | `INTEGER` | **new** — nullable; D10 |
| `core_integration_disparity_rate` | `DECIMAL(10,6)` | **new** — D10 |

The empty-config branch of the macro must gain matching `CAST(NULL AS ...)` entries for every new
column so the zero-design shape stays type-compatible.

### `plan_design_match_tiers` (inline relation, unchanged)

Produced by `dbt/macros/get_plan_design_match_tiers.sql`. Already carries
`(plan_design_id, formula_family, band_min_value, band_max_value, tier_ordinal, employee_min,
employee_max, match_rate, max_deferral_pct)` for all four families across all designs. This feature
consumes it as-is; the family column it already emits becomes load-bearing rather than decorative.

### `plan_design_core_graded_schedule` (inline relation, unchanged)

Produced by `dbt/macros/get_plan_design_core_graded_schedule.sql`, delivered by #632. Keyed
`(plan_design_id, min_years, max_years, rate)`. Consumed as-is.

### `plan_design_core_age_schedule` (inline relation, new)

Produced by `dbt/macros/get_plan_design_core_age_schedule.sql`. Closes half of the
`DBT_VAR_DEFERRED` boundary (D9). Mirrors the graded schedule's shape.

| Column | Type |
|---|---|
| `plan_design_id` | `VARCHAR` |
| `min_age` | `INTEGER` |
| `max_age` | `INTEGER` (nullable — open-ended top band) |
| `rate` | `DECIMAL(10,6)` — stored as a decimal rate, not the percentage the YAML carries |

Band semantics are half-open, `min_age <= age < max_age`, matching
`get_age_banded_core_rate.sql:7-9` so the conversion is behaviour-preserving.

### `plan_design_core_points_schedule` (inline relation, new)

Produced by `dbt/macros/get_plan_design_core_points_schedule.sql`. Closes the other half of D9.
Keyed `(plan_design_id, min_points, max_points, rate)`, half-open, points defined as
`FLOOR(current_age) + FLOOR(years_of_service)` exactly as
`int_employer_core_contributions.sql:64` computes it today.

### `int_plan_design_assignment_accumulator` (unchanged)

Owned by #631. Supplies `(scenario_id, employee_id, simulation_year) → plan_design_id`, sticky across
years. Read-only here.

## Derived columns

### `formula_family` on `all_matches`

`int_employee_match_calculations.sql`. Each family arm projects a constant `formula_family` literal
alongside its existing columns; `all_matches` unions them. Downstream this column drives:

- the cap branch (only `deferral_based` applies `match_cap_percent`);
- `formula_id` / `formula_name`;
- whether `applied_years_of_service` and `applied_points` are populated or NULL.

It is an internal CTE column. The model's **output schema does not change** — `formula_type`,
`formula_id`, `formula_name`, `applied_years_of_service`, and `applied_points` already exist and
already carry exactly this information; they simply stop being run-global constants and start varying
by row. This is what makes SC-001 checkable with the existing column-wise parity harness.

### Arm coverage counter (match)

A guard CTE computes, per `(employee_id, plan_design_id, simulation_year)`, the number of arms that
produced a row. The invariant is `= 1`, evaluated only over match-eligible rows. It is not projected
into the model output; it exists only to abort the build and to be re-derivable by the dbt singular
test.

### `core_rate_source` on `integration_basis`

`int_employer_core_contributions.sql`. Core has no arms to count (D7), so the equivalent guard needs
a provenance marker instead of a counter:

| Value | Meaning |
|---|---|
| `'band'` | the rate came from a matched band row in the design's core schedule |
| `'flat'` | the design's core family is `flat`; `contribution_rate` is the answer, not a fallback |
| `'default'` | the design's family is band-based but no band matched — the silent-fallback case D8 exists to catch |
| `'ineligible'` | the row is not core-eligible; rate forced to `0.00` at `:311`, guard does not apply |

The invariant: no core-eligible row may carry `'default'`. Violations abort with the employee,
design, family, and the age/service/points value that missed every band.

This column is **internal to the model**, like `formula_family` on the match side. The output schema
does not change: `core_contribution_rate`, `contribution_method`, `standard_core_rate`, and
`applied_years_of_service` already exist and already carry this information descriptively; they stop
being run-global constants and start varying by row. That is what keeps SC-001 checkable with the
existing column-wise parity harness.

### Core band multiplicity counter

Per `(employee_id, plan_design_id, simulation_year)`, the number of schedule rows joined. The
invariant is `<= 1`, checked **before** the `WHERE rn = 1` deduplication at `:423` — because that
dedup is precisely what makes overlapping bands invisible today (D8). Per D11, the `ROW_NUMBER()`
partition also gains `plan_design_id`.

## State transitions

None. Match and core calculation are both pure per-year derivations from contributions, eligibility,
workforce state, and configuration. The only stateful entity in the neighbourhood — the design
assignment — belongs to #631 and its stickiness is an input invariant here, not a transition this
feature drives. Because the assignment is sticky, an employee's match family and core family are both
constant across the horizon (Story 1, scenario 3).

## Audit metadata

### `run_metadata.design_formula_families_json` (additive nullable column)

The existing append-only `run_metadata` row gains a canonical JSON map keyed by sorted
`plan_design_id`. Each value contains exactly `match_family` and `core_family`, using normalized
family names. The map describes the effective families actually used by the run, including inherited
run-global defaults on the legacy single-design path.

New records always populate the column. Historical records remain readable with `NULL`. The column
does not change table grain, mutate prior rows, or replace the existing configuration fingerprint;
because the family selectors flow through the effective dbt variables, changing either family also
changes that fingerprint.
