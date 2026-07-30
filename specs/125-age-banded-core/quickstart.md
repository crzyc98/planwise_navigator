# Quickstart: Validate Age-Banded Employer Core Contributions

## Prerequisites

- Activate the project environment: `source .venv/bin/activate`
- Work from branch `125-age-banded-core`.
- Use a disposable scenario database; do not run behavioral validation against `dbt/simulation.duckdb`.

## 1. Run focused configuration tests

```bash
pytest tests/unit/orchestrator/test_config_export.py -q
pytest tests/unit/config/test_core_contribution_validation.py -q
```

Expected outcomes:

- Direct YAML and Studio schedule paths export `employer_core_age_schedule` with percentage-valued dbt rates.
- A valid contiguous schedule is accepted.
- Gaps, overlaps, reversed/equal ranges, negative rates, and a nonfinal open-ended tier fail before simulation.
- An empty age schedule retains the flat fallback.

## 2. Run core calculation and regression coverage in an isolated database

```bash
pytest tests/integration/test_age_banded_core_contributions.py -v
```

The test builds its own disposable databases under pytest's `tmp_path` and sets
`DATABASE_PATH` per run, so no environment prefix is needed; each session-scoped
fixture asserts on teardown that `dbt/simulation.duckdb` was left untouched.
Six short simulations run (~3.5 minutes total): 2025 only for the exact tier
boundaries, 2025-2026 for annual tier migration, an empty-schedule run for the
flat fallback, and one run each for the flat, service-graded, and points-based
modes against the same census. `int_employer_core_contributions` is a table
materialization that retains only a run's final year, which is why the boundary
year and the migration year are separate runs.

Expected outcomes:

- Exact boundary ages use the higher tier.
- Employees move tiers across simulation years as annual age changes.
- A mid-year hire uses prorated compensation with an unprorated selected rate.
- The audited rate and reported core amount agree under every core mode.
- Existing flat, service-graded, and points-based fixtures retain their prior outputs.

## 3. Run the complete feature scenario

```bash
planalign batch --scenarios age_banded_core --clean
```

Query that scenario’s isolated database after the run. Use the schedule bounds rather than reporting age bands to group the result:

```sql
SELECT
  ec.simulation_year,
  CASE
    WHEN ws.current_age >= 50 THEN '50+'
    WHEN ws.current_age >= 40 THEN '40-49'
    WHEN ws.current_age >= 30 THEN '30-39'
    ELSE '0-29'
  END AS applied_age_tier,
  COUNT(*) AS employees,
  AVG(ec.core_contribution_rate) AS average_core_rate,
  SUM(ec.employer_core_amount) AS core_amount
FROM int_employer_core_contributions ec
JOIN int_workforce_state_accumulator ws
  ON ws.employee_id = ec.employee_id
 AND ws.simulation_year = ec.simulation_year
 AND ws.scenario_id = ec.scenario_id
WHERE ec.scenario_id = 'age_banded_core'
GROUP BY 1, 2
ORDER BY 1, 2;
```

Expected outcomes: every eligible employee has the rate for their annual age tier, and cohorts move upward between tiers over time.

## 4. Verify the presentation and caveat

```bash
cd planalign_studio && npm run build
cd .. && pytest tests/test_ndt_401a4.py -q
```

Expected outcomes: Studio exposes and accurately summarizes age-banded core schedules, and a passing age-banded 401(a)(4) result still displays the required nondiscrimination-review caveat.
