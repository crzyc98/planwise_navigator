# Data Model: DC Plan Eligibility Audit Trail (086)

**Date**: 2026-05-20
**Branch**: `086-dc-eligibility-events`

---

## Entities

### 1. Eligibility Event (new)

Represents an immutable record that an employee first achieved DC plan participation eligibility in a given simulation year. One record per employee per simulation; never duplicated across years.

| Field | Type | Nullable | Source | Notes |
|-------|------|----------|--------|-------|
| `employee_id` | VARCHAR | NO | `int_plan_eligibility_determination` | |
| `employee_ssn` | VARCHAR | YES | `int_plan_eligibility_determination` | |
| `event_type` | VARCHAR | NO | Constant `'eligibility'` | |
| `simulation_year` | INT | NO | `var('simulation_year')` | |
| `effective_date` | DATE | NO | `eligibility_effective_date` | `GREATEST(hire_date + waiting_period_days, age_threshold_date)` |
| `event_details` | VARCHAR | NO | Computed | Human-readable description including waiting_period_days and eligibility_status |
| `compensation_amount` | DECIMAL(10,2) | YES | NULL | Not applicable to eligibility events |
| `previous_compensation` | DECIMAL(10,2) | YES | NULL | Not applicable |
| `employee_deferral_rate` | DECIMAL(5,4) | YES | NULL | Not applicable |
| `prev_employee_deferral_rate` | DECIMAL(5,4) | YES | NULL | Not applicable |
| `employee_age` | DECIMAL | YES | `current_age` | At time of simulation year |
| `employee_tenure` | DECIMAL | YES | `current_tenure` | At time of simulation year |
| `level_id` | INT | YES | `level_id` | Job level |
| `age_band` | VARCHAR | YES | `age_band` | From `int_plan_eligibility_determination` |
| `tenure_band` | VARCHAR | YES | `tenure_band` | From `int_plan_eligibility_determination` |
| `event_probability` | DECIMAL | YES | `1.0` | Deterministic — all eligible employees receive event |
| `event_category` | VARCHAR | NO | `'eligibility'` | Via new `cat_eligibility()` macro |

### 2. Eligibility Prerequisite Chain (constraint)

A relational constraint encoded as a dbt data quality test: for every enrollment event in `fct_yearly_events`, a matching eligibility event must exist.

**Matching criteria**:
- Same `employee_id`
- Same `simulation_year`
- Eligibility `effective_date` ≤ Enrollment `effective_date`

---

## Source Models

### `int_plan_eligibility_determination` (existing — read-only)

Provides the eligibility gate computation. Key fields consumed:

| Field | Meaning |
|-------|---------|
| `is_plan_eligible` | `meets_age_requirement AND meets_tenure_requirement` — the combined gate |
| `eligibility_effective_date` | `GREATEST(hire_date + waiting_period_days, age_threshold_jan1)` |
| `eligibility_status` | Reason code: `eligible`, `not_eligible_age`, `not_eligible_tenure`, `not_eligible_other` |
| `waiting_period_days` | From `plan_eligibility_waiting_period_days` var |
| `minimum_age` | From `plan_eligibility_minimum_age` var |

---

## State Transitions

```
Ineligible → [DC_PLAN_ELIGIBILITY event] → Eligible (permanent, one-way)
```

**Transition trigger**: `is_plan_eligible = true` AND no prior eligibility event exists in `{{ this }}`
**Deduplication**: Incremental self-reference (`{{ this }}`) excludes employees already captured in prior years
**Year 1 base case**: All `is_plan_eligible = true` employees receive an event (no prior events exist)

---

## Uniqueness Rules

- At most one `DC_PLAN_ELIGIBILITY` event per `employee_id` across all simulation years (enforced by the self-reference anti-join)
- At most one row per `(employee_id, simulation_year)` in `int_eligibility_events` — enforced by `unique_key` in incremental config

---

## Dependency Graph

```
int_workforce_pre_enrollment
        ↓
int_plan_eligibility_determination
        ↓
int_eligibility_events (incremental, self-referencing for prior years)
        ↓
fct_yearly_events (UNION ALL)
        ↓
int_enrollment_state_accumulator, fct_workforce_snapshot  [already handle eligibility events]
```

---

## Configuration Variables

| Variable | Default | Effect on Eligibility |
|----------|---------|----------------------|
| `plan_eligibility_waiting_period_days` | `0` | Days after hire before eligible; shifts `effective_date` |
| `plan_eligibility_minimum_age` | `21` | Minimum age requirement; may delay `effective_date` beyond waiting period |
| `start_year` | `2025` | Determines Year 1 (no prior-year lookup) vs Year 2+ (self-reference anti-join) |
| `simulation_year` | — | Current year being processed |

---

## New Python Constant

Add to `config/constants.py`:

```python
EVENT_ELIGIBILITY = "eligibility"
```

---

## New dbt Macro

Add to `dbt/macros/constants.sql`:

```sql
{% macro cat_eligibility() %}'eligibility'{% endmacro %}
```

Update `event_category_from_type` CASE to include:

```sql
WHEN {{ col }} = {{ evt_eligibility() }} THEN {{ cat_eligibility() }}
```
