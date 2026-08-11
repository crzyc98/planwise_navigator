# Data Model: Employer Contribution Service Credit

## Existing entities

### Employee workforce service record

Provider: `int_workforce_state_accumulator`

| Field | Type | Rules |
|---|---|---|
| `scenario_id` | string | Part of the employee-year identity. |
| `plan_design_id` | string | Part of the employee-year identity. |
| `employee_id` | string | Stable employee identifier; non-null. |
| `simulation_year` | integer | Decision year; part of the unique key. |
| `current_tenure` | integer | Completed years of service for the authoritative annual record. Active continuing employees advance once per year; current-year hires begin at 0; a terminating employee is measured through the termination date. |
| `employee_hire_date` | date/timestamp | Establishes whether a configured new-hire exception applies. |
| `termination_date` | date/timestamp or null | Bounds service for a terminated employee. |
| `employment_status` | enum | `active` or `terminated`; used independently from service qualification. |
| `detailed_status_code` | enum | Distinguishes continuous active, active new hire, new-hire termination, and experienced termination. |

### Employer eligibility determination

Provider: `int_employer_eligibility`

| Field | Type | Rules |
|---|---|---|
| `employee_id`, `simulation_year`, `scenario_id` | existing key/context | Resolve to the same employee-year as the workforce service record; plan context is supplied by the run. |
| `current_tenure` | integer | Must equal the corresponding workforce `current_tenure`; no prior-year offset or termination adjustment. |
| `eligible_for_core` | boolean | False when service is below `core_tenure_requirement`, unless a configured exception applies; hours and status rules also apply. |
| `eligible_for_match` | boolean | Uses the same service value when `match_apply_eligibility` is true; backward-compatibility mode retains its existing active-plus-hours rule. |
| `core_tenure_requirement` | integer | Existing minimum completed service for core eligibility. |
| `match_tenure_requirement` | integer | Existing minimum completed service for match eligibility. |
| `match_eligibility_reason` | enum | Existing auditable reason, including `insufficient_tenure`; reason and flag must remain consistent. |
| exception metadata | booleans | Existing new-hire and termination allowances. An exception can bypass a gate but never changes recorded service. |

### Employer core contribution calculation

Provider: `int_employer_core_contributions`

| Field | Type | Rules |
|---|---|---|
| `employee_id`, `simulation_year`, `scenario_id` | existing key/context | Relates one contribution calculation to one workforce/eligibility record. |
| `eligible_for_core` | boolean | Consumed from the eligibility determination. |
| `applied_years_of_service` | integer | Must equal the authoritative completed service used by eligibility. |
| `core_contribution_rate` | decimal | For `graded_by_service` and `points_based`, resolves from the same service value; flat and age-banded modes are unaffected. |
| `employer_core_amount` | decimal | Existing eligible compensation and rate calculation; zero when ineligible. |

### Employer match calculation

Provider: `int_employee_match_calculations`

| Field | Type | Rules |
|---|---|---|
| `employee_id`, `simulation_year` | existing key | Relates one match calculation to one workforce/eligibility record. |
| `is_eligible_for_match` | boolean | Consumed from the eligibility determination. |
| `applied_years_of_service` | integer or null | Equals authoritative completed service for service-graded, tenure-graded, and points-based modes; remains null where the formula contract does not audit service. |
| `applied_points` | integer or null | For points-based mode, uses annual age plus the same authoritative completed service. |
| `employer_match_amount` | decimal | Existing formula output, zero when eligibility enforcement marks the employee ineligible. |

### Waiting-period configuration

Existing Pydantic/YAML configuration remains unchanged:

- `employer_core_contribution.eligibility.minimum_tenure_years`
- `employer_match.apply_eligibility`
- `employer_match.eligibility.minimum_tenure_years`
- existing hours, active-at-year-end, new-hire, and termination exception settings

## Relationships

```text
prior workforce state + immutable current-year events
                       │
                       v
        current-year workforce service record
                       │ exact current_tenure
                       v
            eligibility determination
                 │             │
          core eligible   match eligible
                 │             │
                 v             v
       core rate/amount   match rate/amount
                 │             │
                 └──────┬──────┘
                        v
              workforce snapshot costs
```

Relationships use scenario, plan design, employee, and simulation year wherever both relations expose those context fields. Employee-only joins are acceptable only inside a model already filtered to one scenario, plan, and year.

## Validation rules

- Eligibility `current_tenure` equals workforce `current_tenure` for 100% of rows.
- Core and service-dependent match `applied_years_of_service` equal `FLOOR(workforce.current_tenure)` exactly; a difference of one is a failure.
- An employee below a 2- or 3-year requirement is ineligible unless the corresponding existing explicit exception applies.
- A bypass exception changes only the eligibility outcome, not the service audit value or rate-selection basis.
- Zero-year requirements do not change population or contribution results.
- The first simulation year's expected eligibility and contribution outputs remain pinned.
- A checked-in characterization stores only aggregate expected outputs from the synthetic fixture; it contains no census PII or runtime database.

## State transitions

1. The workforce accumulator derives year N from accepted year N-1 state and immutable year N events.
2. Continuing active employees receive the accumulator's single annual service advance.
3. New hires enter with zero completed years; terminated employees are recomputed through their termination date.
4. Eligibility reads year N service without another increment.
5. Core and match calculations consume the eligibility decision and reuse the same service for any service-dependent rate.
6. Saved prior runs remain immutable; a rerun produces a new corrected result under its own provenance.

No new entity, state transition, or public schema is introduced.
