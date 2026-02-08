# Data Model: Fix Deferral Rate Escalation Circular Dependency

**Feature**: 036-fix-deferral-escalation-cycle
**Date**: 2026-02-07

## Entities

### Deferral Escalation Event

**Source model**: `int_deferral_rate_escalation_events` (ephemeral, inlined into consumers)
**Destination**: `fct_yearly_events` (via UNION ALL)

| Column | Type | Description | Nullable |
|--------|------|-------------|----------|
| employee_id | VARCHAR | Unique employee identifier | No |
| employee_ssn | VARCHAR | Employee SSN (masked) | Yes |
| event_type | VARCHAR | Always `'deferral_escalation'` | No |
| simulation_year | INTEGER | Year of the escalation event | No |
| effective_date | DATE | Escalation effective date (configurable, default Jan 1) | No |
| event_details | VARCHAR | Human-readable description (e.g., "6.0% -> 7.0% (+1.0%)") | No |
| new_deferral_rate | DECIMAL(5,4) | Rate after escalation | No |
| previous_deferral_rate | DECIMAL(5,4) | Rate before escalation | No |
| escalation_rate | DECIMAL(5,4) | Increment amount applied | No |
| new_escalation_count | INTEGER | Always 1 (single escalation per year) | No |
| max_escalations | INTEGER | Configured maximum escalations (default 1000) | No |
| max_escalation_rate | DECIMAL(5,4) | Configured rate cap | No |
| compensation_amount | DECIMAL(15,2) | Employee compensation (nullable) | Yes |
| previous_compensation | DECIMAL(15,2) | Previous compensation (nullable) | Yes |
| employee_deferral_rate | DECIMAL(5,4) | New deferral rate (same as new_deferral_rate) | No |
| prev_employee_deferral_rate | DECIMAL(5,4) | Previous rate (same as previous_deferral_rate) | No |
| employee_age | SMALLINT | Employee age at time of escalation | No |
| employee_tenure | DECIMAL(10,2) | Employee tenure at time of escalation | No |
| level_id | SMALLINT | Employee job level | No |
| age_band | VARCHAR | Age band classification | No |
| tenure_band | VARCHAR | Tenure band classification | No |
| event_probability | DECIMAL(5,4) | Escalation rate (for event stream compatibility) | No |
| event_category | VARCHAR | Always `'deferral_escalation'` | No |

**Validation rules**:
- `new_deferral_rate > previous_deferral_rate` (meaningful increase)
- `new_deferral_rate <= max_escalation_rate` (cap enforcement)
- `(new_deferral_rate - previous_deferral_rate) >= 0.001` (minimum meaningful increase)
- `previous_deferral_rate > 0` (must have existing enrollment)
- `previous_deferral_rate < max_escalation_rate` (not already at/above cap)

### Deferral Rate State (Accumulator V2)

**Source model**: `int_deferral_rate_state_accumulator_v2` (incremental, delete+insert)
**Key**: `(employee_id, simulation_year)`

| Column | Type | Description | Nullable |
|--------|------|-------------|----------|
| employee_id | VARCHAR | Employee identifier | No |
| simulation_year | INTEGER | Year of accumulated state | No |
| current_deferral_rate | DECIMAL(5,4) | Current rate (after all escalations) | No |
| escalations_received | INTEGER | Cumulative count of escalations received | No |
| last_escalation_date | DATE | Most recent escalation effective date | Yes |
| has_escalations | BOOLEAN | Whether any escalations have been applied | No |
| escalation_source | VARCHAR | Source model for escalation data | No |
| had_escalation_this_year | BOOLEAN | Whether an escalation occurred this year | No |
| escalation_events_this_year | INTEGER | Count of escalation events this year (0 or 1) | No |
| latest_escalation_details | VARCHAR | Details of most recent escalation | Yes |
| original_deferral_rate | DECIMAL(5,4) | Rate at initial enrollment (before any escalations) | No |
| escalation_rate_change_pct | DECIMAL(8,4) | Percentage change from original rate | Yes |
| total_escalation_amount | DECIMAL(5,4) | Sum of all escalation increments | No |
| years_since_first_escalation | INTEGER | Years since first escalation event | Yes |
| days_since_last_escalation | INTEGER | Days since most recent escalation | Yes |
| is_enrolled_flag | BOOLEAN | Current enrollment status | No |
| employee_enrollment_date | DATE | Date of initial enrollment | Yes |
| created_at | TIMESTAMP | Record creation timestamp | No |
| scenario_id | VARCHAR | Simulation scenario identifier | No |
| data_quality_flag | VARCHAR | Data quality status (VALID/INVALID_*) | No |
| rate_source | VARCHAR | Source of current rate value | No |

**State transitions**:
- **Year 1 (base case)**: State derived from `fct_yearly_events` enrollment events + `int_baseline_workforce` census data
- **Year 2+ (temporal)**: Previous year state from `{{ this }}` + current year escalation events + new enrollments

**Rate source values**: `escalation_event`, `census_rate`, `enrollment_event`, `carried_forward`, `demographic_fallback`, `hard_fallback`, `opt_out`, `not_enrolled`

## Relationships

```
Escalation Configuration (simulation_config.yaml)
         |
         v (exported as dbt vars)
int_deferral_rate_escalation_events  ----->  fct_yearly_events
    ^   |                                         |
    |   |                                         v
    |   +----> int_deferral_rate_state_accumulator_v2
    |                    |
    |                    | ({{ this }} temporal self-reference for Year N-1)
    +--------------------+
         ({{ target.schema }}.table_name for Year N-1 state,
          direct table ref to break dbt DAG cycle)
```

## No Schema Changes Required

All tables and columns already exist in the current schema. The only change is that escalation events will now contain real data instead of empty result sets.
