# Quickstart: Validate Compiled DAG Execution

This is the post-implementation validation path for #470. Run the gates in order and stop at the first failure. Every behavioral command must use a fresh isolated database; never validate against `dbt/simulation.duckdb`.

## Prerequisites

```bash
source .venv/bin/activate
planalign health
git status --short
```

Confirm the development and 60K census inputs are available:

```bash
duckdb -c "SELECT COUNT(*) FROM read_parquet('data/census_preprocessed.parquet')"
duckdb -c "SELECT COUNT(*) FROM read_parquet('var/perf_profile/census_large.parquet')"
```

Expected current sizes are 7,505 and 60,040. Generate the large artifact first with the existing census generator if it is absent.

## Red regression suite

Before implementation, add the six #470 regressions and confirm each fails for its intended reason:

```bash
pytest -q \
  tests/unit/engine/test_preflight.py \
  tests/unit/engine/test_transaction.py \
  tests/unit/engine/test_compiled_runner.py \
  tests/unit/engine/test_workspace.py \
  tests/invariants/test_comparison.py
```

Coverage must prove:

- log-only project hooks do not force delegation;
- unsupported selectors do not become zero-node success;
- in-process dbt uses the explicit isolated database even when ambient state points elsewhere;
- partial writes roll back before typed late delegation;
- delegated build/fallback operations cannot mutate a published bundle;
- equal-total-count duplicate multiplicity changes fail parity.

After implementation, rerun the same command green, then broaden:

```bash
pytest -m "fast and orchestrator" -q
```

## Gate 1 — Tiny isolated exact parity

```bash
planalign parity 2025-2027 \
  --config tests/fixtures/invariant_config.yaml \
  --census tests/fixtures/invariant_census.csv \
  --seed 42 \
  --json
```

Expected: `IDENTICAL`, equal schemas, zero `EXCEPT ALL` differences, zero unexpected fallback, and unchanged shared-development database hash.

## Gate 2 — Multi-year determinism and rerun parity

```bash
pytest -v \
  tests/integration/test_multi_year_invariants.py \
  tests/integration/test_determinism.py
```

Expected: 2025–2027 invariants pass for both engines; fresh identical-input runs and idempotent reruns match exactly.

## Gate 3 — Development and 60K exact parity

```bash
planalign parity 2025-2027 \
  --census data/census_preprocessed.parquet \
  --seed 42 \
  --json

planalign parity 2025-2027 \
  --census var/perf_profile/census_large.parquet \
  --seed 42 \
  --json
```

Expected: both reports are `IDENTICAL` with zero unexpected fallback. Preserve the JSON reports as gate evidence.

## Gate 4 — Actual 100K memory and completion

Generate and verify an input above 100,000 rows:

```bash
python -m scripts.perf_profile.make_large_census \
  --factor 14 \
  --out var/perf_profile/census_100k.parquet

duckdb -c "SELECT COUNT(*) FROM read_parquet('var/perf_profile/census_100k.parquet')"
```

Expected row count from the current 7,505-row source is 105,070. Run one 2025–2027 compiled campaign through the memory-enabled harness against a fresh database. Pass requires completion, authoritative outputs, recorded peak process-tree RSS, no memory/OOM error, and an unchanged shared database.

## Gate 5 — Paired end-to-end performance

```bash
python -m scripts.perf_profile.run_matrix \
  --campaign-id feature119-final \
  --engines dbt,compiled \
  --sizes tiny,dev,large \
  --reps 3 \
  --horizon 2025-2027

python -m scripts.perf_profile.build_report \
  --campaign-id feature119-final \
  --out var/perf_profile/feature119-final/report.md
```

Use paired fresh databases and alternate engine order by repetition. Total wall time includes workspace creation, parsing, compilation, preflight, direct execution, and delegation. Pass requires at least 1.8× median speedup on the approved 60K benchmark; 2.0× remains the target. Report tiny and development results as well.

## Gate 6 — Zero unexpected fallbacks

Aggregate terminal and invocation evidence from gates 1–5. Expected:

```text
unexpected_fallback_count = 0
```

Known unsupported regression cases are expected delegations and are evaluated separately. Any late typed delegation or legacy catch-all replay fails this gate.

## Default flip — only after gates 1–6 pass

After preserving all gate artifacts:

1. Change the Pydantic default from `dbt` to `compiled`.
2. Rerun Gate 1 without an explicit engine override.
3. Run one isolated `--engine dbt` compatibility smoke.
4. Confirm run summaries and terminal evidence name the actual engine.
5. Close #470 only after review of all evidence.

Then start #471. Keep #472–#475 blocked until #471 demonstrates a convincing native-kernel speedup and receives GO.
