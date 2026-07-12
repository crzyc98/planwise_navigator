# Data Model: Config Drift Detection

**Feature**: 109-config-drift-detection | **Date**: 2026-07-12

## Entity: Run Record (`run_metadata` table)

One row per simulation run, appended at run start into the target DuckDB. Never updated or deleted (append-only; survives `maybe_full_reset()` because the table name matches neither the `int_` nor `fct_` clear patterns).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `run_id` | VARCHAR | NOT NULL, UUID4 | Unique run identifier |
| `run_timestamp` | TIMESTAMP | NOT NULL | UTC stamp at run start (before any model builds) |
| `run_type` | VARCHAR | NOT NULL, one of `simulate` / `batch` / `calibration` | Entry point that produced the run |
| `config_fingerprint` | VARCHAR | NOT NULL, 64 hex chars | SHA-256 of canonical JSON of `to_dbt_vars(cfg)` minus `random_seed` |
| `random_seed` | BIGINT | NULLABLE | `simulation.random_seed` (nullable to tolerate legacy/edge configs) |
| `start_year` | INTEGER | NOT NULL | First simulated year of the run |
| `end_year` | INTEGER | NOT NULL | Last simulated year of the run |
| `scenario_id` | VARCHAR | NULLABLE | Config `scenario_id` (falls back to NULL, not "default", to record what was actually set) |
| `plan_design_id` | VARCHAR | NULLABLE | Config `plan_design_id` |
| `planalign_version` | VARCHAR | NULLABLE | From `_version.py`, audit convenience |
| `full_reset` | BOOLEAN | NOT NULL DEFAULT FALSE | Whether this run performed a `clear_mode='all'` full reset before building |

No primary-key enforcement is required (DuckDB, single-writer under `ExecutionMutex`); `run_id` uniqueness comes from UUID4.

### Lifecycle / state notes

- **Created lazily**: `CREATE TABLE IF NOT EXISTS` on first stamp; absence in a legacy DB is the "no history" state, never an error.
- **Interrupted runs**: because the stamp happens before year 1 builds, a crashed run still leaves its record — the next run's comparison correctly reflects that the DB was last written under that fingerprint.
- **Isolation**: each `.duckdb` (shared dev, per-scenario batch, calibration copy) carries its own independent history; no cross-database comparison exists.

## Value object: `DriftCheckResult` (Python dataclass, frozen)

| Field | Type | Description |
|---|---|---|
| `status` | `DriftStatus` enum | `NO_HISTORY` / `MATCH` / `DRIFT` / `UNKNOWN` (detection failed gracefully) |
| `config_changed` | bool | Fingerprint differs from latest record |
| `seed_changed` | bool | Seed differs from latest record |
| `prior_seed` | int \| None | Seed of latest record (for FR-004 messaging) |
| `current_seed` | int \| None | Seed of this run |
| `prior_fingerprint` | str \| None | Latest recorded fingerprint |
| `current_fingerprint` | str | This run's fingerprint |
| `prior_timestamp` | datetime \| None | When the latest recorded run started |
| `suppressed_by_full_reset` | bool | Drift existed but a full reset makes mixed generations impossible → downgraded messaging |

### State machine (per run start)

```
no run_metadata table, or zero rows  → NO_HISTORY  (info note; INSERT record)
latest row: fingerprint == ∧ seed == → MATCH       (silent; INSERT record)
latest row: fingerprint ≠ ∨ seed ≠  → DRIFT        (warning — or info if full_reset
                                                    this run or run_type=calibration;
                                                    INSERT record)
any duckdb.Error during check/insert → UNKNOWN     (single logged note; run proceeds)
```

## Relationships

- `run_metadata` has no foreign keys and is read by no dbt model (no layer-dependency impact; staging→intermediate→marts untouched).
- Input dependency only: `config_fingerprint` is a pure function of `SimulationConfig` via `to_dbt_vars()`.

## Validation rules (from FRs)

- FR-007 determinism: fingerprint function must be pure — canonical JSON (`sort_keys=True`), stable coercion for `Decimal`/`date` (`default=str`), UTF-8.
- FR-008 append-only: module exposes no update/delete operations on `run_metadata`.
- FR-005 non-blocking: every public entry catches `duckdb.Error` and returns `UNKNOWN` instead of raising.
