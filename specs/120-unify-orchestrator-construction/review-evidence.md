# Review and constitution evidence

## Completed gates

- All behavioral simulations used explicit isolated DuckDB paths.
- The deterministic 100K/5-year/one-thread regression completed three times
  without memory failure and improved both median wall time and peak RSS.
- Targeted construction, provenance, initialization, entry-point, and engine
  suites pass.
- Ruff passes for all changed Python modules and tests.
- Construction-package audit found no TODO/FIXME/placeholder implementation.
- New direct DuckDB access in tests and generators uses context managers; product
  construction receives explicit run databases through `ConstructionSpec` and
  never falls back to the shared development database during validation.

## Existing fast-suite budget exception

The constitution says `pytest -m fast` must finish in under 10 seconds. This
repository currently selects 1,700 tests for that marker. The first serial run
took 129.00 seconds; after repairing its schema-contract expectation, the final
serial run passed all 1,700 selected tests in 125.33 seconds. This feature did
not add a slow test to the marker. An `-n auto`
diagnostic took 32.58 seconds and exposed an existing process-global
`.planalign_init.lock` collision, so parallel execution is not a valid shortcut.
The timing requirement is therefore not currently satisfiable without a
repository-wide marker/fixture cleanup outside feature 120. Functional pass
status is recorded separately from this known constitution exception.

## Final suite

With `DATABASE_PATH=/tmp/planalign-u120-full-suite-20260720.duckdb`, the full
suite completed with **2,359 passed and 4 expected skips in 440.40 seconds**.
The skips require opt-in calibration baselines or an explicit expensive
reproducibility flag and are unrelated to this feature.
