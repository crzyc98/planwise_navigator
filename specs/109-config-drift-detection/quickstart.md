# Quickstart: Config Drift Detection

**Feature**: 109-config-drift-detection

## See it work (isolated DB, per §8 of CLAUDE.md — never the shared dev DB)

```bash
mkdir -p /tmp/run109 && cp config/simulation_config.yaml /tmp/run109/cfg.yaml

# 1. First run into a fresh DB → info note ("no prior run record"), record stamped
DATABASE_PATH=/tmp/run109/iso.duckdb \
  planalign simulate 2025-2026 --config /tmp/run109/cfg.yaml --database /tmp/run109/iso.duckdb

# 2. Re-run unchanged → silent (MATCH), second record appended
DATABASE_PATH=/tmp/run109/iso.duckdb \
  planalign simulate 2025-2026 --config /tmp/run109/cfg.yaml --database /tmp/run109/iso.duckdb

# 3. Change a result-affecting value (e.g. simulation.target_growth_rate) or
#    simulation.random_seed in cfg.yaml, re-run → LOUD drift warning before any builds
DATABASE_PATH=/tmp/run109/iso.duckdb \
  planalign simulate 2025-2026 --config /tmp/run109/cfg.yaml --database /tmp/run109/iso.duckdb
```

## Audit a database's provenance (US3 / SC-005)

```bash
duckdb /tmp/run109/iso.duckdb "
  SELECT run_timestamp, run_type, substr(config_fingerprint,1,12) AS fingerprint,
         random_seed, start_year, end_year, full_reset
  FROM run_metadata ORDER BY run_timestamp DESC"
```

Two different fingerprints in the history = the DB has held mixed-generation results at some point.

## Clean remedies the warning recommends

```bash
# Fresh isolated DB (preferred)
planalign batch --scenarios my_scenario --clean

# Or full clean rerun into the same DB (suppresses the drift warning for that run,
# since prior results are wiped first):
#   setup.clear_tables: true
#   setup.clear_mode: all
```

## Run the tests

```bash
pytest -m fast tests/test_run_metadata.py -v                      # unit: fingerprint + state machine
DATABASE_PATH=/tmp/run109/iso.duckdb \
  pytest tests/test_run_metadata_integration.py -v                # integration: end-to-end drift
```

## Key facts

- Detection **never blocks** a run; failures degrade to a logged note.
- `run_metadata` is append-only and survives full resets (not matched by `int_`/`fct_` clear patterns).
- Legacy DBs (no table) get an info note and start accumulating history from their next run.
- Calibration runs record with `run_type='calibration'` and use informational (not warning) messaging, since diverging comp levers and stale DC tables are inherent to calibration.
