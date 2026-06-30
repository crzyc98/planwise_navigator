# Phase 1 Data Model: Eligibility Resolution Semantics

**Feature**: 104-snapshot-eligibility-perf | **Date**: 2026-06-29

This feature mutates **no schema and no data grain**. This document captures the read-side semantics the rewrite must preserve, so the implementation and review can verify behavior is unchanged.

## Entities (read-only inputs)

### `fct_yearly_events` (event store — read, sanctioned mart→fct read)

Relevant rows: `event_type = 'eligibility'`.

| Field | Type | Role in this feature |
|-------|------|----------------------|
| `employee_id` | VARCHAR | Partition key for "latest eligibility year per employee" |
| `simulation_year` | INT | Used by the `MAX(simulation_year)` window (over all eligibility events ≤ current year) |
| `event_details` | VARCHAR (JSON) | Source of `eligibility_date`, `waiting_period_days`; **lacks `determination_type`** (see research R2) |

`event_details` JSON keys actually emitted by `int_eligibility_events`: `eligibility_date`, `waiting_period_days`, `minimum_age`, `reason`, `source`. **`determination_type` is never present** → the `= 'initial'` predicate is always falsy.

### `int_baseline_workforce` (eligibility fallback — read)

Provides `employee_eligibility_date`, `waiting_period_days`, `current_eligibility_status`, `employee_enrollment_date` for the active workforce of the current year. This is the value actually used today (the events join is empty).

### `int_enrollment_state_accumulator`, `employee_events_consolidated` (enrollment — read, untouched)

Drive `employee_enrollment_date` / `is_enrolled_flag` via the existing COALESCE precedence. **Not modified** by this feature.

## The `events` subquery — output columns (must remain identical)

The decorrelated subquery must emit exactly these columns, one row per `employee_id` at most:

| Column | Derivation (unchanged) |
|--------|------------------------|
| `employee_id` | event `employee_id` |
| `employee_eligibility_date` | `JSON_EXTRACT_STRING(event_details,'$.eligibility_date')::DATE` |
| `waiting_period_days` | `JSON_EXTRACT(event_details,'$.waiting_period_days')::INT` |
| `current_eligibility_status` | `'eligible'` if eligibility_date ≤ `{{ simulation_year }}-12-31` else `'pending'` |

**Row-membership rule (the part being decorrelated):** keep an employee's eligibility rows whose `simulation_year` equals that employee's `MAX(simulation_year)` over **all** eligibility events with `simulation_year ≤ {{ simulation_year }}`, **then** apply `determination_type = 'initial'`. Order of operations matters (see research R1): the MAX is computed over all determination types; the `initial` filter is applied after.

## Precedence in the consuming CTE (must remain identical)

```
employee_eligibility_date     = COALESCE(events.employee_eligibility_date,    baseline.employee_eligibility_date)
waiting_period_days           = COALESCE(events.waiting_period_days,          baseline.waiting_period_days)
current_eligibility_status    = COALESCE(events.current_eligibility_status,   baseline.current_eligibility_status)
employee_enrollment_date      = COALESCE(CASE WHEN ec.has_enrollment THEN ec.enrollment_date END,
                                         accumulator.enrollment_date,
                                         baseline.employee_enrollment_date)
is_enrolled_flag              = (employee_enrollment_date IS NOT NULL)
```

Because `events.*` is empty under all current configs, every `COALESCE(events.*, baseline.*)` resolves to `baseline.*` today. The rewrite must not change that.

## Row grain (must remain identical)

- `employee_eligibility` CTE grain: one row per `fwc.employee_id` (the `final_workforce_corrected` set), via `LEFT JOIN`s. The decorrelated `events` subquery must remain ≤1 row per `employee_id` (enforced by `SELECT DISTINCT` + single-year membership) so no new rows or fan-out enter the snapshot.

## State transitions

None. This is a derivation, not a stateful accumulator. No `{{ this }}` self-reference is added or removed.
