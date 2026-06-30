# Output Contract: fct_workforce_snapshot

**Feature**: 104-snapshot-eligibility-perf | **Date**: 2026-06-29

This is an internal dbt model with no external API surface. Its "contract" is the materialized table's schema, grain, and a behavior-preserving invariant. The rewrite MUST satisfy all clauses below.

## C1 — Schema unchanged

The column set, names, types, and ordering of `fct_workforce_snapshot` MUST be identical to `main`. No column added, removed, renamed, or retyped. (The change is confined to the internal `events` subquery of the `employee_eligibility` CTE; no `final_output` projection changes.)

**Check**: `DESCRIBE fct_workforce_snapshot` is identical before/after.

## C2 — Row grain unchanged

One row per `(scenario_id, plan_design_id, employee_id, simulation_year)` (the model's incremental `unique_key`). No new duplicates; no dropped employees.

**Check**: `SELECT COUNT(*)` and `SELECT COUNT(*) FROM (SELECT scenario_id, plan_design_id, employee_id, simulation_year FROM fct_workforce_snapshot GROUP BY ALL HAVING COUNT(*) > 1)` (must be 0) are identical before/after.

## C3 — Zero-diff invariant (the core guarantee)

For an identical configuration and random seed, every cell of `fct_workforce_snapshot` MUST equal the `main` baseline, across all simulation years.

**Check** (per year, full-row hash diff):

```sql
-- run against baseline DB and rewrite DB; result sets must be identical
SELECT simulation_year,
       COUNT(*)                                          AS n,
       SUM(hash(COLUMNS(*))::HUGEINT)                    AS row_hash_sum
FROM fct_workforce_snapshot
GROUP BY simulation_year
ORDER BY simulation_year;
```

Plus an explicit anti-join (see quickstart.md) confirming zero rows differ on the eligibility-relevant columns: `employee_eligibility_date`, `waiting_period_days`, `current_eligibility_status`, `employee_enrollment_date`, `is_enrolled_flag` (or whatever subset surfaces into the final output).

## C4 — dbt schema tests stay green

All existing tests on `fct_workforce_snapshot` (uniqueness on grain, not-null keys) MUST pass after the change.

**Check**: `dbt test --select fct_workforce_snapshot --threads 1`.

## C5 — Scan-count reduction (performance evidence, non-blocking on magnitude)

The compiled subsequent-years query MUST reference `fct_yearly_events` for eligibility resolution **once** (window form), not twice (outer + correlated inner). No wall-clock regression on the `fct_workforce_snapshot` stage.

**Check**: inspect compiled SQL in `target/compiled/...`; compare stage timing baseline vs rewrite from `planalign simulate` output.

## Non-goals (explicitly NOT part of this contract)

- Activating or removing the dead `determination_type='initial'` join (deferred — research R2).
- Any change to the year-1 (`simulation_year == start_year`) branch.
- Any change to enrollment, contribution, or compensation columns.
