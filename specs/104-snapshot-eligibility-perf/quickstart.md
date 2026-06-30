# Quickstart: Validate the Eligibility Decorrelation

**Feature**: 104-snapshot-eligibility-perf | **Date**: 2026-06-29

Goal: prove the rewrite is **byte-identical** to `main` and does not regress build time, using **isolated** databases (never `dbt/simulation.duckdb`), per `CLAUDE.md` §8. Capture the baseline **before** editing the model.

## 0. Prereqs

```bash
source .venv/bin/activate
mkdir -p /tmp/feat104
```

## 1. Capture baseline (on current `main`, BEFORE the edit)

```bash
# Default config, multi-year, isolated DB
DATABASE_PATH=/tmp/feat104/baseline.duckdb \
  planalign simulate 2025-2027 --database /tmp/feat104/baseline.duckdb 2>&1 | tee /tmp/feat104/baseline.log
```

Record the `fct_workforce_snapshot` stage timing from `baseline.log`.

## 2. Edge config (required by SC-004)

Build a second baseline under an edge configuration that actually exercises eligibility — e.g. broad auto-enrollment scope with an early eligibility cutoff:

```bash
cp config/simulation_config.yaml /tmp/feat104/edge.yaml
# edit /tmp/feat104/edge.yaml: auto_enrollment_scope: all_eligible_employees + early hire-date cutoff
DATABASE_PATH=/tmp/feat104/baseline_edge.duckdb \
  planalign simulate 2025-2027 --config /tmp/feat104/edge.yaml --database /tmp/feat104/baseline_edge.duckdb
```

## 3. Apply the rewrite

Edit only the `events` subquery inside the `employee_eligibility` CTE, subsequent-years (`{% else %}`) branch of `dbt/models/marts/fct_workforce_snapshot.sql`, per research.md R1. Keep the `determination_type='initial'` predicate verbatim (research R2).

## 4. Re-run into fresh isolated DBs

```bash
DATABASE_PATH=/tmp/feat104/rewrite.duckdb \
  planalign simulate 2025-2027 --database /tmp/feat104/rewrite.duckdb 2>&1 | tee /tmp/feat104/rewrite.log

DATABASE_PATH=/tmp/feat104/rewrite_edge.duckdb \
  planalign simulate 2025-2027 --config /tmp/feat104/edge.yaml --database /tmp/feat104/rewrite_edge.duckdb
```

## 5. Diff: zero rows must differ (C3)

```bash
# Default config — per-year row hash must match exactly
duckdb -c "
ATTACH '/tmp/feat104/baseline.duckdb' AS b (READ_ONLY);
ATTACH '/tmp/feat104/rewrite.duckdb'  AS r (READ_ONLY);
WITH bb AS (SELECT simulation_year, COUNT(*) n, SUM(hash(COLUMNS(*))::HUGEINT) h FROM b.fct_workforce_snapshot GROUP BY 1),
     rr AS (SELECT simulation_year, COUNT(*) n, SUM(hash(COLUMNS(*))::HUGEINT) h FROM r.fct_workforce_snapshot GROUP BY 1)
SELECT bb.simulation_year, bb.n AS base_n, rr.n AS rew_n,
       (bb.h = rr.h) AS hashes_match
FROM bb JOIN rr USING (simulation_year)
ORDER BY 1;
"
```

Every `hashes_match` must be `true` and `base_n = rew_n`. Repeat the same diff for `baseline_edge.duckdb` vs `rewrite_edge.duckdb` (SC-004).

Targeted eligibility-column anti-join (belt-and-suspenders):

```bash
duckdb -c "
ATTACH '/tmp/feat104/baseline.duckdb' AS b (READ_ONLY);
ATTACH '/tmp/feat104/rewrite.duckdb'  AS r (READ_ONLY);
SELECT COUNT(*) AS differing_rows FROM (
  SELECT employee_id, simulation_year, employee_eligibility_date, waiting_period_days,
         current_eligibility_status, employee_enrollment_date, is_enrolled_flag
  FROM b.fct_workforce_snapshot
  EXCEPT
  SELECT employee_id, simulation_year, employee_eligibility_date, waiting_period_days,
         current_eligibility_status, employee_enrollment_date, is_enrolled_flag
  FROM r.fct_workforce_snapshot
);
"
```

`differing_rows` must be `0`.

## 6. dbt tests + fast suite (C4)

```bash
cd dbt && DATABASE_PATH=/tmp/feat104/rewrite.duckdb dbt test --select fct_workforce_snapshot --threads 1; cd ..
pytest -m fast
```

## 7. Performance (C5)

- Confirm the rewrite's `fct_workforce_snapshot` stage time in `rewrite.log` ≤ baseline's in `baseline.log`.
- Inspect `dbt/target/compiled/.../fct_workforce_snapshot.sql` and confirm the eligibility CTE references `fct_yearly_events` once (no correlated inner re-scan).

## Pass criteria (maps to spec Success Criteria)

| Check | Spec |
|-------|------|
| All `hashes_match = true`, equal row counts (default + edge) | SC-001, SC-004 |
| `differing_rows = 0` | SC-001 |
| Compiled eligibility CTE scans `fct_yearly_events` once | SC-002, SC-005 |
| Stage time ≤ baseline | SC-003 |
| dbt tests + `pytest -m fast` green | C4 |
