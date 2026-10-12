# Native-kernel decision: single-scenario latency

Follow-up: [implementation and validation plan](deterministic-hash-optimization-plan.md)
for a later GPT-6.1-Sol execution session.

Execution completed: [implementation evidence and repeated A/B results](deterministic-hash-optimization-results-2026-10-12.md).

## Recommendation

**Keep the native-kernel program (#469, #471–#475) paused. Prioritize a focused
optimization of the existing deterministic hash implementation, then remeasure
ordinary single-scenario latency.** This is an investigation recommendation, not
an implementation GO or a change to the GitHub issues.

The user's primary objective is faster ordinary single-scenario runs. The
original native-kernel justification emphasized hundreds of optimizer/ensemble
candidates. The current investigation found an immediate improvement within the
existing SQL engine: a prototype that avoids repeated evaluation inside the frozen
hash macros reduced one representative CLI run from **172.21s to 109.99s**,
with exact output parity. That is **62.21s / 36.1% less wall time**, without
porting the simulation's business rules to another engine.

The full-run A/B is one exploratory pair, not a median-of-three release benchmark.
It is sufficient evidence to prioritize the narrower work; it is not a promise
that every configuration or machine will improve by 36%.

## Current workload and environment

- Source revision: `d594e084d57056272a90f2b10d515c86a9d797d7`; local HEAD,
  `origin/main`, and GitHub main agreed at investigation start.
- Current `config/simulation_config.yaml`, with the existing 60,040-row workspace
  census substituted, years 2025–2029, seed 42, and 3% target growth. Match, core,
  enrollment, and escalation use the current configuration.
- Python 3.12.11, dbt-core 1.9.11, dbt-duckdb 1.9.6, DuckDB 1.5.6,
  Pydantic 2.13.5; 12 logical CPUs, Apple arm64 workstation.
- The checkout's `.venv` contains DuckDB 1.1.3. The benchmark used the already
  cached 1.5.6 package via a process-local `PYTHONPATH` overlay, inherited by dbt
  subprocesses. No packages were installed and the shared environment was not
  changed. This was not a newly synchronized lockfile environment.
- Every run used a fresh isolated database, `--threads 1`, and separate dbt
  artifacts. Both CLI A/B runs used copied dbt projects with identical seeds and
  source apart from the experimental hash macro. Default product parsing behavior
  was retained; there was no reuse of simulation state between runs.
- Shared `dbt/simulation.duckdb` SHA-256 was unchanged after each campaign.
  Census/config/seed fingerprints and detailed artifacts are recorded under
  `var/perf_profile/native_gate_20261012/` (ignored, local runtime evidence).

These are current-workload timings. Older 100–120s reports used different code,
dependencies, configurations, and initialization paths. They are historical
context, not a matched baseline for claiming a regression.

## Measurements

### Existing optimizer/ensemble worker

The first campaign used the real `planalign_ensemble.runner.run_seed_worker`, also
called by the optimizer. One initial run was excluded from the warm median; each
repeat still used a fresh database and fresh dbt artifacts. “Warm” refers to the
process/OS environment, not cached simulation results or prepared employee state.

| Run | Wall seconds | CPU seconds | Process-tree peak RSS MiB |
|---|---:|---:|---:|
| Initial | 185.11 | 285.38 | 1522.84 |
| Warm 1 | 183.80 | 281.06 | 1624.56 |
| Warm 2 | 185.82 | 287.63 | 1731.78 |
| Warm 3 | 189.27 | 299.05 | 1633.14 |
| Warm median | **185.82** | **287.63** | **1633.14** |

All four runs completed, produced 751,862 events, and retained all five snapshot
years. The worker made 22 dbt calls and executed 60 distinct models. Its
self-healing initialization accounts for three calls absent from the ordinary CLI.

Warm medians were 177.10s inside dbt invocations, 95.58s in the recorded dbt node
execute phases, and 8.68s outside dbt. Medians are calculated independently. Node
execute time includes dbt materialization/adapter work; the remaining invocation
time includes parsing, compilation, startup, and other adapter work. It is **not**
all removable subprocess overhead. Historical invocation-consolidation experiments
also warn against treating this subtraction as a recoverable performance budget.

The largest initial-run node totals were termination (17.72s), new-hire termination
(14.46s), promotion (14.32s), proactive voluntary enrollment (8.43s), and voluntary
enrollment decisions (8.07s). These helped identify the hash implementation as a
candidate for a controlled experiment; they do not attribute all of those models'
time to hashing.

### Ordinary CLI: controlled exploratory comparison

Both runs invoked the actual Typer `simulate` command in-process, including its
health checks and progress path, with fresh output databases and isolated dbt
projects. Timing includes the command and its child processes, not launching the
outer Python interpreter or the Studio HTTP/UI lifecycle.

| Case | Wall seconds | CPU seconds | Peak RSS MiB | dbt calls | Events |
|---|---:|---:|---:|---:|---:|
| Current main | **172.21** | 281.27 | 2014.83 | 19 | 751,862 |
| SQL hash prototype | **109.99** | 140.21 | 952.94 | 19 | 751,862 |

The invocation count stayed unchanged. This experiment reduced the cost of work
inside the existing pipeline rather than relying on fewer stages or less output.
The timing/RSS differences are single-pair observations and need repeat A/B
measurement before being adopted as release claims.

Instrumentation limitation: the first CLI captures read per-node timings from the
default project's target directory instead of the isolated project's target. Those
per-node values are invalid and excluded from this report; the independently timed
command wall/CPU/RSS and invocation counts remain valid. The local harness now
resolves that target correctly. The worker decomposition above used its explicit
artifact directories and is unaffected.

### Hash diagnostic

Three measured repetitions after a warmup, on 60,040 synthetic event-key strings,
with an in-memory DuckDB connection and one execution thread:

| Implementation | Median seconds | Output identity |
|---|---:|---|
| Current frozen SQL hash | 2.7896 | Reference output |
| SQL prototype reusing intermediate values | 0.4374 | Identical to current SQL |
| Independent scalar Python reference | 0.0877 | Identical to current SQL |

The SQL prototype was approximately **6.38× faster on this primitive**. It retains
the existing MurmurHash64A/UTF-8 semantics and uses single-element lambda bindings
to avoid duplicating expensive intermediate calculations when macros expand.
The Python function is a diagnostic, not an integrated product implementation.

DuckDB 1.5.6's built-in `HASH` was much faster but returned different hashes.
It is not a valid substitute: changing those hashes changes seeded employee
decisions and event identities.

## Correctness evidence and limits

- The prototype matched the current hash on all 60,040 synthetic keys and 302
  explicit cases covering null, empty strings, byte-block boundaries, and Unicode.
- The existing 75-example `test_hash_matches_reference_for_utf8` property was
  executed against a connection containing the prototype and passed.
- The current-main stable-semantics test file passed all 18 tests separately.
  That run tested current main; it is not claimed as the prototype's full suite.
- Both ordinary CLI runs completed with validation failures configured to fail
  the run.
- The parity comparison enumerated mart models from the baseline manifest, checked
  schemas, and used bidirectional `EXCEPT ALL` to retain duplicate multiplicity.

| Mart | Rows | Baseline minus prototype | Prototype minus baseline |
|---|---:|---:|---:|
| `fct_yearly_events` | 751,862 | 0 | 0 |
| `fct_workforce_snapshot` | 351,243 | 0 | 0 |
| `fct_employer_match_events` | 267,478 | 0 | 0 |

Only `created_at` on the event facts and `snapshot_created_at` on the snapshot were
excluded, using the existing Feature 122 exclusion manifest. Event identities,
behavioral dates, contribution amounts, schemas, and duplicate rows were compared.
`dim_hazard_table` and `fct_compensation_growth` were absent in both ordinary runs
and are not counted as validated outputs. This was not an all-intermediate-relation
comparison, a 100K scale gate, or the full edge-configuration matrix.

## Recommended next work and native-kernel gate

1. **Productionize the hash optimization as a focused performance change.** Review
   the macro simplification, retain the independent reference and Unicode/null
   coverage, repeat full-scale A/B timings, and run the applicable isolated
   multi-year and edge-configuration parity gates. Preserve frozen hash semantics.
2. **Profile the remaining single-run cost after that change.** Use the corrected
   artifact locator and real CLI/Studio construction. Check measured startup,
   parsing, and initialization costs; avoid reopening high-risk invocation
   regrouping solely from a subtraction of node time from wall time. The old
   monitor-lifecycle issue and pipeline-redesign work have already shipped.
3. **Revisit #471 against an explicit ordinary-run latency target.** For example,
   if the desired experience is a 60K/five-year run within 30 seconds, the observed
   ~110s prototype still leaves a material gap. That would justify a bounded
   architecture comparison if narrower changes cannot meet it economically.
   Thirty seconds is a proposed decision target, not a user-approved requirement.

If a native spike is reopened, replace its stale compiled-engine thresholds with
absolute single-run latency, measured against the optimized current SQL path.
Require a representative multi-year slice, an honest end-to-end projection including
inputs/output persistence, exact seeded/date/decimal/event parity, memory evidence
at 60K and 100K+, and a credible path to one authoritative rule implementation.
Keep #472–#475 gated until those results support migration. A fast termination-only
microbenchmark would not justify rewriting the entire simulation.

The existing evidence supports a smaller, broadly useful next step. It does not
establish that a native kernel is unnecessary forever or predict its eventual speed.

## Local reproduction and artifacts

The investigation harness, raw measurements, effective configurations, copied dbt
projects, databases, and parity result are retained in
`var/perf_profile/native_gate_20261012/`. They are runtime artifacts, not production
changes. `measure.py` refuses to overwrite an existing benchmark database; use a
fresh campaign directory when repeating it.

With that directory copied to a new sibling under `var/perf_profile/` (copy the
three Python scripts only), activate `.venv` and supply a Python environment with
the versions above. For the existing cached-package overlay, the invocation used
the DuckDB cache directory plus the repository root on `PYTHONPATH`:

```bash
source .venv/bin/activate
python var/perf_profile/<new_campaign>/measure.py serial
python var/perf_profile/<new_campaign>/hash_probe.py var/perf_profile/<new_campaign>/hash_156.json
python var/perf_profile/<new_campaign>/measure.py cli
python var/perf_profile/<new_campaign>/measure.py cli_hash_probe
python var/perf_profile/<new_campaign>/verify.py
```

`serial_environment.json` records the exact overlay path used in this campaign.
Confirm the runtime DuckDB version before repeating; merely activating this
checkout's current `.venv` selects 1.1.3. The scripts contain the local census path;
use the same fingerprinted source for comparable results.

Relevant prior decisions: [native epic #469](https://github.com/crzyc98/planwise_navigator/issues/469),
[feasibility gate #471](https://github.com/crzyc98/planwise_navigator/issues/471),
[state pipeline redesign](state-pipeline-redesign.md),
[invocation-consolidation decision](../../specs/132-collapse-dbt-invocations/evidence/decision-log.md),
and [frozen DuckDB semantics](../guides/duckdb_upgrade.md).
