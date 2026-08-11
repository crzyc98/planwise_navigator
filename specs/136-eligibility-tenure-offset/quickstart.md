# Quickstart: Validate Employer Contribution Service Credit

## Prerequisites

- Activate the project environment: `source .venv/bin/activate`
- Use only disposable scenario databases; never build behavioral validation into `dbt/simulation.duckdb`.

## 1. Run focused invariant and integration tests

```bash
pytest tests/test_employer_eligibility_invariants.py -q
pytest tests/integration/test_employer_eligibility_tenure.py -v
```

The integration module creates one isolated DuckDB file per configuration under pytest `tmp_path`, sets `DATABASE_PATH` for each run, and verifies the shared dev database is unchanged.

Expected outcomes:

- Eligibility, core audit service, and service-dependent match audit service exactly match the current-year workforce accumulator.
- A deliberately offset fixture/query is reported as a violation.
- Employees below enforced 2- and 3-year requirements receive neither core nor match contributions unless an existing explicit exception applies.
- The 1-, 2-, and 3-year core cost curves remain distinct across every year of the five-year projection.
- Opening-year characterization and the zero-wait scenario remain unchanged.
- Mid-year termination service stops at the termination date, and a reset service record is not reconstructed from prior years.

## 2. Produce disposable five-year and termination-tier results

```bash
export PLANALIGN_136_RUN_DIR="$(mktemp -d /tmp/planalign136.XXXXXX)"
python - <<'PY'
import os
from pathlib import Path

from tests.fixtures.employer_eligibility_tenure import (
    prepare_census_parquet,
    run_termination_rate_case,
    run_wait_case,
)

run_dir = Path(os.environ["PLANALIGN_136_RUN_DIR"])
census = prepare_census_parquet(run_dir / "census.parquet")
run_wait_case(2, run_dir / "service_credit.duckdb", census)
run_termination_rate_case(run_dir / "termination_tiers.duckdb", census)
print(run_dir)
PY
```

Review annual cost and final-year service qualification:

```bash
python - <<'PY'
import os
import duckdb

database = os.path.join(os.environ["PLANALIGN_136_RUN_DIR"], "service_credit.duckdb")
with duckdb.connect(database, read_only=True) as connection:
    print(connection.execute("""
        SELECT simulation_year,
               ROUND(SUM(employer_core_amount), 2) AS core_cost,
               ROUND(SUM(employer_match_amount), 2) AS match_cost
        FROM fct_workforce_snapshot
        GROUP BY simulation_year
        ORDER BY simulation_year
    """).fetchall())
    print(connection.execute("""
        SELECT COUNT(*) AS mismatches
        FROM int_employer_eligibility eligibility
        JOIN int_workforce_state_accumulator workforce
          ON workforce.employee_id = eligibility.employee_id
         AND workforce.simulation_year = eligibility.simulation_year
         AND workforce.scenario_id = 'service_wait_2'
         AND workforce.plan_design_id = 'service_credit_plan'
        WHERE eligibility.current_tenure IS DISTINCT FROM workforce.current_tenure
    """).fetchone())
PY
```

Expected outcomes: five annual cost rows are present and the mismatch query returns `0`. The pytest suite performs the stronger comparison across the 0-, 1-, 2-, and 3-year configurations and validates retained employee-year outcomes.

## 3. Run dbt data tests against the disposable database

Run dbt from `dbt/` with one thread and the explicit database path:

```bash
cd dbt
DATABASE_PATH="$PLANALIGN_136_RUN_DIR/termination_tiers.duckdb" dbt test \
  --select assert_employer_eligibility_service_matches_workforce \
           assert_employer_tenure_requirements_enforced \
           test_audit_trail_core_contributions \
           test_service_match_boundaries \
  --vars '{simulation_year: 2026, scenario_id: service_termination_tiers, plan_design_id: service_credit_plan, employer_match_status: tenure_graded}' \
  --threads 1
cd ..
```

Expected outcome: all tests return zero violating rows. Reintroducing the prior-year service offset makes the eligibility and audit reconciliation checks fail.

The fixture YAML files intentionally contain `census_parquet_path: injected`.
Use the Python fixture builder above (or pytest), which creates a synthetic
Parquet census and injects its disposable path before orchestration.

## 4. Run the broader targeted gate

```bash
pytest -m fast -q
```

Expected outcome: existing configuration, eligibility, contribution, and audit behavior remains green outside the corrected service basis.
