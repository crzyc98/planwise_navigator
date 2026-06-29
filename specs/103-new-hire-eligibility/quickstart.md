# Quickstart: New-Hire Eligibility Rate + Census Eligibility Override

Validate the feature on an **isolated** multi-year database (never the shared `dbt/simulation.duckdb`), per CLAUDE.md §8 and [[validate-in-isolated-db]].

## 1. Default = byte-for-byte identical (SC-001 / FR-013)

```bash
# Baseline run (defaults: dial 0.0, match_census false, no census column)
cp config/simulation_config.yaml /tmp/elig/base.yaml
DATABASE_PATH=/tmp/elig/base.duckdb \
  planalign simulate 2025-2027 --config /tmp/elig/base.yaml --database /tmp/elig/base.duckdb

# Re-run into a second isolated DB and diff key marts — expect zero differences
```

## 2. New-hire dial = ~10% ineligible (SC-002 / User Story 1)

```yaml
# /tmp/elig/dial.yaml
eligibility:
  new_hire_ineligible_pct: 0.10
```

```bash
DATABASE_PATH=/tmp/elig/dial.duckdb \
  planalign simulate 2025-2027 --config /tmp/elig/dial.yaml --database /tmp/elig/dial.duckdb

# ~10% of each year's NH_* cohort flagged ineligible, with zero enrollment events
duckdb /tmp/elig/dial.duckdb "
  SELECT simulation_year,
         AVG(CASE WHEN is_plan_ineligible_override THEN 1.0 ELSE 0.0 END) AS ineligible_share
  FROM int_plan_eligibility_override
  WHERE employee_id LIKE 'NH_%'
  GROUP BY 1 ORDER BY 1"
```

## 3. Census column = explicit ineligible (SC-003 / User Story 2)

Add an `eligibility_override` column to the census parquet (`FALSE` for known-ineligible employees), then:

```bash
DATABASE_PATH=/tmp/elig/census.duckdb \
  planalign simulate 2025-2027 --config /tmp/elig/census.yaml --database /tmp/elig/census.duckdb

# Every EMP_* with eligibility_override = FALSE has zero enrollment/contribution/match events
duckdb /tmp/elig/census.duckdb "
  SELECT COUNT(*) AS leaks
  FROM fct_yearly_events e
  JOIN int_plan_eligibility_override o USING (employee_id, simulation_year)
  WHERE o.is_plan_ineligible_override
    AND e.event_type IN ('enrollment','contribution','employer_match')"
# Expect: leaks = 0
```

## 4. Census matching (SC-004 / User Story 3)

```yaml
eligibility:
  new_hire_eligibility_match_census: true
```

Realized `NH_*` ineligible share should track `COUNT(eligibility_override = FALSE) / COUNT(*)` over `stg_census_data`; with no census column it falls back to `new_hire_ineligible_pct`.

## 5. Tests

```bash
# Fast: Pydantic validation + to_dbt_vars export
pytest -m fast tests/test_new_hire_eligibility_config.py -v

# dbt schema + data tests against the isolated DB
cd dbt
DATABASE_PATH=/tmp/elig/census.duckdb dbt test --select stg_census_data int_plan_eligibility_override --threads 1
DATABASE_PATH=/tmp/elig/census.duckdb dbt test --select assert_ineligible_no_enrollment --threads 1
```

## Acceptance crosswalk

| Spec | Validated by |
|------|--------------|
| SC-001 / FR-013 | Step 1 double-run diff |
| SC-002 / US1 | Step 2 share query + reproducibility re-run |
| SC-003 / US2 | Step 3 zero-leak query |
| SC-004 / US3 | Step 4 census-matched share |
| FR-009 | `int_eligibility_events` reason/source annotation; no `DC_PLAN_ELIGIBILITY` for overridden |
| FR-011/FR-012 | Step 5 fast tests + census schema tests |
