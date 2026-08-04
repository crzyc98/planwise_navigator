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

## Variance share attribution (anchor-averaged, #543)

Add `--attribution` to measure, for each of termination, hiring, and promotion,
the share of outcome variance associated with that subsystem's draw.

```bash
planalign simulate 2025-2029 --seeds 25 --attribution --attribution-seeds 10 --attribution-anchors 5
```

For each subsystem, the runner repeats the frozen arm across `--attribution-anchors`
(default 5) independently pinned **anchor seeds**, each time pinning only that
subsystem's seed while the global seed continues to vary across the
`--attribution-seeds` (K) paired baseline seeds, and computes

`1 - Var(Y | subsystem seed = anchor) / Var(Y)`

at every anchor. The reported `variance_share` is the **mean across anchors**,
not one arbitrary anchor's value. By the law of total variance this
approximates the subsystem's first-order Sobol index — the share of outcome
variance associated with its draw, averaged the way the theory requires rather
than measured at a single point. `ci_low`/`ci_high` are a 95% paired-bootstrap
interval: each replicate resamples every anchor's paired (baseline, frozen)
seed values with replacement, recomputes the anchor-averaged share, and the
interval is the 2.5th/97.5th percentile of those replicates. The bootstrap RNG
is seeded deterministically from `(metric, simulation_year, subsystem)`, so
re-running against the same evidence reproduces the same interval.

This supersedes the single-anchor design shipped with Feature 133: pinning to
one arbitrary anchor (`seeds[0]`) could show a subsystem's *conditional*
variance exceeding its *marginal* variance — a measured run showed promotion's
variance 250% higher when pinned at one anchor — which is not an error but is
also not something a single point estimate can distinguish from real signal.
Averaging over several anchors is what makes the number stable enough to rank
and export.

**Still main-effect-only, not a full decomposition.** Pinning one subsystem's
seed also fixes the population later subsystems draw from (hiring changes who
is exposed to termination risk, for example), so interaction effects between
subsystems are not captured and shares across subsystems need not sum to 1.
Results are ranked within a metric/year by the point estimate, but "variance
share" should not be read as "percent of cost caused by."

Consequences:

- Results **are ranked** by `variance_share` and reach the Excel workbook (a
  `Variance_Attribution` sheet) and `fct_variance_attribution`, now that the
  estimate is anchor-averaged with a CI rather than a single-anchor value.
- Raw unpinned and pinned variances (averaged across anchors) are printed
  alongside every share so the magnitude stays inspectable.
- All anchor seeds used are disclosed in the CLI output and stored in
  `fct_variance_attribution.anchor_seeds`; `n_anchors` and
  `bootstrap_iterations` record how the interval was built.

### Cost

Each additional anchor multiplies attribution's frozen-run count by the
subsystem count: **3 subsystems × A anchors × K seeds**, on top of the N
headline runs. The CLI discloses the exact total before any worker starts.

| `--seeds` (N) | K (`--attribution-seeds`) | A (`--attribution-anchors`) | Attribution runs (3×A×K) | Total runs |
|---|---|---|---|---|
| 25 | 10 | 1 (old single-anchor equivalent) | 30 | 55 |
| 25 | 10 | 5 (default) | 150 | 175 |
| 25 | 10 | 10 | 300 | 325 |

Wall time scales with run count and available parallel workers
(`ScenarioRunPool`, sized from memory and CPU count). Per-run wall time is not
dominated by census size — dbt per-invocation overhead dominates at every
scale measured (`docs/perf/run_cost_profile.md`,
`docs/perf/run_cost_profile_production.md`, post-#478 invocation
consolidation):

- **~90–100s/run** for a 5-year horizon at a ~7.5k-employee (dev-scale) census.
- **~120s/run** for a 5-year horizon at a 60k-employee (client-scale) census.

Extrapolating (not a fresh empirical measurement of the full attribution job,
since 150+ real dbt runs is impractical to execute per-change): the default
5-anchor attribution pass above (150 frozen runs) is roughly **3.75–5 CPU-hours**
serial-equivalent at dev-to-client scale, or **~30–45 minutes wall time** with
8 parallel workers. A single `--attribution-anchors 1` run (30 frozen runs,
matching the pre-#543 cost) is proportionally ~5× cheaper. Choose
`--attribution-anchors` and `--attribution-seeds` with this multiplier in mind
before running against a large census.

Note also that small `--attribution-seeds` (K) values still make each anchor's
variance ratio unstable; K and A trade off independently against cost — more
anchors tighten the CI on the *mean*, more seeds tighten each anchor's own
estimate. Headline seed runs are reused as the baseline arm only when both the
seed and effective configuration fingerprint match; reuse and fresh-baseline
counts appear in the report.

Enrollment and merit are deliberately reported as **not stochastic**, not as
0% contributors. Enrollment's production hashes do not include the random
seed, and merit has no random draw. Making enrollment seed-variant would alter
existing outcomes and is intentionally a separate behavior change.

`--discard-seed-dbs` keeps the aggregate database but removes retained headline
seed databases after aggregation. It therefore forfeits reuse as evidence for a
later attribution request.

## Deliverables and validation

An ensemble workbook adds `Metric_Distributions` when aggregate bands exist,
and a `Variance_Attribution` sheet when `--attribution` ran. Existing
non-ensemble exports gain no empty sheet. Attribution evidence also remains
queryable directly in `fct_variance_attribution`.

Use isolated databases for validation:

```bash
pytest -m fast tests/test_ensemble_aggregate.py tests/test_ensemble_planner.py \
  tests/test_ensemble_risk.py tests/test_ensemble_attribution.py
pytest -m integration tests/test_subsystem_seed_identity.py
pytest -m integration tests/test_ensemble_end_to_end.py
```
