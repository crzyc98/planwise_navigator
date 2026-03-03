# Data Model: ERISA 1,000-Hour Eligibility Rules

**Feature**: `063-1000-hr-eligibility` | **Date**: 2026-03-03

## Entity Relationship Overview

```
int_baseline_workforce ─────────────┐
                                    ├──▶ int_eligibility_computation_period ──▶ int_service_credit_accumulator
int_hiring_events ──────────────────┤
int_new_hire_termination_events ────┘
```

All new models are in the `intermediate` layer. They read only from existing staging/intermediate models (no marts-layer references). Parallel architecture — no modifications to existing models. Continuous employment assumed — no break-in-service or rehire tracking.

## Entity: Eligibility Computation Period

**dbt model**: `int_eligibility_computation_period`
**Materialized**: `table` (recomputed per simulation year)
**Tags**: `['eligibility', 'erisa', 'STATE_ACCUMULATION']`
**Unique key**: `employee_id || '_' || simulation_year || '_' || period_type`

| Column | Type | Description | Validation |
|--------|------|-------------|------------|
| employee_id | VARCHAR | Employee identifier | NOT NULL |
| simulation_year | INTEGER | Current simulation year | NOT NULL |
| period_type | VARCHAR | `'iecp'`, `'plan_year'` | NOT NULL, accepted_values |
| period_start_date | DATE | Start of computation period | NOT NULL |
| period_end_date | DATE | End of computation period | NOT NULL, > period_start_date |
| hire_date | DATE | Employee's employment commencement date | NOT NULL |
| iecp_end_date | DATE | hire_date + 12 months (first anniversary) | NOT NULL |
| annual_hours_prorated | DECIMAL(8,2) | Hours credited in this period (prorated from 2,080) | NOT NULL, >= 0, <= 3000 |
| iecp_year1_hours | DECIMAL(8,2) | IECP hours in hire year (hire_date to year-end) | >= 0 |
| iecp_year2_hours | DECIMAL(8,2) | IECP hours in second year (year-start to anniversary) | >= 0 |
| iecp_total_hours | DECIMAL(8,2) | Sum of year1 + year2 IECP hours | >= 0 |
| hours_classification | VARCHAR | `'year_of_service'`, `'no_credit'` | NOT NULL, accepted_values |
| is_iecp_complete | BOOLEAN | Whether the IECP 12-month window has been completed | NOT NULL |
| is_plan_year_eligible | BOOLEAN | Whether employee meets 1,000 hours in this plan year | NOT NULL |
| iecp_eligible | BOOLEAN | Whether employee meets 1,000 hours in the IECP | NOT NULL |
| overlap_double_credit | BOOLEAN | True if employee qualifies for both IECP and plan year credit | NOT NULL |
| eligibility_years_this_period | INTEGER | 0, 1, or 2 (if overlap double credit applies) | NOT NULL, 0-2 |
| plan_entry_date | DATE | Computed entry date per IRC 410(a)(4) | NULL until eligible |
| eligibility_reason | VARCHAR | Reason code for eligibility determination | NOT NULL |
| scenario_id | VARCHAR | Scenario identifier | NOT NULL |
| plan_design_id | VARCHAR | Plan design identifier | NOT NULL |

**State transitions for period_type**:
- Year of hire: `iecp` (mandatory)
- Year after hire (if IECP not satisfied): `iecp` + `plan_year` (overlap evaluation)
- All subsequent years: `plan_year`

**Eligibility reason codes**:
- `eligible_iecp` — Met 1,000 hours in IECP
- `eligible_plan_year` — Met 1,000 hours in plan year (after IECP failed)
- `eligible_double_credit` — Met 1,000 hours in both IECP and plan year
- `pending_iecp` — IECP not yet complete
- `insufficient_hours_iecp` — IECP complete but < 1,000 hours
- `insufficient_hours_plan_year` — Plan year < 1,000 hours
- `already_eligible` — Previously satisfied eligibility

## Entity: Service Credit Accumulator

**dbt model**: `int_service_credit_accumulator`
**Materialized**: `incremental` (delete+insert, temporal accumulator pattern)
**Tags**: `['eligibility', 'erisa', 'STATE_ACCUMULATION']`
**Unique key**: `employee_id || '_' || simulation_year`

| Column | Type | Description | Validation |
|--------|------|-------------|------------|
| employee_id | VARCHAR | Employee identifier | NOT NULL |
| simulation_year | INTEGER | Current simulation year | NOT NULL |
| eligibility_years_credited | INTEGER | Cumulative eligibility service years | NOT NULL, >= 0 |
| vesting_years_credited | INTEGER | Cumulative vesting service years | NOT NULL, >= 0 |
| eligibility_hours_this_year | DECIMAL(8,2) | Hours in this year's ECP | NOT NULL, >= 0 |
| vesting_hours_this_year | DECIMAL(8,2) | Hours in this year's VCP | NOT NULL, >= 0 |
| eligibility_classification_this_year | VARCHAR | `'year_of_service'`, `'no_credit'` | NOT NULL |
| vesting_classification_this_year | VARCHAR | `'year_of_service'`, `'no_credit'` | NOT NULL |
| is_plan_eligible | BOOLEAN | Has met eligibility threshold (ever) | NOT NULL |
| plan_entry_date | DATE | Date of plan entry (once eligible) | NULL until eligible |
| first_eligible_date | DATE | Date eligibility was first satisfied | NULL until eligible |
| employment_status | VARCHAR | `'active'`, `'terminated'` | NOT NULL |
| service_credit_source | VARCHAR | Audit trail: `'baseline'`, `'accumulated'` | NOT NULL |
| scenario_id | VARCHAR | Scenario identifier | NOT NULL |
| plan_design_id | VARCHAR | Plan design identifier | NOT NULL |

**Temporal accumulation logic**:
- **First year**: Initialize from `int_baseline_workforce` (census tenure → seed eligibility years) + `int_eligibility_computation_period` (current year hours)
- **Subsequent years**: Read from `{{ this }}` (prior year) + merge with `int_eligibility_computation_period` (current year)
- **Carry-forward fields**: `eligibility_years_credited`, `vesting_years_credited`, `is_plan_eligible`, `plan_entry_date`
- **Reset fields**: `eligibility_hours_this_year`, `vesting_hours_this_year`

## Configuration Entity

**Location**: `config/simulation_config.yaml` (new section)

```yaml
erisa_eligibility:
  enabled: true
  hour_counting_method: "prorated"        # Only "prorated" supported in this iteration
  plan_year_start_month: 1
  plan_year_start_day: 1
  eligibility_threshold_hours: 1000
  vesting_computation_period: "plan_year"  # "plan_year" | "anniversary_year"
```

## Model Dependency Graph

```
Layer: staging
  stg_census_data ─────────────────────────┐
  stg_config_* (seeds) ───────────────────┐│
                                          ││
Layer: intermediate (existing)            ││
  int_baseline_workforce ◄────────────────┘│
  int_employer_eligibility (UNCHANGED) ◄───┘
  int_eligibility_determination (UNCHANGED)
  int_plan_eligibility_determination (UNCHANGED)
  int_hiring_events (read-only) ─────────────┐
  int_new_hire_termination_events (read-only) ┤
                                              │
Layer: intermediate (NEW)                     │
  int_eligibility_computation_period ◄────────┘
       │
       ▼
  int_service_credit_accumulator

Layer: marts (future consumer)
  fct_workforce_snapshot (could consume new models in future)
```

No circular dependencies. New models only read from existing intermediate-layer models. They do not feed back into any existing model.
