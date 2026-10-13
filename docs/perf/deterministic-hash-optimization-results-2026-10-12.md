# Deterministic hash optimization: execution evidence

Execution of the [implementation plan](deterministic-hash-optimization-plan.md).
Primary workload: ordinary CLI simulation, 60,040 census rows, 2025–2029, seed 42,
and the frozen effective default configuration with 3% growth.

**The optimization passes the performance, exact-parity, and repeatability gates.**
Median ordinary CLI latency fell from **173.89s to 108.58s**, saving **65.31s / 37.6%**.
The diff is ready for review, with the pre-existing fast-suite limitation below.
Keep the native-kernel program paused; assess further work against the remaining
ordinary-run costs and an explicit latency objective.

## Implementation

`pa_hash_mix`, `pa_hash_finalize`, and `pa_hash_hex` now bind intermediate values
through single-element list transforms. The helpers preserve the frozen UTF-8
MurmurHash64A contract, byte order, unsigned arithmetic, tail handling, input cast,
and NULL constant. Existing helper names and attribution remain intact.

The profiler resolves the actual project/target, including command overrides and
explicit artifact directories. Each invocation labels node evidence as fresh,
missing, stale, or malformed, retaining independent wall time on failures. Fresh
failed-node results are retained; previous successful results are never reused.

`scripts/perf_profile/hash_ab.py` invokes the actual Typer command, requires the
two dbt projects to differ only in the hash macro, rejects existing output paths,
creates a fresh project/database per sample, and runs strict mart comparisons.

## Environment and provenance

- Base revision: `d594e084d57056272a90f2b10d515c86a9d797d7`; measurements used the
  implementation diff over that revision, with the candidate macro fingerprint
  retained in the campaign artifacts.
- Python 3.12.11, Apple arm64, 12 logical CPUs; DuckDB 1.5.6, dbt-core 1.9.11,
  dbt-duckdb 1.9.6, Pydantic 2.13.5.
- The existing `.venv` contains DuckDB 1.1.3. All acceptance runs use the already
  cached pinned 1.5.6 build through an inherited process-local `PYTHONPATH` overlay.
  Parent and child Python imports were verified; no dependency installation or
  shared-environment modification was performed.
- dbt uses one thread. Product parsing behavior is preserved for timed runs;
  integration checks separately used `DBT_PARTIAL_PARSE=false`.
- Timing covers in-process actual Typer `simulate`, health checks, validation,
  and child processes. It excludes launching the outer interpreter and the Studio
  HTTP/UI lifecycle. Warmups precede three scored pairs in A/B, B/A, A/B order.
  All runs use fresh databases and initially clean dbt artifact directories.
- Config, census, seed-tree, and both project fingerprints plus raw measurements
  are retained under ignored `var/perf_profile/hash_optimization_20261012/`.
  Census contents and employee-level results are not included in this report.

## Validation completed before the campaign

| Check | Result |
|---|---|
| Expanded hash, profiler, and driver tests | 45 passed |
| Multi-year invariants and seven edge configurations | 30 passed, no skips |
| Fast suite | 3,037 passed; one existing worktree-scan failure |
| Repository-wide mypy | Passed across 135 source files |
| Ruff over profiling code and affected tests | Passed |
| Whitespace check | Passed |

The fast-suite failure is
`test_pipeline_orchestrator_is_instantiated_only_by_canonical_builder` in
`tests/unit/construction/test_no_direct_construction.py`. The unchanged test scans
the existing `.worktrees/` directory and reports eight builders in those repository
copies. All violations are under pre-existing `.worktrees/`; there are no violations
in the implementation's production source. Those worktrees and the unrelated test
remain untouched. The fast suite is therefore not completely green in this
checkout, even though the targeted and integration gates pass.

Tests cover golden values, randomized Unicode, embedded NUL, byte/block boundaries,
long strings, a nullable vectorized column, supported non-string casts, joins,
nested lambdas, repeated installation, artifact overrides, stale/malformed/missing
results, failed invocations, and capture/restoration of reused CLI runners.

During PR validation, the existing graph-contract manifest helper reproduced a
parallel-worker race: each process used an isolated database but wrote the same
project-level manifest. The test helper now gives each parse its own temporary
target/log paths and reads its manifest before cleanup. All 33 focused graph and
artifact-isolation tests passed with four xdist workers after this test-only fix.
The production macro and measured candidate remain unchanged.

## Hash diagnostic

For 60,040 synthetic strings shaped as `EMP_` + eight-digit ID +
`|2025|TERMINATION|42`, both implementations exactly match the independent Python
reference for every output. Single-thread DuckDB, one warmup and three measured
repetitions per implementation:

| Implementation | Median seconds |
|---|---:|
| Baseline SQL | 2.9383 |
| Optimized SQL | 0.4586 |

This is a 6.41× hash-query speedup, a diagnostic rather than a full-run release
claim. Raw samples and matching output digests are in `microbenchmark.json`.

## Full-run performance and parity

All eight runs completed with validation failures treated as errors. No successful
sample was dropped. Warmups were excluded according to the predefined protocol.

| Sample | Wall seconds | CPU seconds | Sampled process-tree peak RSS MiB | dbt calls |
|---|---:|---:|---:|---:|
| Baseline warmup, unscored | 170.20 | 263.58 | 1626.12 | 19 |
| Candidate warmup, unscored | 135.83 | 159.96 | 1098.14 | 19 |
| Pair 1 baseline | 170.88 | 276.41 | 2092.89 | 19 |
| Pair 1 candidate | 107.56 | 141.01 | 1107.42 | 19 |
| Pair 2 candidate, executed first | 108.58 | 141.55 | 1112.08 | 19 |
| Pair 2 baseline | 173.89 | 273.80 | 2075.06 | 19 |
| Pair 3 baseline | 174.89 | 285.09 | 1783.19 | 19 |
| Pair 3 candidate | 111.54 | 144.82 | 1135.66 | 19 |
| **Baseline scored median** | **173.89** | **276.41** | **2075.06** | **19** |
| **Candidate scored median** | **108.58** | **141.55** | **1112.08** | **19** |

Scored ranges were 170.88–174.89s baseline and 107.56–111.54s candidate. CPU median
fell 48.8% and sampled peak RSS median fell 46.4%. These are observations on this
workstation/configuration, not universal latency or memory guarantees. The candidate
warmup was slower than its scored repetitions; both warmups remain visible above.

All 152 dbt invocations across warmups and scored runs had fresh node artifacts.
The scored invocation counts and executed-node sets were identical across arms.
The 20% median-wall-time gate passed at 37.6% without changing its threshold.

Each of the other five scored outputs was compared against the first scored
baseline. Strict schema, row counts, duplicate counts, and bidirectional
`EXCEPT ALL` comparisons passed:

| Public mart | Rows per run | Differences in either direction |
|---|---:|---:|
| `fct_yearly_events` | 751,862 | 0 |
| `fct_workforce_snapshot` | 351,243 | 0 |
| `fct_employer_match_events` | 267,478 | 0 |

All five snapshot years are retained. Transitive comparison to the same baseline
also establishes deterministic repeatability across the three fresh candidate
databases. Only the existing manifest's named runtime timestamp columns were
excluded: `fct_yearly_events.created_at`, `fct_workforce_snapshot.snapshot_created_at`,
and `fct_employer_match_events.created_at`. No numerical tolerances or new
exclusions were introduced. `dim_hazard_table` and `fct_compensation_growth` were
unbuilt in both arms; their absence is not claimed as validated output coverage.

The shared `dbt/simulation.duckdb` fingerprint is unchanged from before regression
validation through the completed campaign. The production macro matches the frozen
candidate project used for measurement.

## Remaining ordinary-run costs

| Timing component, scored median seconds | Baseline | Candidate |
|---|---:|---:|
| dbt invocation wall time | 165.15 | 99.66 |
| Node execute phases | 94.93 | 32.65 |
| Outside dbt invocations | 8.74 | 8.67 |

Medians are calculated independently. About 67s of the candidate's dbt wall time
lies outside recorded node execute phases. This includes parsing, compilation,
hooks, startup, and adapter work; it is not a measured removable startup budget.
The optimization reduces existing work without reducing invocation or model counts.

The largest remaining per-model execute totals (median across the five-year run)
are termination 2.91s, new-hire termination 2.60s, promotion 2.46s, yearly events
2.29s, deferral state accumulation 1.83s, and employer-match events 1.78s. Node
execution includes materialization/adapter work and is not a pure hash timer.

The next decision should set a desired ordinary-run latency and separate the
remaining dbt costs with controlled measurements. A native rewrite would require
its own benefit/cost and parity case; this result does not authorize that program.
No 100K-population, ensemble-throughput, or Studio HTTP/UI acceptance benchmark
was performed for this focused optimization.

## Reproduce

Activate the environment and use the current pinned DuckDB build. On the measured
workstation the existing cached build was selected with:

```bash
source .venv/bin/activate
export PYTHONPATH=/Users/nicholasamaral/.cache/uv/archive-v0/RHpthCeOXh7fvwvFKILmu:$PWD
python -m scripts.perf_profile.hash_ab \
  --config config/simulation_config.yaml \
  --census workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/data/census.parquet \
  --baseline-project var/perf_profile/hash_optimization_20261012/baseline_project \
  --candidate-project var/perf_profile/hash_optimization_20261012/candidate_project \
  --output var/perf_profile/hash_optimization_20261012/campaign \
  --horizon 2025-2029 --seed 42 --pairs 3
```

Use a new output path for a rerun. The two frozen project copies were made from
the same checkout, excluding `target`, `logs`, database files, and `.user.yml`,
before and after the macro edit. If local artifacts have been removed, create two
fresh copies of the same dbt project and restore only the baseline copy's
`macros/utils/stable_hash.sql` from the base revision. Do not reuse historical
timings or substitute another census when claiming matched performance.

The cache path is workstation-specific; on another machine verify the configured
environment matches repository pins. Raw artifacts are disposable, so retain the
aggregate evidence in this report. Behavioral checks always use isolated databases.

Regression commands used the same pinned-runtime overlay:

```bash
python -m pytest tests/unit/test_stable_duckdb_semantics.py \
  tests/unit/test_state_pipeline_profile.py tests/unit/test_hash_ab.py -q
DBT_PARTIAL_PARSE=false python -m pytest \
  tests/integration/test_multi_year_invariants.py \
  tests/integration/test_edge_config_matrix.py -q
python -m pytest -m fast -q
ruff check scripts/perf_profile tests/unit/test_stable_duckdb_semantics.py \
  tests/unit/test_state_pipeline_profile.py tests/unit/test_hash_ab.py
mypy planalign_orchestrator/ planalign_cli/ planalign_core/ --ignore-missing-imports
git diff --check
```
