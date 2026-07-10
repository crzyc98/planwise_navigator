# Contract: Prior Enrollment Decision Projection

## Producer

The PlanAlign orchestrator rebuilds `enrollment_decision_projection` after FOUNDATION and before EVENT_GENERATION for each decision year.

## Authoritative Inputs

- Start condition: `int_baseline_workforce`.
- Post-census transitions: immutable `fct_yearly_events` only.
- Scope: active `scenario_id`, `plan_design_id`, and fact years earlier than `decision_year`.

## Consumer Boundary

dbt declares the projection as a source, exposes it through `stg_prior_enrollment_state`, and requires all enrollment decision models to use `ref('stg_prior_enrollment_state')`. Direct reads of the projection, fact table, accumulator, or an intermediate model's prior rows are prohibited in those models.

## Required Columns

| Column | Requirement |
|---|---|
| `employee_id` | Non-null employee identifier |
| `scenario_id` | Equals active scenario |
| `plan_design_id` | Equals active plan design |
| `decision_year` | Equals current simulation year |
| `enrollment_date` | Census or latest applicable fact-derived date |
| `is_enrolled` | Final status after prior-fact replay |
| `ever_opted_out` | True after any prior explicit opt-out |
| `enrollment_source` | `baseline`, `fact_event`, or `none` |
| `current_deferral_rate` | Latest applicable prior rate or census rate |
| `latest_event_id` | Provenance to authoritative fact, when event-derived |
| `latest_event_year` | Provenance year, always earlier than decision year |
| `latest_event_effective_date` | Provenance ordering date |
| `rebuilt_at` | Diagnostic timestamp excluded from reproducibility comparisons |

## Lifecycle

1. Validate required prior-year state.
2. Build a temporary projection inside a transaction.
3. Validate uniqueness, scope, prior-year cutoff, and fact reconciliation.
4. Atomically replace the active projection.
5. Execute enrollment decision models.

On retry or resume, rebuild from baseline and facts; never trust prior projection contents.

## Failure Behavior

Any dependency, uniqueness, scope, or reconciliation failure stops event generation and reports correlation ID, decision year, scenario/plan context, affected counts, and resolution hints.
