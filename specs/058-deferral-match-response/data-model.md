# Data Model: Match-Responsive Deferral Adjustments

**Feature**: `058-deferral-match-response`
**Date**: 2026-02-21

## Entities

### 1. Match-Response Deferral Event (new rows in `fct_yearly_events`)

Events generated when employees adjust deferrals in response to the match formula gap.

| Column | Type | Description |
|--------|------|-------------|
| `employee_id` | VARCHAR | Employee identifier |
| `employee_ssn` | VARCHAR | Employee SSN (masked) |
| `event_type` | VARCHAR | Always `'deferral_match_response'` |
| `simulation_year` | INTEGER | Year the event occurs (first simulation year only) |
| `effective_date` | DATE | Date the adjustment takes effect (Jan 1 of simulation year) |
| `event_details` | VARCHAR | Human-readable: "Match response: 3.0% → 6.0% (maximize, target 6.0%)" |
| `employee_deferral_rate` | DECIMAL(5,4) | New deferral rate after adjustment |
| `prev_employee_deferral_rate` | DECIMAL(5,4) | Previous deferral rate before adjustment |
| `escalation_rate` | DECIMAL(5,4) | Amount of change (new - previous) |
| `compensation_amount` | DECIMAL(15,2) | Current annual compensation |
| `previous_compensation` | DECIMAL(15,2) | Previous compensation (same as current for rate-only changes) |
| `employee_age` | DECIMAL(5,2) | Employee age at event time |
| `employee_tenure` | DECIMAL(5,2) | Employee tenure at event time |
| `level_id` | INTEGER | Job level |
| `age_band` | VARCHAR | Age band assignment |
| `tenure_band` | VARCHAR | Tenure band assignment |
| `event_probability` | DECIMAL(5,4) | Hash-based random value used for selection |
| `event_category` | VARCHAR | Always `'match_response'` |

**Identity**: One event per employee per simulation year (unique on `employee_id + simulation_year + event_type`).

**Lifecycle**: Created once in the first simulation year. Immutable after creation. No updates or deletes.

### 2. DeferralMatchResponseSettings (Pydantic config model)

Configuration controlling match-responsive behavior.

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `enabled` | bool | `False` | — |
| `upward_participation_rate` | Decimal | `0.40` | `>= 0.0, <= 1.0` |
| `upward_maximize_rate` | Decimal | `0.60` | `>= 0.0, <= 1.0` |
| `upward_partial_increase_rate` | Decimal | `0.40` | `>= 0.0, <= 1.0` |
| `upward_partial_increase_factor` | Decimal | `0.50` | `>= 0.0, <= 1.0` |
| `downward_enabled` | bool | `True` | — |
| `downward_participation_rate` | Decimal | `0.15` | `>= 0.0, <= 1.0` |
| `downward_reduce_to_max_rate` | Decimal | `0.70` | `>= 0.0, <= 1.0` |
| `downward_partial_decrease_rate` | Decimal | `0.30` | `>= 0.0, <= 1.0` |
| `downward_partial_decrease_factor` | Decimal | `0.50` | `>= 0.0, <= 1.0` |
| `effective_timing` | str | `"first_year"` | Literal["first_year"] |

**Validation rules**:
- `upward_maximize_rate + upward_partial_increase_rate` must equal `1.0`
- `downward_reduce_to_max_rate + downward_partial_decrease_rate` must equal `1.0`
- All rates must be in `[0.0, 1.0]`

### 3. dbt Variables (exported from config)

| Variable Name | Type | Default | Used By |
|---------------|------|---------|---------|
| `deferral_match_response_enabled` | bool | `false` | Event model guard |
| `deferral_match_response_upward_participation_rate` | float | `0.40` | Employee selection |
| `deferral_match_response_upward_maximize_rate` | float | `0.60` | Sub-group split |
| `deferral_match_response_upward_partial_factor` | float | `0.50` | Partial gap closing |
| `deferral_match_response_downward_enabled` | bool | `true` | Downward guard |
| `deferral_match_response_downward_participation_rate` | float | `0.15` | Employee selection |
| `deferral_match_response_downward_reduce_to_max_rate` | float | `0.70` | Sub-group split |
| `deferral_match_response_downward_partial_factor` | float | `0.50` | Partial gap closing |

## Relationships

```
simulation_config.yaml
  └─ DeferralMatchResponseSettings (Pydantic)
       └─ export.py → dbt variables
            └─ int_deferral_match_response_events.sql (ephemeral)
                 ├─ reads: int_enrollment_events (Year 1 rates)
                 ├─ reads: int_synthetic_baseline_enrollment_events (Year 1 census rates)
                 ├─ reads: int_employee_compensation_by_year (active employees, demographics)
                 ├─ reads: {{ target.schema }}.int_deferral_rate_state_accumulator_v2 (Year 2+ rates)
                 ├─ reads: match tier config via dbt variables (match-maximizing rate)
                 └─ outputs to:
                      ├─ fct_yearly_events (event record)
                      └─ int_deferral_rate_state_accumulator_v2 (rate merge)
```

## State Transitions

```
Employee Deferral Rate State Machine:

  [Enrollment] ──→ initial_rate
       │
       ▼
  [Match Response?] ──(no)──→ initial_rate preserved
       │ (yes)
       ▼
  [Maximize or Partial?]
       │                    │
       ▼                    ▼
  match_max_rate    initial + factor × (match_max - initial)
       │                    │
       └──────┬─────────────┘
              ▼
  [Auto-Escalation?] ──(no)──→ match-adjusted rate preserved
       │ (yes)
       ▼
  match-adjusted + escalation_increment
       │
       ▼
  [Cap Check] → MIN(rate, escalation_cap, IRS_402g_limit)
       │
       ▼
  final_deferral_rate → state accumulator
```
