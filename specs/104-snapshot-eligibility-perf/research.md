# Phase 0 Research: fct_workforce_snapshot Eligibility Decorrelation

**Feature**: 104-snapshot-eligibility-perf | **Date**: 2026-06-29

## R1 — Faithful decorrelation of the eligibility subquery

### Decision

Rewrite the `events` subquery (subsequent-years branch of `employee_eligibility`) so the "latest eligibility year per employee" is computed once with a window function, **not** via a per-row correlated `MAX()`. The faithful form is:

```sql
LEFT JOIN (
    WITH elig_events AS (
        SELECT
            employee_id,
            simulation_year,
            event_details,
            -- max year over ALL eligibility events for this employee, ≤ current year
            MAX(simulation_year) OVER (PARTITION BY employee_id) AS latest_elig_year
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'eligibility'
          AND simulation_year <= {{ simulation_year }}
    )
    SELECT DISTINCT
        employee_id,
        JSON_EXTRACT_STRING(event_details, '$.eligibility_date')::DATE AS employee_eligibility_date,
        JSON_EXTRACT(event_details, '$.waiting_period_days')::INT       AS waiting_period_days,
        CASE
            WHEN JSON_EXTRACT_STRING(event_details, '$.eligibility_date')::DATE <= '{{ simulation_year }}-12-31'::DATE
            THEN 'eligible' ELSE 'pending'
        END AS current_eligibility_status
    FROM elig_events
    WHERE simulation_year = latest_elig_year
      AND JSON_EXTRACT_STRING(event_details, '$.determination_type') = 'initial'
) events ON fwc.employee_id = events.employee_id
```

### Rationale

The original outer query keeps rows whose `simulation_year` equals the per-employee `MAX(simulation_year)` over **all** eligibility events ≤ current year — the inner `MAX` is **not** filtered by `determination_type`, only the outer query is. A naive `QUALIFY ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY simulation_year DESC)` applied to the `determination_type='initial'`-filtered set would pick the latest *initial* event, which differs from the original whenever an employee has a later non-initial eligibility event. The `MAX(...) OVER (PARTITION BY employee_id)` computed **before** the `determination_type` filter reproduces the exact original set membership while reading `fct_yearly_events` **once** instead of twice (outer ref + correlated inner ref).

### Alternatives considered

- **`QUALIFY ROW_NUMBER()` over the initial-only set** — rejected: changes semantics when a later non-initial eligibility event exists (the original would then yield no row and fall back to baseline; QUALIFY would keep an older initial row). Not byte-identical in the general case.
- **Pre-aggregated `max_year` CTE joined once** — equivalent in effect to the window form; the window form is chosen for locality (keeps the whole subquery self-contained, matching the surrounding CTE style).
- **Leave the correlated subquery as-is** — rejected; it is the issue being addressed and is an O(N²)-shaped per-employee re-scan.

## R2 — Decisive finding: `determination_type` is never emitted (dead predicate)

### Decision

Preserve the `JSON_EXTRACT_STRING(event_details, '$.determination_type') = 'initial'` predicate **verbatim** in the rewrite. Do **not** "fix" or remove it.

### Evidence

- The only eligibility-event producer, `dbt/models/intermediate/events/int_eligibility_events.sql` (L150–156), builds `event_details` as JSON containing `eligibility_date`, `waiting_period_days`, `minimum_age`, `reason`, `source` — **no `determination_type` key**.
- `grep -rn "determination_type"` across `dbt/`, `config/`, `planalign_orchestrator/` returns **only the consumer** at `fct_workforce_snapshot.sql:468`; there is no producer.
- The Polars/Python event path was removed in E024 (SQL-only); there is no alternate emitter.
- Consequently `JSON_EXTRACT_STRING(event_details, '$.determination_type')` is `NULL` for every eligibility row, `NULL = 'initial'` is falsy, and the `events` subquery returns **zero rows in every configuration**. The DB confirms each employee has at most one eligibility event in a single year (2025: 8116 emps, 2026: 1568, 2027: 1639 — no employee spans >1 year), so even ignoring the predicate the correlated `MAX` is degenerate.

### Implication

The byte-identical guarantee (FR-002/SC-001) holds trivially: today the `events` join contributes nothing and `COALESCE(events.*, baseline.*)` always uses `baseline.*`. Keeping the dead predicate guarantees the rewrite stays at zero rows. The performance win (one scan instead of two, no per-row correlation) is real and independent of the predicate being dead.

### Deferred (out of scope)

The entire events-eligibility join is effectively dead code under current producers. Whether to (a) remove it, or (b) make `int_eligibility_events` emit `determination_type` so the join becomes live, is a **business-rules decision** explicitly out of scope per the spec ("no change to eligibility business rules"). Recommend a separate tracked issue. This plan neither removes nor activates it — it only decorrelates while preserving exact behavior.

## R3 — Issue #365 "redundant scan" claim, reconciled

### Decision

Treat the redundant-scan elimination as a **byproduct of R1** for the in-scope branch, and drop the literal "use `current_year_events`" substitution.

### Rationale

- **L466 (subsequent-years eligibility read)** filters eligibility events across **all years ≤ current** (via the inner `MAX` subquery), not the current year only. It therefore **cannot** be sourced from `current_year_events` (which is current-year-only) without changing semantics. The issue's framing here is imprecise. The decorrelation in R1 already removes the genuine redundancy — the *double* read of `fct_yearly_events` (outer + correlated inner) collapses to a single read.
- **L412 (new-hire hire-event read)** lives in the **year-1** branch (`simulation_year == start_year`), which the spec places **out of scope** (FR-004, Out of Scope §). It is left untouched.

### Alternatives considered

- Substituting `current_year_events` at L466 — rejected: would drop prior-year eligibility events the original logic intends to consider, breaking byte-identity.

## Open questions

None. All Technical Context items resolved; no NEEDS CLARIFICATION remain.
