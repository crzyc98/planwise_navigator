# Parallel scenario fan-out

Scenario runs are embarrassingly parallel. E069 already guarantees **one
`.duckdb` file per scenario**, so N scenarios share no state and can occupy N
cores. `planalign batch` fans them out across worker processes, and the pool it
uses (`ScenarioRunPool`) is the shared primitive the seed-ensemble runner
(Roadmap 6) and the optimizer (Roadmap 7) submit to.

Fan-out multiplies whatever per-run engine we have. It does not make an
individual run cheaper — see [`docs/perf/run_cost_profile_production.md`](../perf/run_cost_profile_production.md)
for where a single run's time actually goes.

## Using it from the CLI

```bash
# Default: concurrency sized from measured memory and CPU budgets
planalign batch --scenarios baseline,high_growth,cost_control

# Pin the worker count (e.g. on hardware we have not measured)
planalign batch --parallel 4

# Force the serial path — unchanged pre-#457 behavior
planalign batch --parallel 1
```

The resolved fan-out and its reasoning are printed in the batch summary:

```
⚡ Fan-out: 3 worker(s) — limited by available memory
   (cpu cap 11, memory cap 3 @ 1536 MiB/worker, 5849 MiB available)
```

## How the default worker count is chosen

Concurrency is `min(scenario_count, cpu_budget, memory_budget)`:

| Budget | Value | Why |
|---|---|---|
| `cpu_budget` | `cpu_count - 1` | Leaves a core for the parent, the OS, and the user. |
| `memory_budget` | `available_memory / 1536 MiB` | A run's measured peak RSS is **1296 MiB** (#455 baseline, 5-year horizon), plus ~18% headroom. |

**Memory, not CPU, is usually the binding constraint.** On a 16-core laptop with
6 GiB free you get 3 workers, not 15. Sizing on CPU count alone is how you swap:
N concurrent DuckDB instances at ~1.3 GiB each is the real limit. If a machine
reports too little memory for even one worker, the pool still runs one — it
degrades to serial rather than refusing to work.

An explicit `--parallel N` is honored as given (a warning is logged if it
exceeds the memory budget), because the measured figure comes from one census
size on one class of hardware.

If a worker is killed for memory use, its scenario is reported as failed with a
message pointing at `--parallel`, rather than silently vanishing from the
summary.

## Guarantees

**Determinism.** Every job is fully resolved *before* any worker starts —
config merge, scenario overrides, and seed resolution all happen in the parent.
A scenario therefore computes the same thing regardless of which worker picks
it up or in what order. Parallel and serial output are verified equal in
`tests/unit/orchestrator/test_run_pool.py` and by an end-to-end table-hash
comparison of `fct_yearly_events` / `fct_workforce_snapshot`.

**Process isolation.** Workers are processes, not threads: each drives its own
dbt subprocesses and DuckDB connections, so there is no GIL contention and no
shared-connection risk. The pool uses the `spawn` start method rather than
`fork`, because forking a parent that already holds DuckDB connections and
threads into a child that then runs dbt is exactly the shared-state hazard
process isolation is meant to remove.

**dbt artifact isolation.** dbt writes `target/` and `logs/` inside the project
dir, so concurrent workers sharing `dbt/` would overwrite each other's
`run_results.json` — and failure attribution reads that file. Each worker gets
its own artifacts directory under
`var/outputs/batch_<ts>/<scenario>/dbt_artifacts/`, wired via `DBT_TARGET_PATH`
and `DBT_LOG_PATH`. Serial batches keep writing to `dbt/target` so the usual
post-mortem workflow is unchanged for anyone not opting into fan-out.

One consequence: each worker parses the dbt project from scratch on its first
invocation, since it does not inherit the shared `partial_parse.msgpack`. That
is a few seconds per worker, once.

**Failure containment.** One scenario failing never stops the pool. It lands as
a failed entry in the batch summary alongside the successes, mirroring serial
behavior. A scenario that fails during *setup* (bad config) is reported the
same way and simply never becomes a job.

**Run metadata.** Config-drift stamping (Feature 109) happens inside
`execute_multi_year_simulation`, per scenario database, so it is unchanged by
fan-out — each scenario DB gets its own `run_metadata` row exactly as in a
serial run.

**Ctrl+C.** Each worker calls `setsid`, so the worker pid is also its session
and process-group id, and its dbt children inherit it. On interrupt the pool
signals each worker's whole process group — `SIGTERM`, then `SIGKILL` after a
10s grace period — so no dbt subprocess is orphaned. Workers ignore `SIGINT`
themselves so a terminal Ctrl+C cannot race the parent's orchestrated shutdown.

## Reusing the pool (Roadmap 6/7)

The API is deliberately tiny: build jobs, run them, collect results.

```python
from planalign_orchestrator import ScenarioJob, ScenarioRunPool, resolve_worker_count

def my_worker(job: ScenarioJob) -> dict:
    """Must be a module-level function — jobs cross the process boundary by pickle."""
    ...

jobs = [
    ScenarioJob(
        name=f"seed_{seed}",
        config=config_with_seed_pinned,   # fully resolved in the parent
        db_path=Path(f"var/ensemble/seed_{seed}.duckdb"),
        seed=seed,
        dbt_artifacts_dir=Path(f"var/ensemble/artifacts/seed_{seed}"),
    )
    for seed in seeds
]

budget = resolve_worker_count(None, len(jobs))
results = ScenarioRunPool(budget.workers).run(
    my_worker, jobs, on_event=lambda e: print(e.kind, e.job_name)
)

for name, result in results.items():
    if result.succeeded:
        consume(result.value)
```

Three rules for anything submitting to the pool:

1. **The worker must be a module-level function.** Workers receive it by
   pickled reference; a closure or bound method will not survive `spawn`.
2. **Resolve everything in the parent.** Anything left to the worker —
   especially seeds — makes results depend on scheduling.
3. **Give each job its own database and artifacts directory.** The pool does
   not enforce this; it is the invariant that makes the jobs independent.

Events are delivered on the calling thread as results arrive, so `on_event` can
drive a progress display without workers touching the terminal.

## Validating a change to fan-out

Per the isolated-database rule, never validate against `dbt/simulation.duckdb`.
Run the same scenarios both ways and compare the simulation output directly:

```bash
planalign batch --scenarios a,b --parallel 1 --clean   # reference
# hash fct_yearly_events / fct_workforce_snapshot per scenario DB
planalign batch --scenarios a,b --parallel 2 --clean   # fan-out
# hashes must match, and the two scenarios must differ from each other
```

**Exclude the build timestamps from the hash.** `fct_yearly_events.created_at`
and `fct_workforce_snapshot.snapshot_created_at` are wall-clock stamps written
at build time — they differ between *any* two runs, serial included, and are
not a determinism signal. Hashing whole rows makes an otherwise-identical run
look like a failure. Everything else is deterministic, event UUIDs included.

The cross-scenario check matters as much as the parallel-vs-serial one: if two
differently-configured scenarios produce identical output, they contaminated
each other rather than agreeing.

Last measured (2 scenarios, 2025–2026, this branch):

| | Wall | Result |
|---|---|---|
| `--parallel 1` | 106.9s | reference |
| `--parallel 2` | 56.3s (1.90×) | 70/70 semantic columns identical per scenario |

Slowest single scenario was 55.2s, so fan-out cost ~1.1s of overhead.
