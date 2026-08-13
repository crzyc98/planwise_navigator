# Contract: Event Factory JSON Serialization

**Feature**: 437-property-based-event-factories
**Producer**: `SimulationEvent.model_dump(mode="json")`
**Consumer boundary**: Guarded JSON-compatible audit payload contract for downstream ingestion/adapters; no direct event-factory-to-DuckDB adapter is asserted by this feature

## Envelope Contract

Every in-scope factory emits exactly these top-level keys:

| Key | JSON type | Notes |
|---|---|---|
| `event_id` | string | Canonical UUID text. |
| `employee_id` | string | Trimmed, non-empty, Unicode-preserving. |
| `effective_date` | string | ISO `YYYY-MM-DD`. |
| `created_at` | string | ISO-8601 datetime; factory default is UTC. |
| `scenario_id` | string | Trimmed and non-empty. |
| `plan_design_id` | string | Trimmed and non-empty. |
| `source_system` | string | Fixed by factory family as listed below. |
| `payload` | object | Exact type-specific shape selected by `event_type`. |
| `correlation_id` | string or null | Factory-created events currently emit null. |

Exact top-level key set:

```text
event_id, employee_id, effective_date, created_at, scenario_id,
plan_design_id, source_system, payload, correlation_id
```

## Common Type Rules

- UUID, date, datetime, and Decimal native values serialize as JSON strings.
- Decimal strings retain the model-normalized scale: six fractional digits for monetary values and four for rates.
- `bool` values serialize as JSON booleans, not integers or strings.
- `int` values serialize as JSON numbers.
- `None` serializes as JSON `null`.
- Nested balance mappings serialize as JSON objects whose values are decimal strings.
- Vesting balance signs are not constrained by the current payload schema; only their JSON string type and six-place scale are contractual here.
- Exact key membership and value type are contractual. JSON object key order and whitespace are not.

## Payload Contracts

### Hire

**Factory**: `WorkforceEventFactory.create_hire_event`
**Source**: `workforce_simulation`
**Effective date source**: `hire_date`

| Key | JSON type |
|---|---|
| `event_type` | string (`hire`) |
| `plan_id` | string or null |
| `hire_date` | date string |
| `department` | string |
| `job_level` | number (integer) |
| `annual_compensation` | six-place decimal string |

### Termination

**Factory**: `WorkforceEventFactory.create_termination_event`
**Source**: `workforce_simulation`
**Effective date source**: `effective_date`

| Key | JSON type |
|---|---|
| `event_type` | string (`termination`) |
| `plan_id` | string or null |
| `termination_reason` | string |
| `final_pay_date` | date string |

### Promotion

**Factory**: `WorkforceEventFactory.create_promotion_event`
**Source**: `workforce_simulation`
**Effective date source**: `effective_date`

| Key | JSON type |
|---|---|
| `event_type` | string (`promotion`) |
| `plan_id` | string or null |
| `new_job_level` | number (integer) |
| `new_annual_compensation` | six-place decimal string |
| `effective_date` | date string |

### Merit (raise equivalent)

**Factory**: `WorkforceEventFactory.create_merit_event`
**Source**: `workforce_simulation`
**Effective date source**: `effective_date`

| Key | JSON type |
|---|---|
| `event_type` | string (`merit`) |
| `plan_id` | string or null |
| `new_compensation` | six-place decimal string |
| `merit_percentage` | four-place decimal string |

### Enrollment

**Factory**: `DCPlanEventFactory.create_enrollment_event`
**Source**: `dc_plan_administration`
**Effective date source**: `enrollment_date`

| Key | JSON type |
|---|---|
| `event_type` | string (`enrollment`) |
| `plan_id` | string |
| `enrollment_date` | date string |
| `pre_tax_contribution_rate` | four-place decimal string |
| `roth_contribution_rate` | four-place decimal string |
| `after_tax_contribution_rate` | four-place decimal string |
| `auto_enrollment` | boolean |
| `opt_out_window_expires` | date string or null |
| `enrollment_source` | string |
| `auto_enrollment_window_start` | date string or null |
| `auto_enrollment_window_end` | date string or null |
| `proactive_enrollment_eligible` | boolean |
| `window_timing_compliant` | boolean |

### Contribution

**Factory**: `DCPlanEventFactory.create_contribution_event`
**Source**: `dc_plan_administration`
**Effective date source**: `contribution_date`

| Key | JSON type |
|---|---|
| `event_type` | string (`contribution`) |
| `plan_id` | string |
| `source` | string |
| `amount` | six-place decimal string |
| `pay_period_end` | date string |
| `contribution_date` | date string |
| `ytd_amount` | six-place decimal string |
| `payroll_id` | string |
| `irs_limit_applied` | boolean |
| `inferred_value` | boolean |

### Vesting

**Factory**: `DCPlanEventFactory.create_vesting_event`
**Source**: `dc_plan_administration`
**Effective date source**: `service_computation_date`

| Key | JSON type |
|---|---|
| `event_type` | string (`vesting`) |
| `plan_id` | string |
| `vested_percentage` | four-place decimal string |
| `source_balances_vested` | object of source name to six-place decimal string |
| `vesting_schedule_type` | string |
| `service_computation_date` | date string |
| `service_credited_hours` | number (integer) |
| `service_period_end_date` | date string |

### Forfeiture

**Factory**: `PlanAdministrationEventFactory.create_forfeiture_event`
**Source**: `plan_administration`
**Effective date source**: `effective_date`

| Key | JSON type |
|---|---|
| `event_type` | string (`forfeiture`) |
| `plan_id` | string |
| `forfeited_from_source` | string |
| `amount` | six-place decimal string |
| `reason` | string |
| `vested_percentage` | four-place decimal string |

### HCE status

**Factory**: `PlanAdministrationEventFactory.create_hce_status_event`
**Source**: `hce_determination`
**Effective date source**: `determination_date`

| Key | JSON type |
|---|---|
| `event_type` | string (`hce_status`) |
| `plan_id` | string |
| `determination_method` | string |
| `ytd_compensation` | six-place decimal string |
| `annualized_compensation` | six-place decimal string |
| `hce_threshold` | six-place decimal string |
| `is_hce` | boolean |
| `determination_date` | date string |
| `prior_year_hce` | boolean or null |

## Compatibility Rule

Any addition, removal, rename, source-system change, effective-date mapping change, or JSON type change in the envelope or covered payloads must fail the property suite and receive explicit contract review. The suite does not require stable JSON object ordering or byte-for-byte timestamp text formatting beyond successful Pydantic round-trip equality.
