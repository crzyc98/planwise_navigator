# Quickstart: Plan-Design Optimizer

Worked example matching the spec's exit criteria: match formula tier rate × auto-enrollment default rate, minimizing employer cost subject to a participation floor.

## 1. Write a design-space + objective spec

`var/optimizer_specs/cost_vs_participation.yaml`:

```yaml
design_space:
  levers:
    - name: employer_match.tier_1_rate
      kind: continuous
      bounds: [0.03, 0.06]
    - name: auto_enrollment.default_deferral_rate
      kind: continuous
      bounds: [0.03, 0.08]

objective:
  objectives:
    - metric: total_employer_plan_cost
      direction: minimize
  constraints:
    - metric: participation_rate
      operator: ">="
      threshold: 0.85

baseline:
  config_path: config/simulation_config.yaml
```

## 2. Run the optimizer with a bounded budget

```bash
source .venv/bin/activate

planalign optimize var/optimizer_specs/cost_vs_participation.yaml \
  --max-runs 20 \
  --seed 42 \
  --database var/optimizer_runs/cost_vs_participation
```

The command prints the resolved worker budget, then evaluates up to 20 candidate designs — never more, per the mandatory `--max-runs` cap — reporting progress as each candidate's isolated scenario run completes.

## 3. Inspect the ranked result

```bash
duckdb var/optimizer_runs/cost_vs_participation/*/candidates.csv 2>/dev/null || \
  cat var/optimizer_runs/cost_vs_participation/*/report.md
```

Expect: a ranked table of feasible candidates (participation ≥ 85%) ordered by ascending `total_employer_plan_cost`, plus every infeasible/non-evaluable/failed candidate reported separately rather than omitted.

## 4. Drill into the top candidate

```bash
CANDIDATE_DB=$(find var/optimizer_runs/cost_vs_participation -name scenario.duckdb | head -1)
duckdb "$CANDIDATE_DB" "SELECT simulation_year, active_headcount, total_employer_contributions FROM fct_workforce_snapshot ORDER BY simulation_year"
```

Every candidate's underlying `.duckdb` remains queryable after the run completes — no re-run required (FR-014).

## 5. Reproduce the same search

```bash
planalign optimize var/optimizer_specs/cost_vs_participation.yaml --max-runs 20 --seed 42 \
  --database var/optimizer_runs/cost_vs_participation_rerun
```

The same spec + `--seed 42` evaluates the identical sequence of candidate configurations and produces the identical ranked output (FR-010, SC-003).

## 6. A two-objective tradeoff (Pareto frontier)

```yaml
objective:
  objectives:
    - metric: total_employer_plan_cost
      direction: minimize
    - metric: participation_rate
      direction: maximize
```

Re-running the optimizer against a spec shaped this way adds a Pareto-frontier section to `report.md` and an extra sheet in `optimizer_results.xlsx`, distinguishing frontier candidates from dominated ones (FR-009).

## Validating this feature during development

Per the project's isolated-database rule, never point `--database` at `dbt/simulation.duckdb`. Use a small, fast baseline for iteration:

```bash
DATABASE_PATH=/tmp/optimizer_dev/iso.duckdb \
  pytest -m fast tests/test_optimizer_spec_io.py tests/test_optimizer_design_space.py \
    tests/test_optimizer_evaluate.py tests/test_optimizer_search.py \
    tests/test_optimizer_pareto.py tests/test_optimizer_export.py tests/test_optimizer_metrics.py

pytest -m integration tests/test_optimizer_end_to_end.py
```
