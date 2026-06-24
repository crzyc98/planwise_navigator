# Quickstart: Validating Same-Year Enroll → Opt-Out Window Proration

> **Rule:** validate in an **isolated** database — never `dbt/simulation.duckdb`. Run a **full multi-year** simulation so the enroll→opt-out cohort actually materializes.

## 0. Prerequisites

```bash
source .venv/bin/activate
python -c "import planalign_orchestrator"   # sqlparse token fix
```

## 1. Build an isolated scenario that produces same-year enroll → opt-out

Use a config that yields voluntary enrollments **and** opt-outs in-year: voluntary enrollment enabled, non-zero opt-out rates, auto-enrollment optional. Run into an isolated DB:

```bash
DATABASE_PATH=/tmp/run101/iso.duckdb \
  planalign simulate 2025-2027 --config /tmp/run101/cfg.yaml --database /tmp/run101/iso.duckdb
```

## 2. Find a same-year enroll → opt-out employee

```bash
duckdb /tmp/run101/iso.duckdb "
WITH ev AS (
  SELECT employee_id, simulation_year,
         MAX(CASE WHEN event_type='enrollment' THEN effective_date END) AS enroll_dt,
         MAX(CASE WHEN event_type='enrollment_change' AND LOWER(event_details) LIKE '%opt-out%' THEN effective_date END) AS optout_dt
  FROM fct_yearly_events
  GROUP BY 1,2)
SELECT * FROM ev WHERE enroll_dt IS NOT NULL AND optout_dt IS NOT NULL AND optout_dt >= enroll_dt LIMIT 5"
```

## 3. Assert the fix (US1 / SC-001, US2 / SC-004)

For a chosen `<emp>` / `<year>`:

```bash
duckdb /tmp/run101/iso.duckdb "
SELECT c.employee_id,
       c.active_enrollment_days,
       c.effective_annual_deferral_rate,
       c.prorated_annual_compensation,
       c.total_contribution_base_compensation,
       c.annual_contribution_amount,
       m.employer_match_amount
FROM int_employee_contributions c
LEFT JOIN fct_employer_match_events m
  ON c.employee_id = m.employee_id AND c.simulation_year = m.simulation_year
WHERE c.employee_id = '<emp>' AND c.simulation_year = <year>"
```

**PASS:**
- `annual_contribution_amount > 0` (was `$0` pre-fix) — SC-001.
- `total_contribution_base_compensation < prorated_annual_compensation` (windowed) and `prorated_annual_compensation` matches the employee's employment-window comp (unchanged).
- `employer_match_amount > 0` and consistent with the windowed contribution + match formula — SC-004.

## 4. Year-end status unchanged (US1 / SC-003)

```bash
duckdb /tmp/run101/iso.duckdb "
SELECT employee_id, participation_status, current_deferral_rate
FROM fct_workforce_snapshot
WHERE employee_id='<emp>' AND simulation_year=<year>"
# Expect: not_participating, 0.0
```

## 5. No regression on the non-opt-out path (SC-005)

Pick an employee who enrolled and did **not** opt out; confirm `total_contribution_base_compensation = prorated_annual_compensation` and `annual_contribution_amount` is unchanged vs. a pre-change baseline build of the same scenario.

## 6. Guard (US3 / SC-006)

```bash
cd dbt
DATABASE_PATH=/tmp/run101/iso.duckdb dbt test --select assert_same_year_enroll_optout_window --vars '{"simulation_year": 2026}' --threads 1
# Passes at enforcing severity once implemented; temporarily reverting the crediting must fail the build.
```

## 7. Degenerate windows (FR-007)

Confirm no negative contributions for same-day or out-of-order enroll/opt-out (filter `active_enrollment_days = 0` and assert `annual_contribution_amount = 0`).
