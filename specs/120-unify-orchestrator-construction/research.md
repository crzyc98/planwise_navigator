# Phase 0 Research: Unify Orchestrator Construction

All findings below are grounded in the current `main` (post #455/#466/#479). They resolve the two open assumptions from the spec and the unknowns in the plan's Technical Context.

## R1. Inventory of current construction paths (what diverges)

**Decision**: Treat the `OrchestratorWrapper` behavior as canonical; converge the others onto it.

**Findings** — the runnable construction sites:

| Path | Location | Installs |
|---|---|---|
| Wrapper (product) | `planalign_cli/integration/orchestrator_wrapper.py:197` | `DbtRunner(db_manager, database_path, project_dir, threading)`, `RegistryManager`, `DataValidator`+2 rules, `PipelineOrchestrator`. Forces `event_generation.mode="sql"`; validates threading + eligibility. **No** self-healing hook. **No** engine selection. |
| Factory | `planalign_orchestrator/factory.py:124` (`create_orchestrator` / `OrchestratorBuilder`) | Builds via `OrchestratorBuilder.build()`; registers a `PRE_SIMULATION` **self-healing init hook** (`auto_initialize=True` default). Does **not** force sql-mode or run the wrapper's config validations. |
| Batch | `planalign_orchestrator/scenario_batch_runner.py:292` | Calls `create_orchestrator(config, db_manager, threads=…)` → **the factory path (self-healing on)**. |
| Legacy CLI | `planalign_orchestrator/cli.py:72` | Direct `PipelineOrchestrator(...)` construction (third variant). |
| Harness/probe | `scripts/perf_profile/run_matrix.py`, `probe_direct_execution.py` | Factory (`create_orchestrator`) — the `wrapper|factory` toggle added in #455 lets the harness now exercise either. |

**Consequence**: `simulate` (wrapper) and batch (factory) genuinely construct differently today — different init behavior and config-validation. This is the divergence to eliminate.

**Alternatives considered**: (a) make the factory canonical and fold wrapper into it — rejected: the factory carries the self-healing init + #467 hazard and is *not* what production runs, so it is the wrong reference of record. (b) Leave both, add a shared "settings" object — rejected: does not remove divergence (FR-009 / SC-001 require one path).

## R2. Self-healing initializer & the #467 swallowed-failure

**Decision**: The canonical (production) path installs **no implicit self-healing**. Self-healing becomes an explicit, opt-in `InitializationPolicy` with a **fail-loud** contract. Fresh-DB preparation on the canonical path relies on the pipeline's own setup, which production already uses.

**Findings**:
- `AutoInitializer.ensure_initialized()` (`planalign_orchestrator/self_healing/auto_initializer.py:103`) runs steps: check → `load_seeds` (`dbt seed --full-refresh`) → `build_foundation` (staging + `int_baseline_workforce`) → verify, returning an `InitializationResult`.
- The factory registers it as a `PRE_SIMULATION` hook that raises `InitializationError` when `not result.success` (`factory.py:181-198`).
- **#467 root cause**: `HookManager.execute_hooks` (`planalign_orchestrator/pipeline/hooks.py:175-177`) wraps every hook in `except Exception: logger.error(...)` and **continues** ("Error isolation … continue pipeline execution"). So the init hook's `InitializationError` is **swallowed** — on a fresh DB the `build_foundation` step fails after seeding succeeded, the run continues anyway, and it happens to work only because the pipeline's own `_ensure_seeds_loaded` + `_run_start_year_setup` (`pipeline_orchestrator.py:586,590,654,674`) re-prepare the DB.
- This proves the self-healing init is **redundant with the pipeline's own setup on the product path** (the same reason its duplicate-seed optimization was dead code in #468). Production (`simulate`, no self-healing) already initializes fresh DBs correctly.

**Batch dependency resolution (the spec's assumption #1)**: batch currently gets self-healing via the factory. Because the pipeline's own setup prepares fresh DBs (that is how `simulate` works on a fresh DB), batch drops implicit self-healing. **Verification gate**: an isolated fresh-DB batch run must produce byte-identical outputs before and after removal. If a gap surfaces, repair the missing canonical setup step and keep batch on `InitializationPolicy.NONE`; retaining entry-point-specific initialization would violate FR-003 and SC-002.

**Fail-loud mechanism options** (decide in design): (a) run initialization **explicitly before** `execute_multi_year_simulation` (not via a hook), letting `InitializationError` propagate — simplest, avoids the swallow entirely; or (b) add a `critical: bool` flag to `Hook` and have `execute_hooks` re-raise for critical hooks. **Leaning (a)** — keeps hook error-isolation intact for genuinely optional hooks and makes the init contract explicit and un-swallowable.

## R3. Where to record the construction signature + work schedule

**Decision**: Persist the construction signature on the existing run-start `run_metadata` row and persist the finalized ordered schedule in an append-only terminal execution record written at run completion. Expose both in-process for harness/parity tooling.

**Findings**:
- `run_metadata.py` already defines a lazily-created `run_metadata` table with `run_id`, `run_type`, `config_fingerprint`, `random_seed`, timestamps, `start_year`/`end_year`, and `check_and_record_run(...)` is called at run start.
- Feature 119 already deployed an eleven-column `run_execution_metadata` table. Feature 120 must extend that exact table with nullable `invocation_count` and `schedule_steps` columns and continue supplying all of Feature 119's required fields; reusing the name with an incompatible four-column `CREATE TABLE IF NOT EXISTS` shape fails on existing scenario databases.
- The `#455` harness already models a `construction` signal + per-invocation schedule (`scripts/perf_profile/profile_config.py`), so the product signature and the harness signature can share one shape.

**Alternatives considered**: writing final schedule values on the startup row — rejected because those values do not exist yet and updating the row would violate append-only provenance. Log-only — rejected because FR-005/FR-014 require queryable, testable diagnostics. A terminal companion record is the smallest append-only representation that preserves the lifecycle.

## R4. Execution-engine option contract

**Decision**: Reject unsupported `optimization.execution_engine` values at validation; do not wire any alternate engine.

**Findings at implementation**: the field was absent before this feature, so unknown values were accepted as untyped extras and ignored. `OptimizationSettings.execution_engine` is now typed, defaults to `dbt`, and rejects every other value during config/CLI validation. The canonical builder resolves the validated field as its single engine attach point.

**Alternatives considered**: silently default unknown values to standard — rejected (that *is* the bug class SC-004 forbids). Wire the compiled engine end-to-end — rejected (out of scope; #476 is paused/NO-GO and "do not advertise").

## R5. Migration & test-adapter strategy

**Decision**: Incremental, parity-gated migration behind stable public call sites.

**Findings/approach**:
- Introduce `planalign_orchestrator/construction/` and route `OrchestratorWrapper.create_orchestrator` through it first (product path — proves canonical == current production, byte-identical).
- Then migrate batch, then `cli.py` (or delete it if unused), then the harness/probe, then every direct-construction test site found by repository search.
- `factory.create_orchestrator` becomes a thin adapter that calls the canonical builder with `InitializationPolicy.SELF_HEALING` (fail-loud) so existing factory callers/tests keep working during migration; removed once no caller needs it (FR-009).
- Tests construct via the canonical seam with explicit overrides (mock runner, in-memory DB) rather than reproducing construction — the seam accepts injected dependencies for testability.
- Every migration step validated with the `#455` harness + `EXCEPT ALL` multiset parity (both configs, isolated DBs) and green fast+integration suites; shared dev DB SHA-256 unchanged.

## Resolved unknowns summary

| Unknown (Technical Context) | Resolution |
|---|---|
| Canonical behavior of record | Production `OrchestratorWrapper` behavior (R1) |
| Batch's self-healing dependency | Removable; pipeline setup covers fresh DBs; repair canonical setup if parity exposes a gap (R2) |
| Fail-loud init mechanism | Explicit pre-run initialization outside hook isolation (R2) |
| Signature/schedule storage | Start signature on `run_metadata`; finalized schedule in a terminal append-only record (R3) |
| Engine-option contract | Reject unsupported values at validation; no engine wiring (R4) |
| Test migration | Canonical seam with injected overrides; incremental, parity-gated (R5) |

No `NEEDS CLARIFICATION` items remain open.
