# Quickstart: Verifying Explicit New-Hire Enrollment Rates

**Feature**: 652-flat-newhire-enrollment-rates

Every step runs against an isolated database. Nothing here touches `dbt/simulation.duckdb` — running dbt against the shared dev DB would overwrite state other work depends on.

```bash
source .venv/bin/activate
export RUN=/tmp/run/652 && mkdir -p $RUN
```

---

## Step 1 — Settle Risk 1 before implementing (Phase A, blocking)

SC-004 targets ~0% not-enrolled new hires. Research R6 predicts a permanent floor from new hires who terminate inside their 45-day auto-enrollment window. Confirm the mechanism on an existing run before building against the target.

```sql
-- Against a database from a scope=all_eligible, auto_enroll=true run
SELECT
  s.simulation_year,
  COUNT(*)                                            AS not_enrolled_new_hires,
  COUNT(t.employee_id)                                AS terminated_in_hire_year,
  COUNT(*) FILTER (WHERE NOT COALESCE(e.is_plan_eligible, TRUE)) AS plan_ineligible
FROM fct_workforce_snapshot s
LEFT JOIN int_employee_termination_dates t
  ON s.employee_id = t.employee_id AND s.simulation_year = t.simulation_year
LEFT JOIN int_plan_eligibility_determination e
  ON s.employee_id = e.employee_id AND s.simulation_year = e.simulation_year
WHERE EXTRACT(YEAR FROM s.employee_hire_date) = s.simulation_year
  AND s.participation_status_detail = 'not_participating - not auto enrolled'
GROUP BY 1 ORDER BY 1;
```

**If `terminated_in_hire_year` accounts for most of the residual**, amend SC-004 in `spec.md` to measure new hires active at year end, and re-run the requirements checklist. Do not adjust event effective dates to make the number move — that would falsify the event history to satisfy a metric.

---

## Step 2 — Baseline for the compatibility guarantee (SC-006, SC-009)

Capture new-hire enrollment counts from a scenario that sets neither rate, before any code change.

```bash
cp config/simulation_config.yaml $RUN/unset.yaml   # ensure neither rate is set
DATABASE_PATH=$RUN/baseline.duckdb \
  planalign simulate 2025-2029 --config $RUN/unset.yaml --database $RUN/baseline.duckdb
```

```sql
SELECT simulation_year, participation_status_detail, COUNT(*)
FROM fct_workforce_snapshot
WHERE EXTRACT(YEAR FROM employee_hire_date) = simulation_year
GROUP BY 1, 2 ORDER BY 1, 2;
```

Save the output. After Phase C and again after Phase G, re-run with the same config and assert the counts are **identical**, not merely close. Phase C's deletion of the inert multiplier is provably a no-op (R1); if these counts move, that reasoning is wrong and the phase should stop.

---

## Step 3 — The three acceptance configurations (SC-001 through SC-004)

```bash
# A: P=0.6, Q=0.1  -> expect 60% voluntary / 36% auto / 4% opted out / 0% not enrolled
# B: P=1.0         -> expect ~100% voluntary
# C: P=0.0, Q=0.0  -> expect 100% auto-enrolled and participating
for s in a b c; do
  DATABASE_PATH=$RUN/$s.duckdb \
    planalign simulate 2025-2029 --config $RUN/$s.yaml --database $RUN/$s.duckdb
done
```

Each config sets `auto_enrollment.enabled: true` and `scope: all_eligible_employees`, so the whole eligible new-hire cohort is in auto-enrollment scope and the four-outcome guarantee applies.

```sql
SELECT
  simulation_year,
  participation_status_detail,
  COUNT(*) AS n,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY simulation_year), 1) AS pct
FROM fct_workforce_snapshot
WHERE EXTRACT(YEAR FROM employee_hire_date) = simulation_year
GROUP BY 1, 2 ORDER BY 1, 2;
```

Compare `pct` against the expectation for each config, in **every** year — a single-year check would hide the cohort-size sensitivity described in R7.

---

## Step 4 — Determinism (SC-005)

Counts matching is not the criterion; the same individuals must be selected.

```bash
DATABASE_PATH=$RUN/a2.duckdb \
  planalign simulate 2025-2029 --config $RUN/a.yaml --database $RUN/a2.duckdb
```

```sql
ATTACH '/tmp/run/652/a.duckdb'  AS r1 (READ_ONLY);
ATTACH '/tmp/run/652/a2.duckdb' AS r2 (READ_ONLY);

SELECT COUNT(*) AS employees_differing FROM (
  SELECT employee_id, simulation_year FROM r1.fct_yearly_events
  WHERE event_category = 'voluntary_enrollment'
  EXCEPT
  SELECT employee_id, simulation_year FROM r2.fct_yearly_events
  WHERE event_category = 'voluntary_enrollment'
);
-- must be 0
```

Repeat with `event_category = 'enrollment_opt_out'`.

---

## Step 5 — Single decision per new hire (FR-004)

No new hire may appear with more than one enrollment event in a year, and `proactive_voluntary` must not be produced when the flat rate is set.

```sql
SELECT event_category, COUNT(*)
FROM fct_yearly_events
WHERE event_type = 'enrollment'
GROUP BY 1 ORDER BY 2 DESC;
-- 'proactive_voluntary' must be absent in runs A, B and C

SELECT COUNT(*) AS employees_with_multiple_enrollments FROM (
  SELECT employee_id, simulation_year
  FROM fct_yearly_events WHERE event_type = 'enrollment'
  GROUP BY 1, 2 HAVING COUNT(*) > 1
);
-- must be 0
```

---

## Step 6 — Enrollment method labeling (FR-011, R4)

The accumulator's alias list omits `proactive_voluntary`, so proactive enrollments currently reach the voluntary bucket only through a NULL-method fallback. After the fix, no enrolled employee should carry an unresolved method.

```sql
SELECT COUNT(*) AS unresolved_method
FROM fct_workforce_snapshot
WHERE participation_status_detail = 'participating - unknown source';
-- must be 0
```

---

## Step 7 — Fast tests

```bash
pytest -m "fast and config" -v
pytest tests/unit/orchestrator/test_config_export.py -v
```

Covers FR-008 validation, the set/unset export convention, and the `0.0`-is-not-`None` distinction.
