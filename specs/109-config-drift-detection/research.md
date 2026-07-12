# Research: Config Drift Detection

**Feature**: 109-config-drift-detection | **Date**: 2026-07-12

No NEEDS CLARIFICATION markers remained in the Technical Context; research below records the design decisions and the codebase evidence behind them.

## D1: Fingerprint input surface — `to_dbt_vars()` canonical JSON, seed excluded

**Decision**: `config_fingerprint = sha256(json.dumps(to_dbt_vars(cfg) minus "random_seed", sort_keys=True, default=str))`. The random seed is stored in its own column and compared separately.

**Rationale**:
- `to_dbt_vars()` (`planalign_orchestrator/config/export.py:1293`) is precisely the "effective, result-affecting" configuration: it is the full var surface handed to dbt, shared by simulate, batch, and calibration (`calibration_runner.py` imports it explicitly). Anything that changes simulation output must flow through it; FR-007's no-false-negative requirement is satisfied by construction for all SQL-driven behavior.
- Hashing the raw `SimulationConfig.model_dump()` instead would fold in non-result-affecting knobs (`setup.clear_tables`, `optimization`, `orchestrator` threading, verbosity) — and `setup.clear_tables` toggling is exactly the *remedy* the warning recommends, so it would guarantee a false positive on the recommended clean-rerun flow.
- Excluding `random_seed` from the hash (it is exported at `export.py:70-71`) lets the warning distinguish "seed changed" from "config changed" (FR-004) without diffing.
- Canonical JSON (`sort_keys=True`, `default=str` for Decimal/date) gives determinism across runs and machines (FR-007).

**Alternatives considered**:
- *Hash the YAML config file bytes*: rejected — comment/whitespace edits and CLI/dbt-var overrides would produce false results in both directions; the file is not the effective config.
- *Hash full `model_dump()`*: rejected per above (false positive on the sanctioned clean-rerun remedy).
- *Store the full vars JSON for field-level diffs in the warning*: deferred — the spec only requires identifying config-vs-seed; storing full JSON is a cheap future extension (column exists in the schema as nullable `config_json`? — **no**: keep the table minimal now; a richer diff can be added later by widening the message, not the promise).

## D2: Storage — orchestrator-managed `run_metadata` table, lazy DDL, append-only

**Decision**: A `run_metadata` table created with `CREATE TABLE IF NOT EXISTS` by the new module on first stamp, in the target database itself. One INSERT per run at run start. Never UPDATE/DELETE.

**Rationale**:
- The database must be self-describing (SC-005), and per-scenario isolated DBs each need their own history (edge case in spec) — so the record lives in the DB, not in `var/` logs.
- Precedent: `hazard_cache_manager.py` already owns an orchestrator-managed metadata table with SHA-256 checksums in the same database; this is an established pattern, not a new architecture.
- Not a dbt model/seed: dbt models are rebuilt/truncated by the pipeline and by `maybe_full_reset()` (which clears `int_`/`fct_` prefixes — `run_metadata` deliberately matches neither pattern, so history survives clean reruns, satisfying the audit story even across resets).

**Alternatives considered**:
- *dbt seed or model*: rejected — rebuilt by the pipeline, wrong lifecycle, and dbt writes happen after the point where the warning must fire (FR-003: before simulation work begins).
- *Sidecar JSON file next to the .duckdb*: rejected — separable from the database it describes; copies/moves lose provenance.

## D3: Wiring points — two call sites cover every writer

**Decision**: Call `check_and_record_run(...)` (1) in `PipelineOrchestrator.execute_multi_year_simulation` inside the `ExecutionMutex`, immediately after `maybe_full_reset()` / `warn_if_stale_years_beyond()` (`pipeline_orchestrator.py:290-291`); (2) in `CalibrationRunner.run_calibration` before the per-year builds (`run_type='calibration'`).

**Rationale**:
- Caller audit: `execute_multi_year_simulation` is invoked by `planalign_cli/commands/simulate.py:154`, `planalign_cli/integration/orchestrator_wrapper.py:411` (Studio), `planalign_orchestrator/cli.py:83`, and `planalign_orchestrator/scenario_batch_runner.py:302` (batch). One wiring covers simulate + batch + Studio (FR-009).
- `CalibrationRunner` drives `DbtRunner` directly and never touches `PipelineOrchestrator`, so it needs its own call.
- Placing the check *after* `maybe_full_reset()` lets the module see whether a full reset just ran: when `setup.clear_tables` + `clear_mode='all'` is active, prior results were wiped, mixed generations are impossible, and the drift message downgrades from warning to informational note (avoids punishing the exact remedy FR-010 recommends). The run is still recorded either way.
- Calibration intentionally diverges from the baseline DB's config (comp levers) and intentionally leaves DC tables stale — the calibration-path message is worded for that reality ("comp levers differ from the run that built this DB; DC-plan tables are stale by design") rather than pretending it's accidental drift.

**Alternatives considered**:
- *Hook via `HookType.PRE_SIMULATION`*: rejected — hooks don't cover CalibrationRunner and bury a correctness feature in an extension mechanism.
- *Wire each CLI command*: rejected — four call sites instead of two, and Studio/API paths would be easy to miss.

## D4: Warning presentation — module logs via `logger.warning`, matching `warn_if_stale_years_beyond`

**Decision**: The shared module emits a multi-line `logger.warning` (or `logger.info` for the no-history / post-full-reset / calibration cases) containing: what changed (config fingerprint short-hash old→new, and/or seed old→new), when the prior run happened, and the FR-010 remedies. The CLI does not grow a separate Rich panel in this feature; orchestrator log output is already surfaced by all entry points.

**Rationale**: `StateManager.warn_if_stale_years_beyond` (`state_manager.py:268`) is the direct precedent — same contamination class (stale trailing years), same channel, already accepted as "loud" in this codebase. One emission point serves all four entry paths; a Rich panel would only cover `planalign simulate`.

**Alternatives considered**: *Rich Panel in `simulate.py`* — deferred as a follow-up polish; requires returning the `DriftCheckResult` through `MultiYearSummary` or a callback, disproportionate for v1.

## D5: Failure semantics — detection never raises

**Decision**: All DuckDB errors inside check/record (table unreadable, corrupt, permission) are caught, logged as a single note, and the run proceeds; the function returns a `DriftCheckResult(status=UNKNOWN)`.

**Rationale**: FR-005 and the edge-case list are explicit: a provenance feature must never take down a simulation. Catch `duckdb.Error` specifically (constitution: no bare except).

## D6: Comparison target — most recent record only

**Decision**: Compare current fingerprint+seed against the latest row by `run_timestamp` (tie-broken by insertion order via `rowid`-equivalent max). Full history retained for audit (US3) but not scanned for drift.

**Rationale**: Spec assumption made explicit during /speckit.specify; the last run defines the state the DB was left in. Comparing against all history would warn forever on a DB that drifted once and was then fully reset.
