# Data Model: Preserve Census Enrollment

Public event, accumulator, and snapshot schemas remain unchanged. One internal disposable projection is introduced to bridge the orchestration-year boundary without making derived state authoritative.

## Census Participant Baseline

**Source**: `int_baseline_workforce`

**Relevant fields**: `employee_id`, `employee_enrollment_date`, `employee_deferral_rate`, `is_enrolled_at_census`, `simulation_year`.

**Rules**:

- Supplies initial state only.
- Is scoped into the active `scenario_id` and `plan_design_id` when the projection is rebuilt.
- Never overrides a later immutable fact event.

## Immutable Enrollment Event

**Authoritative source**: `fct_yearly_events`

**Relevant fields**: `event_id`, `scenario_id`, `plan_design_id`, `employee_id`, `event_type`, `event_category`, `simulation_year`, `effective_date`, `event_sequence`, `event_details`, `employee_deferral_rate`.

**Rules**:

- Only events earlier than the decision year participate in projection rebuild.
- Only rows matching the active scenario and plan design participate.
- Ordering is deterministic by effective date, simulation year, event sequence, then event ID.
- Event rows remain immutable and are never changed by this feature.

## Enrollment Decision Projection

**Internal table**: `enrollment_decision_projection`

**Purpose**: Disposable, fact-reconciled state used by current-year enrollment decisions.

**Fields**:

- `employee_id`: Unique employee key within the active projection.
- `scenario_id`: Active scenario identifier.
- `plan_design_id`: Active plan identifier.
- `decision_year`: Year whose events will consume this state.
- `enrollment_date`: Effective enrollment date after prior-event replay.
- `is_enrolled`: Status after replaying prior facts over census state.
- `ever_opted_out`: Whether a prior fact contains an explicit opt-out.
- `enrollment_source`: `baseline`, `fact_event`, or `none`.
- `current_deferral_rate`: Latest applicable fact rate or census rate.
- `latest_event_id`: Fact event establishing the latest applicable state, when present.
- `latest_event_year`: Year of that fact event, when present.
- `latest_event_effective_date`: Effective date of that fact event, when present.
- `rebuilt_at`: Projection build timestamp for diagnostics only.

**Validation rules**:

- Unique by `employee_id`, `scenario_id`, `plan_design_id`, and `decision_year`.
- Contains no current- or future-year fact events.
- Contains only the active scenario/plan pair.
- Rebuild is atomic and replaces the prior projection only after reconciliation succeeds.
- Repeating a rebuild with unchanged census/facts produces identical business fields.
- Projection counts and statuses reconcile to the baseline-plus-fact replay query.

## Staged Prior Enrollment State

**Model**: `stg_prior_enrollment_state`

**Purpose**: Declared dbt boundary over the orchestrator projection.

**Rules**:

- Reads the projection through `source()`.
- Filters to current `simulation_year`, `scenario_id`, and `plan_design_id` vars.
- Exposes explicit columns only and is unique per employee for the active decision context.
- Is the only prior-enrollment input referenced by enrollment decision models.

## Enrollment Opportunity

Represents deterministic eligibility for an applicable enrollment path, not the random realization of an event.

**Fields**: employee identity, decision year, currently enrolled flag, ever-opted-out flag, applicable auto/voluntary eligibility flag, exclusion reason.

**Rules**:

- Census participants projected as enrolled are excluded from new-enrollee populations.
- Genuinely unenrolled controls remain in the applicable eligible population.
- Event emission is asserted only under a fixture probability of `1.0`; otherwise tests assert opportunity membership.

## Enrollment State and Yearly Workforce State

**Existing models**: `int_enrollment_state_accumulator`, `int_employee_compensation_by_year`, `fct_workforce_snapshot`.

**Rules**:

- Accumulator and snapshot remain downstream of immutable events.
- Every completed simulation year remains represented.
- Current-year rebuilds may replace current-year rows but never prior completed years.
- Snapshot enrollment and deferral values reconcile to accumulated state and applicable fact events.

## Scenario Run

**Identity**: scenario ID, plan design ID, isolated database path, isolated artifact directory, year range, random seed.

**Rules**:

- Distinct runs under test use distinct database and artifact paths.
- All facts inside a run database match its scenario/plan identity.
- Completing another run does not change the first run's database checksum or row counts.

## State Transitions

```text
census baseline
  + prior immutable fct_yearly_events
  -> atomically rebuilt enrollment_decision_projection
  -> stg_prior_enrollment_state
  -> current-year enrollment decisions
  -> immutable fct_yearly_events
  -> enrollment accumulator
  -> workforce snapshot
```

- `baseline_enrolled -> enrolled`: carries forward without a new enrollment event.
- `never_enrolled -> eligible`: enters applicable decision population.
- `eligible -> enrolled`: occurs when deterministic/configured selection emits an enrollment fact.
- `enrolled -> opted_out`: explicit opt-out fact sets false and records opt-out history.
- `opted_out -> opted_out`: census does not restore participation.
- `unenrolled -> re_enrolled`: only when existing configured rules permit a new enrollment fact.
