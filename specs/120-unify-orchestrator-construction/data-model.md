# Phase 1 Data Model: Unify Orchestrator Construction

This feature adds **no** simulation-data tables and changes **no** `fct_*`/`int_*` schemas. The "entities" below are in-process construction types plus a small extension to the existing `run_metadata` provenance record.

## 1. ConstructionSpec (input)

The Pydantic-v2 typed and validated input to the canonical builder — everything an entry point supplies to construct a run.

| Field | Type | Notes |
|---|---|---|
| `config` | `SimulationConfig` (Pydantic v2) | Already-validated configuration. |
| `database` | `Path \| DatabaseConnectionManager` | Resolved run database. Feature validation requires an isolated per-run/scenario DB; normal development behavior remains unchanged. |
| `threads` | `int` (default from config) | Single-threaded default (constitution VI). |
| `dbt_project_dir` | `Optional[Path]` | Scenario project overlay; `None` ⇒ shared `dbt/`. |
| `initialization` | `InitializationPolicy` | Default `NONE`. See entity 3. |
| `execution_engine` | `ExecutionEngineOption` | Default standard. See entity 5. Config-facing ⇒ **Pydantic v2** validated (constitution V). |
| `entry_point` | `str` | Attribution: `cli.simulate \| batch \| studio \| parity \| invariant_test \| perf_harness`. |
| `validation_mode` | `bool` | When true, the builder refuses the shared dev DB (see below). Default false. |
| `verbose` | `bool` | Diagnostics verbosity only. |
| `dry_run` | `bool` | Maps runner executable to a no-op, as today. |

**Type policy (constitution V)**: `ConstructionSpec`, `ExecutionEngineOption`, and any config-facing additions are **Pydantic v2** models/validators. `InitializationPolicy` is an enum. Internal, non-configuration observability values (`ConstructionSignature`, `WorkSchedule`) may be plain dataclasses.

**Validation rules**:
- `config` MUST have passed `validate_threading_configuration()` and `validate_eligibility_configuration()` (the builder invokes these, matching the wrapper today).
- `event_generation.mode` is forced to `"sql"` (Polars removed in E024).
- The shared-DB guard is **validation-only**: the builder refuses `dbt/simulation.duckdb` **only when `validation_mode=True`**. Normal production/dev runs may legitimately target the shared dev DB, so the guard MUST NOT be unconditional.
- Unsupported `execution_engine` ⇒ reject (entity 5).

## 2. CanonicalConstruction (behavior, not persisted)

The single authoritative assembly the builder produces: a fully-wired `PipelineOrchestrator` with `DbtRunner`, `RegistryManager`, `DataValidator` (+ standard rules), `HookManager`, resolved thread policy, resolved initialization policy, and resolved engine. Identical for a given `ConstructionSpec` regardless of caller.

## 3. InitializationPolicy (enum)

| Value | Meaning |
|---|---|
| `NONE` (default, canonical/production) | No implicit self-healing. The pipeline's own `_ensure_seeds_loaded` + `_run_start_year_setup` prepare fresh/empty databases (current `simulate` behavior). |
| `SELF_HEALING` (explicit opt-in) | Run `AutoInitializer.ensure_initialized()` **before** the simulation, with a **fail-loud** contract: a critical failure raises and aborts the run — it is never routed through swallowing hook isolation. Resolves #467. |

**State/behavior**: `SELF_HEALING` failure ⇒ run aborts, zero outputs. Success ⇒ proceed. `NONE` never installs the self-healing hook. Both must yield identical outputs on an already-initialized DB.

## 4. ConstructionSignature (observable record)

Emitted per run and persisted; the comparable proof that two entry points constructed identically (FR-005, SC-002).

| Field | Type | Source |
|---|---|---|
| `entry_point` | `str` | `"cli.simulate" \| "batch" \| "studio" \| "parity" \| "invariant_test" \| "perf_harness"` |
| `runner_kind` | `str` | Resolved runner behavior (standard dbt runner today). |
| `database_path` | `str` | Resolved isolated DB path. |
| `dbt_project_dir` | `str` | Resolved project dir (`dbt/` or overlay). |
| `thread_count` | `int` | Resolved thread policy. |
| `initialization_policy` | `str` | `NONE \| SELF_HEALING`. |
| `installed_hook_names` | `list[str]` | Names of registered hooks (order-stable). |
| `execution_engine` | `str` | Resolved engine (`dbt`). |
| `signature_hash` | `str` | Stable hash over semantic construction fields — the single comparable value. |

**Rule**: For a fixed validated config, `signature_hash` is identical across all entry points. Exclude `entry_point` and the literal run-specific database path; encode the database isolation policy and project relationship (`shared` versus the same scenario overlay) semantically. Shares its field shape with the `#455` harness `construction` signal.

## 5. ExecutionEngineOption

Config-facing ⇒ **Pydantic v2** validator (constitution V).

| Value | Behavior |
|---|---|
| standard (`"dbt"`/unset) | Supported; the only engine present on `main`. |
| any other value | **Rejected at validation** with a clear message naming the option (FR-008, SC-004). No silent default. |

## 6. WorkSchedule (observable, terminal record)

The **executed** ordered list of build/execution steps a run performed — captured during execution and finalized at run completion (it does not exist at run start). Used by the production-path integration test (FR-014) and as the authoritative baseline that #478 reduces.

| Field | Type | Notes |
|---|---|---|
| `steps` | `list[ScheduleStep]` | Ordered, as executed. |
| `ScheduleStep.seq` | `int` | Position. |
| `ScheduleStep.command` | `str` | The dbt command/selector issued. |
| `ScheduleStep.stage` | `Optional[str]` | Workflow stage. |
| `ScheduleStep.year` | `Optional[int]` | Simulation year. |
| `ScheduleStep.runner_kind` | `str` | Runner that executed the step. |
| `invocation_count` | `int` | Total executed invocations (provisional; the authoritative value is established by this capture, reconciling the 38-vs-62 count discrepancy — see spec Assumptions). |

## 7. Persistence: run-start signature + terminal execution record

Two distinct write points on the existing `run_metadata` provenance store (Feature 109) — **no new fct/int table**:

- **Run-start (signature)**: on the run's `run_metadata` row, record `construction_signature_hash`, `initialization_policy`, `entry_point`, `runner_kind`. Written on the existing run-start recording path (`check_and_record_run`). These are known at construction time.
- **Run-completion (executed schedule)**: append to Feature 119's existing `run_execution_metadata` terminal-record shape, carrying its required engine/status fields plus the finalized `invocation_count` and ordered `steps` (seq, command/selector, stage, year, runner_kind). Final executed values MUST NOT be written at run start.

**Schema evolution (idempotent)**: pre-existing scenario databases may carry both the older `run_metadata` schema and Feature 119's eleven-column `run_execution_metadata` schema. `CREATE TABLE IF NOT EXISTS` will not add new columns. The recorder MUST perform idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS` on both tables (and create the full compatible terminal shape if absent), preserve historical terminal rows with `NULL` schedule fields, and fail loudly if a required column cannot be added. Backward compatibility is covered by tests against both deployed schemas.

Both records are append-only and queryable for the FR-005 audit and the FR-014 integration test.

## Relationships

```
Entry point ──builds──▶ ConstructionSpec ──canonical builder──▶ CanonicalConstruction (PipelineOrchestrator)
                                     │                                   │
                                     └── initialization: InitializationPolicy
                                     └── execution_engine: ExecutionEngineOption (validated)
CanonicalConstruction ──emits──▶ ConstructionSignature ──run-start──▶ run_metadata row
Run execution ────────emits──────▶ WorkSchedule ──run-completion──▶ terminal execution record
```
