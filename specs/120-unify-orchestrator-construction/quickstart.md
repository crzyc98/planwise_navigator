# Quickstart: Validating Unified Orchestrator Construction

How to prove feature 120 works. All runs use **isolated** databases; the shared dev DB is never built into.

## Prerequisites

```bash
source .venv/bin/activate
python -c "import planalign_orchestrator"   # sqlparse .pth fix
CENSUS=workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/data/census.parquet   # 60,040 rows
```

## 1. Same config → identical results across entry points (US1 / SC-003)

Run one validated config via two entry points into isolated DBs, then compare authoritative outputs with an order-insensitive multiset check (only `created_at`/`snapshot_created_at` excluded):

```bash
# CLI path
DATABASE_PATH=/tmp/u120/cli.duckdb \
  planalign simulate 2025-2027 --config config/simulation_config.yaml --database /tmp/u120/cli.duckdb

# Batch path (same config as a single scenario), isolated scenario DB
planalign batch --scenarios u120_ref --clean     # writes u120_ref.duckdb

# Compare fct_yearly_events + fct_workforce_snapshot both directions (EXCEPT ALL) -> expect 0 diffs
```

Success: **0 differing rows** in either direction for both tables.

## 2. Construction signature is identical + observable (US2 / SC-002, FR-005)

```bash
# Every run records its start-time signature in run_metadata:
duckdb /tmp/u120/cli.duckdb \
  "SELECT entry_point, runner_kind, initialization_policy, \
          substr(construction_signature_hash,1,12) AS sig \
   FROM run_metadata ORDER BY run_timestamp DESC LIMIT 5"

# Completed runs append their finalized ordered schedule separately:
duckdb /tmp/u120/cli.duckdb \
  "SELECT run_id, invocation_count, schedule_steps \
   FROM run_execution_metadata ORDER BY recorded_at DESC LIMIT 5"

# The corrected #455 harness reports the SAME signature hash as the product for the same config:
python -m scripts.perf_profile.run_matrix --campaign-id u120 --construction wrapper \
  --config config/simulation_config.yaml --config-label reference \
  --census "$CENSUS" --horizon 2025-2027 --reps 1 --skip-cold
```

Success: `construction_signature_hash` matches across all six entry points for the same config; Studio records `entry_point='studio'`; the terminal record contains the full ordered schedule.

## 3. Fresh-DB init is fail-loud (US3 / SC-005, #467)

```bash
# Force a critical initialization failure against a fresh DB -> run MUST abort with a clear error,
# and NO fct_yearly_events rows are written. Under normal conditions a fresh DB completes and
# matches a pre-initialized run byte-for-byte.
```

Success: forced failure aborts with an attributable error and zero outputs; normal fresh-DB run == pre-initialized run.

## 4. Unsupported engine option is rejected, not ignored (US4 / SC-004)

```bash
# Add optimization.execution_engine: some_unsupported_value to a config and launch -> validation
# rejects it with a message naming the option; a supported/unset value behaves identically everywhere.
```

Success: unsupported value → clear validation error, no run; supported value → identical behavior across entry points.

## 5. Scale and memory regression (SC-009)

Generate the 100,000-employee census from the repository fixture/generator into a disposable directory, then run three repetitions of the multi-year production path with one thread while recording elapsed time and peak RSS. Success: every repetition completes without memory errors, and median elapsed time and peak RSS increase by no more than 10% from the three-repetition pre-change measurements.

## 6. Guardrails (SC-006)

```bash
# Shared dev DB unchanged across all validation:
shasum -a 256 dbt/simulation.duckdb    # identical before and after the steps above
```

## Fast checks during development

```bash
pytest -m "fast and orchestrator" -q      # unit
pytest -m integration -q -k construction  # cross-entry-point equivalence + signature + init contract
```

## Recorded validation (2026-07-20)

All six flows passed:

1. Product parity tests and isolated reference/Studio harness runs completed
   with unchanged shared-DB SHA-256.
2. Six entry points emitted one semantic signature; old-schema evolution and
   append-only terminal schedule persistence passed.
3. Forced CLI/batch initialization failures aborted with zero facts; fresh
   versus explicit pre-initialization matched with bidirectional `EXCEPT ALL`.
4. Unset/`dbt` engine values resolved identically; `compiled` was rejected
   before construction.
5. Three 100K/5-year repetitions produced medians of 137.70s and 1,552.22 MiB,
   below both +10% regression limits.
6. Every behavioral campaign verified SHA-256
   `46ef47d6c8b46142d2cb0863d19ba8ba19e2bd6c3fcab2e846cbaacc4bfa5683`
   before and after.
