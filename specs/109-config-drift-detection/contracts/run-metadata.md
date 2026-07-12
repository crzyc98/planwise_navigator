# Contract: `planalign_orchestrator.run_metadata`

**Feature**: 109-config-drift-detection | **Date**: 2026-07-12

This feature has no HTTP/CLI surface; its contracts are (1) the module API consumed by the two run entry points and (2) the `run_metadata` table schema, which is a public audit surface users query directly with the `duckdb` CLI.

## 1. Module API

```python
# planalign_orchestrator/run_metadata.py

RUN_METADATA_TABLE: str = "run_metadata"

class DriftStatus(Enum):
    NO_HISTORY = "no_history"
    MATCH = "match"
    DRIFT = "drift"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class DriftCheckResult:
    status: DriftStatus
    config_changed: bool
    seed_changed: bool
    prior_seed: int | None
    current_seed: int | None
    prior_fingerprint: str | None
    current_fingerprint: str
    prior_timestamp: datetime | None
    suppressed_by_full_reset: bool

def compute_config_fingerprint(config: SimulationConfig) -> str:
    """SHA-256 hex digest of canonical JSON of to_dbt_vars(config) with
    'random_seed' removed. Pure and deterministic (FR-007)."""

def check_and_record_run(
    db_manager: DatabaseConnectionManager,
    config: SimulationConfig,
    *,
    start_year: int,
    end_year: int,
    run_type: Literal["simulate", "batch", "calibration"],
    full_reset: bool = False,
) -> DriftCheckResult:
    """Compare current fingerprint+seed to the latest run_metadata row,
    emit the appropriate log message, append this run's record, and return
    the result. NEVER raises for database errors (FR-005): any duckdb.Error
    is logged once and yields DriftCheckResult(status=UNKNOWN, ...)."""
```

### Behavioral guarantees

| Guarantee | FR |
|---|---|
| Called (and message emitted) before any dbt model builds | FR-003 |
| Warning on DRIFT names config-vs-seed distinctly; seed message includes old and new values | FR-004 |
| Non-blocking always; internal errors degrade to UNKNOWN + one log note | FR-005 |
| NO_HISTORY (new/legacy DB) emits info note, not a warning | FR-006 |
| Exactly one row appended per invocation; no update/delete API exists | FR-008 |
| DRIFT message includes remedies: fresh/isolated DB or `setup.clear_tables: true` + `clear_mode: all` | FR-010 |
| `full_reset=True` or `run_type="calibration"` downgrades DRIFT messaging from warning to info (record still appended, `status` still DRIFT) | edge cases |

### Call sites (the other half of the contract)

| Caller | Location | run_type | Notes |
|---|---|---|---|
| `PipelineOrchestrator.execute_multi_year_simulation` | after `maybe_full_reset()` inside `ExecutionMutex` | `"simulate"` (or `"batch"` when invoked by `scenario_batch_runner` — passed through orchestrator construction context; if plumbing a flag is disproportionate, `"simulate"` for both is acceptable v1) | `full_reset` = whether `setup.clear_tables` with `clear_mode='all'` is active |
| `CalibrationRunner.run_calibration` | before per-year builds | `"calibration"` | always downgraded messaging |

`dry_run=True` runs MUST NOT stamp a record (nothing is written to the DB, so recording would be false provenance) — the orchestrator call site skips the call when `dry_run` is set.

## 2. Table schema (public audit surface)

```sql
CREATE TABLE IF NOT EXISTS run_metadata (
    run_id             VARCHAR   NOT NULL,
    run_timestamp      TIMESTAMP NOT NULL,
    run_type           VARCHAR   NOT NULL,
    config_fingerprint VARCHAR   NOT NULL,
    random_seed        BIGINT,
    start_year         INTEGER   NOT NULL,
    end_year           INTEGER   NOT NULL,
    scenario_id        VARCHAR,
    plan_design_id     VARCHAR,
    planalign_version  VARCHAR,
    full_reset         BOOLEAN   NOT NULL DEFAULT FALSE
);
```

Stability promise: columns may be **added** in future versions; existing columns are never renamed, retyped, or removed (users query this table directly — SC-005).

### Canonical audit query (documented in quickstart)

```sql
SELECT run_timestamp, run_type, substr(config_fingerprint, 1, 12) AS fingerprint,
       random_seed, start_year, end_year, full_reset
FROM run_metadata
ORDER BY run_timestamp DESC;
```

## 3. Log message contract (user-visible)

- **DRIFT (warning)** — multi-line, matching the `warn_if_stale_years_beyond` tone: states the DB was last written under a different {configuration | seed | configuration and seed}, shows prior run timestamp, prior→current seed values when the seed changed, prior→current fingerprint short-hashes (12 chars) when config changed, and the two remedies (FR-010).
- **NO_HISTORY (info)** — "no prior run record; recording this run for future drift detection."
- **MATCH** — silent (SC-003: no warning fatigue).
- **UNKNOWN (info)** — single note that drift detection was skipped and why.
