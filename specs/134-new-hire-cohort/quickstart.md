# Quickstart: Verifying New-Hire Cohort Isolation

How to verify the `cohort` filter, following the isolated-DB rule in `CLAUDE.md` §8 — never validate against the shared `dbt/simulation.duckdb`.

## 1. Build two isolated scenario databases with a multi-year horizon

A single-year run will not exercise the behavior that motivates this feature (new-hire share needs years to grow).

```bash
source .venv/bin/activate
planalign batch --scenarios baseline generous_match --clean
```

This writes `baseline.duckdb` and `generous_match.duckdb` under a timestamped directory — never `dbt/simulation.duckdb`.

## 2. Confirm the ground truth in DuckDB directly

```bash
duckdb <scenario>.duckdb "
  SELECT simulation_year,
         employee_hire_date >= (SELECT MIN(simulation_year) FROM fct_workforce_snapshot) || '-01-01' AS is_new_hire,
         COUNT(*),
         SUM(employer_match_amount + employer_core_amount) AS employer_cost
  FROM fct_workforce_snapshot
  GROUP BY 1, 2 ORDER BY 1, 2"
```

Confirm the `is_new_hire = true` and `is_new_hire = false` rows' `employer_cost` sum to the unfiltered per-year total.

## 3. Confirm the API returns the same split

```bash
planalign studio --api-only
```

```bash
curl -s "http://127.0.0.1:8000/api/workspaces/<ws>/scenarios/<scenario>/analytics/dc-plan?cohort=all" | jq '.contribution_by_year[] | {year, total_employer_cost}'
curl -s "http://127.0.0.1:8000/api/workspaces/<ws>/scenarios/<scenario>/analytics/dc-plan?cohort=new_hires" | jq '.contribution_by_year[] | {year, total_employer_cost}'
curl -s "http://127.0.0.1:8000/api/workspaces/<ws>/scenarios/<scenario>/analytics/dc-plan?cohort=baseline" | jq '.contribution_by_year[] | {year, total_employer_cost}'
```

For every year, `new_hires.total_employer_cost + baseline.total_employer_cost == all.total_employer_cost`. `cohort=all` must match the pre-feature response for the same scenario (no `cohort` param at all should also produce this response — regression guard).

```bash
curl -s "http://127.0.0.1:8000/api/workspaces/<ws>/scenarios/<scenario>/analytics/dc-plan?cohort=not_a_value" -o /dev/null -w '%{http_code}\n'
# expect: 422
```

## 4. Confirm the Studio UI

```bash
planalign studio
```

Open Cost Comparison, select the two scenarios from step 1, switch the cohort control through all three values, and confirm:
- the cost matrix, incremental-cost chart, and methodology panel all update
- a badge appears on non-default cohorts naming the resolved first simulation year
- reloading the page restores the last-selected cohort
- copy-to-TSV on the matrix includes the cohort label when non-default

## 5. Run the automated contract tests

```bash
pytest tests/ -k "cohort" -v
```
