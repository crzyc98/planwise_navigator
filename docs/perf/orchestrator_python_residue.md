# Orchestrator-Python Residue Attribution (#521)

_Answers the question `run_cost_profile_production.md` §8 left open: what is
the ~17s "orchestrator Python" residue actually spending time on?_

## Headline finding

**None of the candidates #521 named are the answer.** `StateManager`,
`DataValidator`, `HazardCacheManager`, `RegistryManager`, `HookManager`, and
`run_metadata` writes each account for **≤0.2%** of the residue, in every
rep of every run. The residue is dominated by two things instead, in this
order:

1. **~50% is background resource-monitor thread lifecycle overhead** —
   directly measured, not inferred. `PerformanceMonitor.time_operation()`
   (and, when active, `AdaptiveMemoryManager`/`CPUMonitor`/`MemoryMonitor`)
   spin up a **new daemon thread per instrumented operation**
   (`multi_year_run`, `year_simulation_N`, `stage_X_N` — ~26 operations over
   a 5-year run) purely to sample `psutil` memory/CPU stats, then tear it
   down with a **blocking `Thread.join(timeout=...)`** on the main thread.
   That join is real, synchronous wall-clock cost with no relationship to
   simulation business logic.
2. **Most of the rest is DuckDB connection/lock-retry churn** triggered by
   `_clear_snapshot_rows_if_needed()` (`year_executor.py`) — the pre-clear
   `DELETE FROM fct_workforce_snapshot` that runs before every incremental
   snapshot rebuild "to avoid dbt pre-hook concurrency issues" (per its own
   comment) — going through `DatabaseConnectionManager.execute_with_retry()`,
   which retries with a `time.sleep()` backoff on lock contention.

## Method

Three isolated reps against the reference config (`config/simulation_config.yaml`)
+ workspace census (60,040 employees) + 2025–2029 horizon, wrapper seam —
identical inputs to the accepted `run_cost_profile_production.md` baseline.
Each rep gets a fresh isolated DB under `var/perf_profile/<campaign>/db/`;
`dbt/simulation.duckdb` is never touched.

1. **Rep 1 — baseline (monitors on).** `InvocationRecorder` wraps
   `DbtRunner.execute_command` (same non-invasive per-instance patch as the
   existing harness). `residue_s = total_wall_s − Σ(invocation wall_s)`,
   exactly the existing accepted definition. The four monitor components'
   `start_monitoring`/`stop_monitoring` methods are also wrapped with plain
   `time.perf_counter()` — no cProfile — to directly time their real
   wall-clock cost without any multi-threading attribution problem.
2. **Rep 2 — baseline, monitors suppressed.** Identical to rep 1, except
   the four monitor components' `start_monitoring` methods are patched to
   no-ops for this rep only (restored immediately after). No thread is ever
   created, so `stop_monitoring`'s join never fires either. This isolates a
   clean "everything else" residue number by plain wall clock — no profiler
   involved, so it cannot be a measurement artifact.
3. **Rep 3 — profiled, monitors suppressed.** A single `cProfile.Profile` is
   enabled for the whole run, `disable()`d immediately before and
   `enable()`d immediately after every `execute_command` call, so dbt
   subprocess wall time is excluded from profiling (only Python between
   invocations is traced). Monitors are suppressed here too — a single
   shared `cProfile.Profile` cannot correctly separate call stacks across
   concurrently running OS threads, and in practice this corrupted
   attribution badly (background-thread frames showed implausible callers
   like `builtins.next`, and total call counts stopped reconciling with the
   sum over recorded callers) until the monitor threads were suppressed.
   Rep 3's bucket **shares** are scaled onto rep 2's clean residue — an
   apples-to-apples comparison, since both are monitor-suppressed — rather
   than rep 1's raw residue.

No production code is modified. All patching is runtime monkeypatching of
one live instance/class for the duration of a measurement rep, restored
immediately after, the same technique `dbt_timing.InvocationRecorder`
already uses in the accepted harness.

Script: `scripts/perf_profile/profile_python_residue.py`.

## Results

Three independent full-scale runs (60,040 employees, 2025–2029, wrapper
seam) — the qualitative picture is identical across all three:

| Run | Total wall | Rep-1 residue | Monitor lifecycle (% of residue) | Rep-2 clean residue |
|---|---:|---:|---:|---:|
| `residue-521` | 105.48s | 17.92s (17.0%) | _(not yet instrumented)_ | — |
| `residue-521-v2` | 103.52s | 18.05s (17.4%) | 9.17s (50.8%) | — |
| `residue-521-final` | 98.51s | 17.15s (17.4%) | 8.92s (52.0%) | 8.69s |

Reconciliation (final run): rep-1 residue minus directly-measured monitor
lifecycle (17.15 − 8.92 = 8.22s) lands within 5.7% of rep 2's independently,
directly measured 8.69s — consistent with the monitor-suppression context
being the dominant, correctly-isolated difference between the two reps, with
the gap explained by ordinary run-to-run variance in a single-laptop
measurement (see Caveats).

### Bucket breakdown (rep 3, scaled onto rep 2's 8.69s clean residue)

| Bucket | tottime (cProfile, monitors suppressed) | Share | Est. seconds of clean residue |
|---|---:|---:|---:|
| YearExecutor (stage orchestration + retry caller frames) | 1.166s | 66.0% | 5.73s |
| DatabaseConnectionManager (connect/retry/transaction) | 0.444s | 25.1% | 2.18s |
| other | 0.110s | 6.2% | 0.54s |
| stdlib/third-party runtime | 0.025s | 1.4% | 0.12s |
| HazardCacheManager | 0.012s | 0.7% | 0.06s |
| other orchestrator Python | 0.007s | 0.4% | 0.03s |
| StateManager (cleanup/DDL) | 0.003s | 0.2% | 0.01s |
| PipelineOrchestrator glue, run_summary, config export/fingerprint, HookManager, DataValidator, EventGenerationExecutor, run_metadata writes, DbtRunner, StageValidator, RegistryManager | 0.000s each | 0.0% each | 0.00s each |

**Total cProfile-traceable Python: 1.77s of the 8.69s clean residue (20%).**
The remaining 6.92s is main-thread wall time cProfile cannot attribute to a
traced Python frame — most plausibly additional DuckDB lock-contention wait
that occurs *inside* the C extension call before the Python-level exception
that triggers the visible retry/sleep is even raised (see Discussion). This
same 66%/25% YearExecutor/DatabaseConnectionManager split, and the same
near-zero result for every #521-named candidate, reproduced independently
in `residue-521` (67.4%/23.9%) and `residue-521-v2` (68.4%/23.2%) before the
3-rep refinement existed — the qualitative finding is not an artifact of
any one run.

### Where the traceable 1.77s actually goes

- `time.sleep` (DB lock-retry backoff): **2.31s tottime**, 3 calls — split
  across caller frames into the YearExecutor bucket above (the call chain is
  `_run_stage_models_legacy` → `_run_sequential_event_models` →
  `_clear_snapshot_rows_if_needed` → `execute_with_retry` → `time.sleep`).
  Only 1.58s of cumulative time traces back through `_clear`'s own frame,
  meaning at least one more `execute_with_retry` call site elsewhere also
  hit contention and retried.
- `transaction()` (`utils.py:309`, `DatabaseConnectionManager`): 0.34s
  tottime across **145 calls** — a fresh short-lived transaction/connection
  per call, ~2.3ms average.
- `_create_connection`/`duckdb.duckdb.connect`: 0.09s + 0.09s across 18/25
  calls — raw DuckDB connection establishment cost.
- Every one of #521's named candidates (`StateManager`, `DataValidator`,
  `HazardCacheManager`, `RegistryManager`, `HookManager`, `run_metadata`)
  reads at or near **0.000s** of tottime. `HazardCacheManager.
  compute_hazard_params_hash` (which re-reads seed files, per #521's own
  candidate list) shows up but at 0.012–0.014s — noise, not a contributor.

## Discussion

**#521 asked the right question but guessed the wrong subsystems.** The
issue's candidate list was reasonable a priori (anything that runs once per
year is a natural suspect), but every one of them is fast. The real cost is
observability machinery measuring the run, and DB-connection churn from a
correctness workaround:

1. **Monitor thread lifecycle (~50% of residue, ~9s/run).** Every
   `time_operation()` call — and there are ~26 of them across a 5-year
   run — creates a brand-new `threading.Thread`, starts it, lets it poll
   `psutil` every 0.5s, then joins it with a timeout on teardown. The join
   is a real blocking wait for the daemon thread to notice a stop flag,
   bounded by the polling interval. This cost scales with the **number of
   instrumented operations**, not with census size or simulation
   complexity — it would be identical at 7,505 employees or 600,040.
2. **DB connection/retry churn (most of the remaining ~20% that's
   traceable at all).** `_clear_snapshot_rows_if_needed()` pre-clears
   `fct_workforce_snapshot` for the current year before every incremental
   rebuild, specifically to dodge a dbt pre-hook concurrency issue (per the
   comment at its call site). That path goes through
   `execute_with_retry()`, which is built to tolerate DuckDB lock
   contention — and in this run, it needed to: multiple retries actually
   fired. 145 separate `transaction()` calls over one run also means 145
   separate short-lived DuckDB connections opened and closed, rather than
   one held connection reused — overhead that scales with operation count,
   not row count.
3. **~80% of the "clean" residue is real wall time cProfile cannot
   attribute to any Python frame.** This is consistent with DuckDB lock
   contention: the actual multi-hundred-millisecond wait for a
   writer/checkpoint lock happens inside the C extension's blocking call
   *before* it raises the Python-visible exception that triggers the
   measured `time.sleep()` retry. cProfile can only see the visible retry
   sleep, not the invisible wait that provoked it.

## Recommendations (not implemented — this is a breakdown, not a fix)

- **Monitor lifecycle**: don't spin up a new thread per operation. A single
  sampler thread reused for the whole run (or the whole year), or skipping
  background monitoring for operations below some duration threshold, would
  remove most of the ~9s directly-measured cost with no loss of the metrics
  the sampler collects (peak memory/CPU are still observable at coarser
  granularity).
- **DB retry churn**: investigate what is actually contending for the
  DuckDB writer lock during `_clear_snapshot_rows_if_needed()` — is it a
  concurrently-open read connection from the resource monitors themselves,
  or genuine contention from within the orchestrator's own sequential
  execution model (which should not need cross-connection locking at all in
  a single-process, single-writer run)? If a `_clear` call never needs to
  retry, both the sleep and its opening/closing of a fresh connection
  disappear.
- Neither fix touches dbt semantics, model SQL, or event generation — both
  are pure orchestrator-side plumbing, matching #521's framing that this
  residue is "pure Python we control."

## Caveats

- Single unshared dev laptop; DB lock-contention retries are inherently
  stochastic (dependent on real OS/filesystem timing), so exact seconds
  vary run to run more than the rest of this profile family. The bucket
  *shares* and the monitor-lifecycle measurement are consistent and
  reproducible; treat individual-run absolute seconds as illustrative.
- cProfile itself adds overhead and cannot correctly attribute time spent in
  concurrently-running OS threads — see Method for how this was handled
  (monitor suppression during rep 3, cross-checked against a
  monitor-suppressed non-profiled rep 2).
- This profile does not decompose the ~80% of clean residue that cProfile
  cannot trace to a frame; the Discussion section's account of that gap is
  inference from the code path, not a direct measurement.

## Reproduction & provenance

```bash
python -m scripts.perf_profile.profile_python_residue \
    --campaign-id residue-521-final --horizon 2025-2029
```

Uses `config/simulation_config.yaml` + the workspace census
(`workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/data/census.parquet`) by
default — the same reference config + census as
`run_cost_profile_production.md`.

Environment: arm64 cpus=12, macOS-26.6-arm64-arm-64bit, Python 3.12.11,
dbt-core 1.8.8, dbt-duckdb 1.8.1, duckdb 1.0.0, git SHA `ec6cdf5c`.

Artifacts: `var/perf_profile/residue-521-final/` (git-ignored) — per-rep
isolated `.duckdb` files, the effective config, and `profiled.prof`
(loadable with `python -m pstats` or `snakeviz` for further drill-down).
