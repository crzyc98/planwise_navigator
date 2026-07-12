# Implementation Plan: Config Drift Detection

**Branch**: `109-config-drift-detection` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/109-config-drift-detection/spec.md`

## Summary

Stamp every simulation run's effective-config fingerprint + random seed + year range into an append-only `run_metadata` table inside the target DuckDB at run start; on subsequent runs against the same database, compare against the most recent record and emit a loud, non-blocking warning on mismatch (seed changes called out distinctly). One new small module (`planalign_orchestrator/run_metadata.py`) computes the fingerprint from the existing `to_dbt_vars()` surface and performs check-then-record; it is wired into the two run entry points that exist: `PipelineOrchestrator.execute_multi_year_simulation` (covers `simulate`, batch, and Studio, which all funnel through it) and `CalibrationRunner` (which drives dbt directly).

## Technical Context

**Language/Version**: Python 3.11 (orchestrator); no dbt model changes — the metadata table is orchestrator-managed DDL, like the hazard-cache registry
**Primary Dependencies**: existing `planalign_orchestrator` internals only — `to_dbt_vars()` (`config/export.py`), `DatabaseConnectionManager` (`utils.py`), `hashlib` (stdlib); Rich already available for CLI presentation
**Storage**: DuckDB — new append-only `run_metadata` table created lazily in each target database (shared dev DB, per-scenario batch DBs, calibration DBs)
**Testing**: pytest with E075 fixtures (`tests/fixtures/database.py` in-memory/isolated DBs); fast-marker unit tests for fingerprint + check/record logic; integration test via isolated `DATABASE_PATH` DB
**Target Platform**: macOS/Linux work laptops (on-prem analytics servers)
**Project Type**: single project — orchestrator library + CLI
**Performance Goals**: drift check + stamp adds <100ms to run startup (one table probe, one SELECT of the latest row, one INSERT)
**Constraints**: MUST never block or fail a run (detection degrades to a logged note on any error); append-only records; deterministic fingerprint across machines
**Scale/Scope**: one new module (~150 lines), two call-site wirings, tests; no schema migration of existing tables, no API/UI changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Event Sourcing & Immutability | ✅ PASS | Run records are append-only with UUID + timestamp — the feature *extends* immutability/reproducibility guarantees to run provenance. |
| II. Modular Architecture | ✅ PASS | One new single-responsibility module well under 600 lines, ≤4 public symbols; no reverse-layer dependencies (orchestrator-level, no dbt model reads `run_metadata`). |
| III. Test-First Development | ✅ PASS | Unit tests (fingerprint determinism/sensitivity, check/record state machine) written first against in-memory DuckDB fixtures; integration test on isolated DB. |
| IV. Enterprise Transparency | ✅ PASS | This feature *is* transparency: every run logged with context; warning includes what changed and resolution guidance (E074 style). |
| V. Type-Safe Configuration | ✅ PASS | Fingerprint derives from the validated Pydantic config via `to_dbt_vars()`; result object is a typed dataclass; no raw table-name concatenation beyond the single constant. |
| VI. Performance & Scalability | ✅ PASS | O(1) startup work; single-threaded; no per-employee cost. |

**Post-Phase-1 re-check**: PASS — design introduces no violations; Complexity Tracking table left empty.

## Project Structure

### Documentation (this feature)

```text
specs/109-config-drift-detection/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── run-metadata.md  # Table schema + module API contract
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── run_metadata.py                  # NEW: fingerprint + check-then-record + DriftCheckResult
├── pipeline_orchestrator.py         # MODIFIED: wire check into execute_multi_year_simulation
│                                    #   (inside ExecutionMutex, next to maybe_full_reset /
│                                    #    warn_if_stale_years_beyond)
├── calibration_runner.py            # MODIFIED: wire check into CalibrationRunner (run_type='calibration')
└── config/export.py                 # UNCHANGED: to_dbt_vars() is the fingerprint input surface

tests/
├── test_run_metadata.py             # NEW: fast unit tests (fingerprint, state machine, degradation)
└── test_run_metadata_integration.py # NEW: isolated-DB integration (two runs, drift warning, history)
```

**Structure Decision**: Single project, orchestrator-level. Detection lives in `planalign_orchestrator/run_metadata.py` (top-level, beside `hazard_cache_manager.py`, which already owns a similar orchestrator-managed metadata table) rather than in `pipeline/` — `CalibrationRunner` does not use the pipeline package, and both entry points must share the module. Batch (`scenario_batch_runner.py`) and Studio simulations call `execute_multi_year_simulation`, so wiring the orchestrator covers them with no additional call sites.

## Complexity Tracking

*No constitution violations — table intentionally empty.*
