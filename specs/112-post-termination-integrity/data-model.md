# Data Model: Post-Termination Event Integrity

This feature changes event eligibility semantics without adding a public or persisted schema. The shared termination-boundary relation is ephemeral; existing immutable events, validation evidence, archives, and reports retain their schemas.

## Employment Period

Represents the supported continuous active interval for one employee within a scenario and plan design.

| Field | Meaning | Rule |
|---|---|---|
| scenario_id | Scenario execution scope | Required in authoritative validation |
| plan_design_id | Plan-design execution scope | Required in authoritative validation |
| employee_id | Internal employee key | Used only inside the isolated simulation database |
| active_start | Hire or baseline active date | Existing source semantics |
| active_end | Earliest termination date | Null while no termination exists |

There is currently no explicit rehire/reinstatement event. Once `active_end` exists, later events remain invalid across later simulation years. A future rehire feature must introduce a new employment period explicitly rather than reinterpret this invariant.

## Current-Year Termination Boundary

Ephemeral relation consumed during EVENT_GENERATION.

| Field | Type | Rule |
|---|---|---|
| employee_id | Identifier | Required; internal only |
| simulation_year | Integer | Equals the current simulation year |
| termination_date | Date | Minimum non-null date across experienced and new-hire termination sources |
| termination_cohort | Enum | `experienced` or `new_hire`; deterministic precedence if duplicate source rows exist |

### Validation rules

- At most one boundary row exists per employee and simulation year.
- The earliest termination date governs when duplicates exist.
- The relation reads only termination generators, never the current-year fact table.
- The relation is not persisted to archives or provenance output.
- Current-year scope is sufficient because prior-year terminated employees never enter the affected generators' state sources (start-of-year active workforce and current-year hires); the later-year invariant (FR-008) is enforced by that existing exclusion plus regression tests, not by this relation. If a prior-year cohort ever surfaces in a generator input, the relation's scope widens to the lifetime-earliest termination per scenario/plan/employee.

## Candidate Event

An event proposed by an eligibility, enrollment, promotion, merit, or deferral generator before authoritative emission.

| Field | Type | Rule |
|---|---|---|
| employee_id | Identifier | Must join to the same employee boundary |
| simulation_year | Integer | Must equal the generator year |
| event_type | Enum/string | Existing unified event type |
| effective_date | Date/timestamp | Required by existing event contract |
| generation_path | Internal label | Fixed producer identity; not parsed from free text |
| remaining event fields | Existing event payload | Unchanged |

### Boundary transition

```text
candidate event
  ├─ no termination boundary ───────────────> sequence-eligible event
  ├─ effective_date <= termination_date ───> sequence-eligible event
  └─ effective_date > termination_date ────> rejected candidate
```

Enrollment applies this transition to all combined candidates before event-category prioritization. This allows a valid earlier candidate to survive when a higher-priority candidate is dated after termination.

## Sequence-Eligible Event

A candidate that may enter the existing authoritative event union.

### Invariants

- No non-termination event is later than the current employment period's termination date.
- An event on the termination date is allowed.
- Event IDs, sequence numbers, and deterministic selection are calculated only from retained candidates through existing behavior.
- Rejected candidates do not enter state accumulators, registries, archives, or reports.

## Event-Sequence Validation Result

Existing captured result; schema is unchanged.

| Field | Rule |
|---|---|
| simulation_year | Candidate-event year being checked |
| check_name | `event_sequence_validation` |
| severity | `error` |
| passed | True only when affected count is zero |
| affected_record_count | Exact count of later non-termination event rows |

The lookup boundary is the earliest termination across all years for the same scenario, plan design, and employee. Termination rows themselves are excluded. Null effective dates are excluded from sequence comparison (never treated as a valid ordering) and remain a separate failure under the existing `not_null` data test on `fct_yearly_events.effective_date` in `dbt/models/marts/schema.yml`.

## Root-Cause Aggregate

Privacy-safe research/verification projection; not an employee-level artifact.

| Field | Allowed values/rules |
|---|---|
| simulation_year | Affected candidate year |
| event_type | Safe normalized event type |
| termination_cohort | `same_year_experienced`, `same_year_new_hire`, `prior_year_terminated`, `unknown` |
| generation_path | Fixed safe producer label |
| state_source | `current_year_workforce`, `current_year_hire`, `prior_year_snapshot`, `enrollment_projection_or_registry`, `other` |
| affected_event_count | Positive integer |

Rows sort deterministically by all dimensions. Their per-year sums equal validation affected counts, and the grand total equals the run total. Employee identifiers, exact dates, compensation, and event details are forbidden.

## Run Validation Disposition

Existing manifest field recalculated from all captured yearly validation results.

```text
any failed error       -> failed
else any failed check  -> passed_with_warnings
else all checks pass   -> passed
missing/incomplete set -> incomplete or unavailable under existing capture rules
```

Adding a later passing year cannot downgrade `failed` from an earlier year. Per-year validation rows remain immutable evidence for the run.

## Corrected Run Evidence

Existing archived evidence only: effective configuration and fingerprints, event aggregates, annual reconciliation, validation rows, report disposition, and deterministic digest. The corrected run is a new archive. Historical run `c9e319bd-e1bd-4c03-9210-30ced7f42185` and its report are never modified.
