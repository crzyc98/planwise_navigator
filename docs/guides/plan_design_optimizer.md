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

## Experimental first-year screening benchmark

The research-only screening modules live under `scripts/perf_profile/` and are
not included in the installed optimizer package.

Before adding a cheaper evaluation mode, measure its decision quality using
the paired benchmark. This research tool evaluates the same fixed designs at
one year and across the full baseline horizon, then independently reruns the
retained designs at full fidelity to measure actual staged wall time. It uses
the normal optimizer evaluator and the same worker limit for every stage.
It does not change `planalign optimize` or produce promotable optimizer results.

From the repository root, use the checked-in synthetic census and edge spec:

```bash
source .venv/bin/activate
PYTHONPATH=. python scripts/benchmark_optimizer_screening.py \
  --spec tests/fixtures/optimizer_screening.yaml \
  --census-csv tests/fixtures/invariant_census.csv \
  --output var/optimizer_screening/experiment-001 \
  --candidates 8 --repetitions 3 --max-simulations 72 --parallel 2
```

The output root must be fresh. `--max-simulations` must reserve the worst-case
`3 × candidates × repetitions`: full-reference runs, screens, and retained
full reruns. Failed evaluations count; there are no retries. A finite design
space can yield fewer designs than requested. The settings, spec, and resolved
baseline are saved before evaluation; `benchmark.json` and `report.md` retain
the paired ledgers, fidelity horizons, selection reasons, replay checks,
wall times, and sampled process-tree RSS. The completed CLI artifact also
records input/code hashes and environment versions.

The experimental policy keeps first-year feasible candidates, missing/failed
evidence, unsupported screening constraints, and candidates within 5% of a
violated constraint boundary. It audits a deterministic 10% of the remaining
rejections (rounded up). Low-fidelity infeasibility is only a screening signal;
full-reference results measure false rejection. There is no filtering solely
by the apparent first-year Pareto frontier.

The prespecified gate requires at least 1.5x measured speedup, no rejected
full-horizon feasible designs, and exact replay of retained full results.
Three complete repetitions with feasible evidence are required even for
`GO_FOR_EXPANDED_BENCHMARK`. That result authorizes further investigation, not
production rollout. A failed gate yields `NO_GO`; incomplete evidence yields
`INSUFFICIENT_EVIDENCE`. Percentile constraints and external ensemble inputs
are rejected by this point-estimate experiment.

Point metrics refer to the latest year of each fidelity. For example, screening
participation in 2025 does not prove a participation constraint for 2027.
Employer cost is terminal-year cost, not the sum of annual costs. Compare
screening against the existing parallel evaluator at equal worker limits;
do not infer speedup from rejected-candidate percentages alone.

See [the feasibility plan and pilot results](../perf/optimizer_screening.md)
for the tested workload, decision, and limits of the evidence.
