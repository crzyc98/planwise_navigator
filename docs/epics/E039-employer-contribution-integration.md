# Epic E039 – Employer Contribution Integration

Status: Implemented and validated. This document summarizes the integration, dependencies, and fixes applied.

## Stories

- Story S039-01: Basic Employer Contributions
  - Models: `int_employer_eligibility`, `int_employer_core_contributions`
  - Outcome: Core contributions calculated (flat rate) and integrated into `fct_workforce_snapshot`.

- Story S039-02: Workforce Snapshot Integration (Match)
  - Models: `int_employee_match_calculations`, `fct_employer_match_events`
  - Outcome: Match calculations produced from employee contributions; match events generated and snapshot joined with match amounts.

## Dependency Chain

Baseline → Compensation → Deferral State → Contributions → Match → Snapshot

1. `int_baseline_workforce`
2. `int_employee_compensation_by_year`
3. `int_enrollment_state_accumulator` and `int_deferral_rate_state_accumulator`
4. `int_employee_contributions`
5. `int_employee_match_calculations` and `fct_employer_match_events`
6. `fct_workforce_snapshot`

Match depends on Contributions; Contributions depend on Deferral State; both depend on Compensation and Baseline.

## Orchestrator and Runner Ordering

- Orchestrator `pipeline.py` stages updated:
  - EVENT_GENERATION: hiring/termination/promotion/merit/eligibility/enrollment/escalation events only.
  - STATE_ACCUMULATION: yearly events → enrollment state → deferral state → contributions → match calculations → match events → workforce snapshot.

- Simple runner `run_multi_year.py` updated to execute:
  - `int_employee_contributions` → `int_employee_match_calculations` → `fct_employer_match_events` after events and states.

## Config → dbt Vars Mapping

`config/simulation_config.yaml` → dbt vars via both orchestrators:

- Employer match
  - `employer_match.active_formula` → `active_match_formula`
  - `employer_match.formulas` → `match_formulas`

## Match Events Materialization

- `fct_employer_match_events` now uses:
  - `incremental_strategy='delete+insert'` with `unique_key=['employee_id','simulation_year']`
  - Deterministic `event_id = md5(employee_id || '-MATCH-' || simulation_year)`
  - Selection constrained to `simulation_year = var('simulation_year')` for idempotent per-year re-runs.

## AE and Opt-out Interactions

- `int_enrollment_events`: when AE is enabled, events tagged `auto_enrollment` and use `auto_enrollment_default_deferral_rate`.
- `int_deferral_rate_state_accumulator`: includes current-year enrollment events; applies same-year opt-out to set rate to 0.

## Verification Steps

- Rebuild per year (example 2025):
  - `dbt run --select "int_deferral_rate_state_accumulator int_employee_contributions int_employee_match_calculations fct_employer_match_events fct_workforce_snapshot" --vars '{"simulation_year": 2025}' --full-refresh`

- Sanity queries:
  - `SELECT COUNT(*), SUM(annual_contribution_amount) FROM int_employee_contributions WHERE simulation_year=2025;`
  - `SELECT COUNT(*), SUM(employer_match_amount) FROM int_employee_match_calculations WHERE simulation_year=2025;`
  - `SELECT COUNT(*), SUM(amount) FROM fct_employer_match_events WHERE simulation_year=2025;`
  - `SELECT SUM(employer_match_amount) FROM fct_workforce_snapshot WHERE simulation_year=2025;`

## Notes

- `fct_yearly_events` no longer mixes employer match; match events are kept in `fct_employer_match_events` to avoid circular dependencies.
- The CLI runner audit was updated to summarize employer match from `fct_employer_match_events`.
