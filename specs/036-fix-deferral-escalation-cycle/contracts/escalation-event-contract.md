# Escalation Event Contract

**Feature**: 036-fix-deferral-escalation-cycle
**Date**: 2026-02-07

## Contract: Deferral Escalation Event Output Schema

This contract defines the output schema of `int_deferral_rate_escalation_events` that must be maintained for compatibility with all downstream consumers.

### Consumers

1. `fct_yearly_events` - UNION ALL leg (fuses escalation events into the immutable event stream)
2. `int_deferral_rate_state_accumulator_v2` - Reads current year escalation events for state accumulation
3. `int_deferral_escalation_state_accumulator` - Legacy consumer (reads all escalation events up to current year)
4. `int_deferral_rate_state_accumulator` - Legacy consumer

### Required Output Columns

The escalation model MUST output these columns (when `deferral_escalation_enabled = true`):

```yaml
columns:
  - name: employee_id
    type: VARCHAR
    nullable: false
  - name: employee_ssn
    type: VARCHAR
    nullable: true
  - name: event_type
    type: VARCHAR
    nullable: false
    value: 'deferral_escalation'
  - name: simulation_year
    type: INTEGER
    nullable: false
  - name: effective_date
    type: DATE
    nullable: false
  - name: event_details
    type: VARCHAR
    nullable: false
  - name: new_deferral_rate
    type: DECIMAL(5,4)
    nullable: false
  - name: previous_deferral_rate
    type: DECIMAL(5,4)
    nullable: false
  - name: escalation_rate
    type: DECIMAL(5,4)
    nullable: false
  - name: new_escalation_count
    type: INTEGER
    nullable: false
  - name: max_escalations
    type: INTEGER
    nullable: false
  - name: max_escalation_rate
    type: DECIMAL(5,4)
    nullable: false
  - name: employee_deferral_rate
    type: DECIMAL(5,4)
    nullable: false
  - name: prev_employee_deferral_rate
    type: DECIMAL(5,4)
    nullable: false
  - name: employee_age
    type: SMALLINT
    nullable: false
  - name: employee_tenure
    type: DECIMAL(10,2)
    nullable: false
  - name: level_id
    type: SMALLINT
    nullable: false
  - name: age_band
    type: VARCHAR
    nullable: false
  - name: tenure_band
    type: VARCHAR
    nullable: false
  - name: event_probability
    type: DECIMAL(5,4)
    nullable: false
  - name: event_category
    type: VARCHAR
    nullable: false
    value: 'deferral_escalation'
```

### Disabled Output Schema

When `deferral_escalation_enabled = false`, the model MUST return zero rows with the same column schema (all columns cast to correct types with NULL values, filtered by `WHERE FALSE`).

### Invariants

1. `new_deferral_rate > previous_deferral_rate` for all output rows
2. `new_deferral_rate <= max_escalation_rate` for all output rows
3. `(new_deferral_rate - previous_deferral_rate) >= 0.001` for all output rows
4. All output employees have `employment_status = 'active'` in the current year
5. Output is deterministic for a given configuration and simulation year
6. Zero rows when escalation is disabled via configuration toggle
