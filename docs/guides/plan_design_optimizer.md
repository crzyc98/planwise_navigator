# Plan-design optimizer

The plan-design optimizer searches a declared, bounded set of plan levers and
returns auditable candidates ranked against explicit objectives and hard
constraints. Every candidate is a normal isolated simulation with its own
DuckDB database; the optimizer never writes to `dbt/simulation.duckdb`.

## Run an optimization

Create a YAML spec and state a hard run budget on every invocation:

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

```bash
source .venv/bin/activate

planalign optimize var/optimizer_specs/cost_vs_participation.yaml \
  --max-runs 20 \
  --seed 42 \
  --database /tmp/planalign_optimizer/run-001
```

`--max-runs` is mandatory and counts distinct scenario evaluations. A failed
candidate consumes one budget unit and is not retried. An exact duplicate
reuses the earlier result and does not consume another unit. The search seed
controls only the deterministic candidate path; each candidate retains the
baseline simulation seed.

Use `--dry-run` to validate the spec and inspect the initial candidate plan
without creating databases or consuming budget. Use `--parallel N` to request
the same memory-aware worker-pool behavior as batch and ensemble runs.

## Supported spec shape

Version 1 accepts zero to eight mixed levers. Continuous levers require
inclusive `[min, max]` bounds; discrete levers require non-empty choices.
Supported areas are match tiers/caps, auto-enrollment rate/scope, escalation,
eligibility, and vesting-schedule choice. Every undeclared configuration field
is structurally pinned to the baseline.

One objective produces a ranked feasible list. Two objectives produce a
Pareto frontier. The point-estimate metric vocabulary matches seed ensembles:
headcount, compensation, match cost, total employer plan cost, participation,
and average deferral rate. `irs_compliance_pass` is available as a constraint.

## Budget and reporting guardrails

The optimizer stops when the declared budget is exhausted, regardless of
convergence. Every evaluated candidate remains in the ledger as `feasible`,
`infeasible`, `non_evaluable`, or `failed`; missing metrics are never changed
to zero. When no candidate is feasible, `report.md` names any constraint that
no candidate satisfied.

Re-running the same validated spec with the same search seed evaluates the
same candidate sequence. Baseline fingerprints are persisted with the run so
automation can warn when a later run resolves a different baseline.

## Percentile constraints

Point estimates are always the default. A percentile is used only when it is
explicitly declared and `baseline.ensemble_database` points to a pre-existing
ensemble aggregate database:

```yaml
constraints:
  - metric: total_employer_plan_cost
    operator: "<="
    threshold: 2400000
    percentile: 90
baseline:
  config_path: config/simulation_config.yaml
  ensemble_database: /tmp/ensemble/ensemble.duckdb
```

The optimizer reads the ensemble's retained `fct_metric_seed_values` and uses
linear quantiles. If percentile evidence is unavailable, evaluation falls back
to the candidate point estimate and labels the mode `point_estimate`.

## Outputs and drill-down

The output directory contains the resolved `spec.yaml`, `candidates.csv`,
`optimizer_results.xlsx`, `optimizer_results.json`, and `report.md`. The
workbook adds a `Pareto Frontier` sheet only for a two-objective run. Candidate
databases remain beneath `candidates/candidate-NNNN/scenario.duckdb` and can be
queried without re-running the search.

## Cost and validation

Search cost is dominated by scenario runs: approximately 90–120 seconds per
five-year candidate at measured development/client scale. Approximate wall
time is `max_runs / workers × per-run time`; choose the budget before launching
a client-scale run.

Validate changes only with isolated paths:

```bash
pytest -m fast tests/test_optimizer_spec_io.py tests/test_optimizer_design_space.py \
  tests/test_optimizer_evaluate.py tests/test_optimizer_search.py \
  tests/test_optimizer_pareto.py tests/test_optimizer_export.py \
  tests/test_optimizer_metrics.py

DATABASE_PATH=/tmp/optimizer_validation/isolated.duckdb \
  pytest -m integration tests/test_optimizer_end_to_end.py
```
