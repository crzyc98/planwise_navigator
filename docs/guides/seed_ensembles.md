# Seed ensembles

Seed ensembles turn a single scenario result into a distribution over isolated,
reproducible seed worlds. They are useful when a point estimate alone would hide
the spread caused by termination, hiring, and promotion draws.

## Run an ensemble

Activate the project environment and request a seed count. The command creates
one DuckDB database per seed plus a separate aggregate database beneath a
timestamped directory; it never uses `dbt/simulation.duckdb` as an ensemble
target.

```bash
source .venv/bin/activate

planalign simulate 2025-2029 --seeds 25 --database /tmp/planalign_ensembles
```

Use an explicit list when the exact seed worlds need to be part of a review or
reproduction:

```bash
planalign simulate 2025-2029 \
  --seed-list 42,1043,2044,3045 \
  --database /tmp/planalign_ensembles
```

The command prints the resolved seeds, memory-based worker budget, run count,
estimated disk use, and output directory before it starts workers. Completed
seed databases are treated as immutable inputs during aggregation.

## Bands and thin samples

`ensemble.duckdb` contains `fct_metric_seed_values` (the evidence) and
`fct_metric_distributions` (P10/P25/P50/P75/P90, mean, and sample standard
deviation). Percentiles use NumPy's `linear` method over seed-ordered values.

```bash
E=$(find /tmp/planalign_ensembles -name ensemble.duckdb -print -quit)
duckdb "$E" "SELECT metric, simulation_year, p10, p50, p90, n_seeds
             FROM fct_metric_distributions
             ORDER BY metric, simulation_year"
```

The default minimum sample is 10. Below `--min-seeds`, the run succeeds and
retains per-seed values, but every band statistic is `NULL` and
`is_sufficient` is `false`; a withheld percentile is never represented as zero.

## Threshold risk

Attach a threshold at invocation time, or put a reusable threshold in the
scenario config:

```bash
planalign simulate 2025-2029 --seeds 25 \
  --threshold total_employer_plan_cost:2400000
```

```yaml
ensemble:
  thresholds:
    - metric: total_employer_plan_cost
      value: 2400000
      label: Plan cost ceiling
```

For every sufficient metric/year sample, the CLI reports the strict-exceedance
probability and contributing seed count. A metric unavailable from the source
mart is reported as not evaluable rather than silently treated as zero.

## Conditional variance change (EXPERIMENTAL — diagnostic only)

> **This is not variance attribution and must not be presented as one.** It is
> excluded from client-facing workbooks. Read this section before using the
> numbers for anything.

Add `--attribution` to measure, for each of termination, hiring, and promotion,
how the outcome variance changes when that subsystem's seed is pinned.

```bash
planalign simulate 2025-2029 --seeds 25 --attribution --attribution-seeds 10
```

The runner pins only that subsystem's seed while the global seed continues to
vary, compares sample variance over the same paired seed list, and reports:

`1 - Var(Y | subsystem seed = anchor) / Var(Y)`

**The anchor is a single arbitrary value** — the first attribution seed. That is
the central limitation. Conditional variance at one particular anchor can
legitimately be *larger* than marginal variance, because pinning a subsystem
fixes its hash key rather than its realized multi-year event stream, and the
still-varying subsystems interact with it. A measured run showed promotion's
variance 250% *higher* when pinned; that is anchor dependence and interaction,
not an error and not proof of noise.

Consequences, all deliberate:

- Results are **never ranked** — ordering one-anchor numbers implies a
  decomposition that has not been estimated.
- Raw unpinned and pinned variances are printed alongside every value so the
  magnitude is inspectable rather than reduced to a single percentage.
- The anchor seed is disclosed in the output and stored in
  `fct_variance_attribution.anchor_seed`.
- Nothing from this pass reaches the Excel workbook. The evidence stays
  queryable in `fct_variance_attribution`.

A defensible estimator must average conditional variance across **many** anchors
(law of total variance), or use a pick-freeze/Sobol design with genuinely
independent subsystem streams. Both cost substantially more simulation runs.
Tracked in #543. Until then, treat the output as a diagnostic for exploring
model behavior, not as evidence about what drives cost.

Note also that small `--attribution-seeds` values make variance *ratios* very
unstable, compounding the anchor problem. The command discloses the extra
`3 × K` frozen runs before it starts. Headline seed runs are reused only when
both the seed and effective configuration fingerprint match; reuse and
fresh-baseline counts appear in the report.

Enrollment and merit are deliberately reported as **not stochastic**, not as
0% contributors. Enrollment's production hashes do not include the random
seed, and merit has no random draw. Making enrollment seed-variant would alter
existing outcomes and is intentionally a separate behavior change.

`--discard-seed-dbs` keeps the aggregate database but removes retained headline
seed databases after aggregation. It therefore forfeits reuse as evidence for a
later attribution request.

## Deliverables and validation

An ensemble workbook adds `Metric_Distributions` when aggregate bands exist.
Existing non-ensemble exports gain no empty sheet. Conditional variance results
are intentionally **not** exported — a spreadsheet cell strips the caveats the
number cannot be read without — and remain in `fct_variance_attribution`.

Use isolated databases for validation:

```bash
pytest -m fast tests/test_ensemble_aggregate.py tests/test_ensemble_planner.py \
  tests/test_ensemble_risk.py tests/test_ensemble_attribution.py
pytest -m integration tests/test_subsystem_seed_identity.py
pytest -m integration tests/test_ensemble_end_to_end.py
```
