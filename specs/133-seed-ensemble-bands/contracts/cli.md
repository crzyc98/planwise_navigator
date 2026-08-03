# Contract: CLI Surface

**Feature**: 133-seed-ensemble-bands

The user-facing interface. This is the contract that must stay stable; internal module boundaries may move freely.

---

## `planalign simulate <year-range> --seeds N`

| Option | Type | Default | Meaning |
|---|---|---|---|
| `--seeds` | int | none (single run) | Ensemble size N. Absent ⇒ today's single-run behavior, unchanged. |
| `--seed-list` | csv ints | derived | Explicit seeds. Mutually exclusive with `--seeds`. Duplicates are rejected. |
| `--attribution` | flag | off | Run OFAT variance attribution (FR-017). |
| `--attribution-seeds` | int | min(N, configured) | K, must be ≤ N and a subset of the headline list (FR-019a). |
| `--min-seeds` | int | 10 | Below this, percentiles are withheld (FR-013). |
| `--discard-seed-dbs` | flag | off | Delete per-seed databases after aggregation (FR-028). |
| `--threshold` | `metric:value` | none | Repeatable. Exceedance thresholds (FR-014). |

**Compatibility**: every existing invocation without `--seeds` behaves exactly as it does today. `--seeds` is purely additive.

**Implementation note**: `simulate.py` declares its options twice — on the `run` subcommand and on the hidden `default` command backing `planalign simulate 2025-2029`. Both must carry these options or the documented bare form silently ignores them.

### Pre-execution disclosure (FR-021, FR-006)

Before any worker starts, the command prints the resolved plan and does not proceed until it has:

```
Ensemble: 25 seeds × 5 years (2025-2029)
  Seeds:        [derived from base seed 42] 42, 1043, 2044, ...
  Worker budget: 4 worker(s) — memory-bound (cpu cap 7, memory cap 4 @ 1296 MiB/worker, 6144 MiB available)
  Runs:          25 simulation runs
  Est. disk:     ~8.2 GiB across 25 databases + 1 ensemble database
  Output:        var/ensembles/20260803T141522Z-baseline/
```

With `--attribution`, the run count line becomes explicit about the multiplier:

```
  Runs:          25 headline + 30 attribution (3 subsystems × 10 seeds) = 55 total
                 baseline runs reused from headline: 10 of 10
```

### Completion output

Distribution table (FR-024), one block per metric, seed count always present (FR-026):

```
Total employer plan cost — n=25 seeds, linear percentiles
  Year     P10        P25        P50        P75        P90
  2025   $1.92M     $1.96M     $2.01M     $2.05M     $2.09M
  ...
```

Insufficient samples never render as a band (FR-013a):

```
Participation rate — INSUFFICIENT SAMPLE (n=4, minimum 10)
  Percentiles withheld. Per-seed values written to fct_metric_seed_values.
```

Risk statements (FR-015), and a not-evaluable line rather than silence (FR-016):

```
Risk — thresholds
  P(total employer plan cost > $2.40M) : 2027  0% (0/25)   2028 12% (3/25)
  P(match cost > $900K)                : not evaluable — metric absent from these runs
```

Attribution (FR-019c, FR-020), with structural absences distinguished from measured zeros:

```
What drives the spread — total employer plan cost, 2029  (n=10 seeds/subsystem)
  1. termination    61% variance reduction when frozen
  2. hiring         22%
  3. promotion       9%
     enrollment     not stochastic — draws do not vary with seed
     merit          not stochastic — no random draws
  Method: one factor at a time; shares need not sum to 100%.
  Baselines: 10 reused from headline ensemble, 0 executed.
```

### Exit codes

| Code | Condition |
|---|---|
| 0 | Ensemble completed; aggregate written (bands may be withheld — that is success with a warning) |
| 1 | Configuration invalid (duplicate seeds, `--attribution-seeds` > N, malformed threshold) |
| 2 | One or more seed runs failed; failures reported with reasons |
| 3 | No successful seed runs; no aggregate written |
| 130 | Interrupted; workers terminated, no aggregate written (SC-010) |

Note that a below-minimum sample exits **0**, not an error: withholding percentiles is defined success, and the per-seed values are still delivered.

---

## `planalign batch --seeds N`

Same option names and semantics (FR-001), applied per scenario. Each scenario gets its own ensemble directory and aggregate; scenario-level isolation is unchanged.

---

## Workbook export

Added only when an ensemble aggregate exists (FR-025):

- **`Metric_Distributions`** — one row per (metric, year), percentile columns, `n_seeds`, `is_sufficient`. Withheld percentiles are empty cells, never `0`.
- **`Variance_Attribution`** — subsystem, metric, year, share, seed count, `stochastic_status`, reuse counts.

Existing sheets are unchanged, and no empty sheet is added when ensembles were not used.

---

## Library surface

Exported from `planalign_ensemble`:

```python
plan_ensemble(spec: EnsembleSpec) -> SeedPlan
run_ensemble(plan: SeedPlan, *, parallel: int | None = None) -> EnsembleResult
aggregate_ensemble(outcomes, *, min_seeds: int) -> list[MetricDistribution]
evaluate_thresholds(distributions, seed_values, thresholds) -> list[RiskStatement]
attribute_variance(plan, headline_outcomes, *, subsystems) -> list[AttributionShare]
```

`run_ensemble`'s worker must remain a module-level function — jobs cross the process boundary by pickle (`ScenarioRunPool` constraint).
