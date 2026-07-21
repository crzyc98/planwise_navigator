---

description: "Task list for feature 120 — Unify Orchestrator Construction Across Entry Points"
---

# Tasks: Unify Orchestrator Construction Across Entry Points

**Input**: Design documents from `/specs/120-unify-orchestrator-construction/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: REQUIRED. Constitution Principle III requires tests before implementation. Reusable census/config inputs and generators live under `tests/fixtures/`; all behavioral validation uses isolated databases and `--threads 1`.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: different files and no dependency on unfinished work
- **[Story]**: US1–US4 for user-story work; Setup, Foundational, and Polish have no story label

---

## Phase 1: Setup and Pre-Change Evidence

**Purpose**: Preserve the scale envelope before construction or telemetry code changes and create the canonical package boundary.

- [X] T001 Record the pre-change median completion time and peak RSS across three repetitions of a 100,000-employee multi-year `--threads 1` run using a deterministic generator/recipe in `tests/fixtures/performance_census.py`, isolated databases, and evidence in `specs/120-unify-orchestrator-construction/performance-baseline.md`; record the shared development database SHA-256 before and after and do not commit generated census or database files
- [X] T002 [P] Create `planalign_orchestrator/construction/` with `__init__.py`, `spec.py`, `signature.py`, and `builder.py` package stubs

---

## Phase 2: Foundational Canonical Seam

**Purpose**: Establish one type-safe, final-form builder. No user story begins until this phase is complete.

### Tests first

- [X] T003 [P] Add failing Pydantic validation tests for `ConstructionSpec` and `ExecutionEngineOption` plus enum tests for `InitializationPolicy` in `tests/unit/construction/test_construction_spec.py`
- [X] T004 [P] Add failing deterministic hash and schedule-order tests for `ConstructionSignature`, `WorkSchedule`, and `ScheduleStep` in `tests/unit/construction/test_signature.py`
- [X] T005 [P] Add failing tests in `tests/unit/construction/test_initialization_executor.py` proving explicit `SELF_HEALING` runs outside hook isolation, propagates `InitializationError` with correlation context, and leaves optional-hook error isolation unchanged

### Implementation

- [X] T006 [P] Implement Pydantic-v2 `ConstructionSpec` and `ExecutionEngineOption`, plus `InitializationPolicy` (`NONE`, `SELF_HEALING`), in `planalign_orchestrator/construction/spec.py` per `data-model.md`
- [X] T007 [P] Implement `ConstructionSignature`, `WorkSchedule`, `ScheduleStep`, and stable semantic `signature_hash` in `planalign_orchestrator/construction/signature.py` per `contracts/construction-signature.md`
- [X] T008 Implement `build_orchestrator(spec) -> ConstructionResult` and the explicit fail-loud initialization executor in `planalign_orchestrator/construction/builder.py`: reproduce production wrapper wiring; force SQL event generation; validate threading/eligibility; default to `NONE`; never install initialization as a hook; run explicit `SELF_HEALING` before simulation when requested; refuse `dbt/simulation.duckdb` only when `validation_mode=True`; emit the signature; accept typed test overrides (depends on T003–T007)
- [X] T009 Export the canonical seam and types from `planalign_orchestrator/construction/__init__.py` and `planalign_orchestrator/__init__.py` (depends on T008)

**Checkpoint**: Canonical construction is type-safe, importable, validation-mode aware, and has no swallowed initialization path.

---

## Phase 3: User Story 1 — Same Configuration, Same Product Result (Priority: P1) 🎯 MVP

**Goal**: CLI, batch, and Studio use the same seam, `NONE` initialization policy, semantic construction, and authoritative outputs.

**Independent Test**: Run reference and Studio-realistic fixture configurations through CLI, batch, and Studio into isolated databases; compare explicit authoritative columns with bidirectional `EXCEPT ALL`; expect zero differences and identical signature hashes.

### Tests first

- [X] T010 [P] [US1] Add a failing wrapper-equivalence test in `tests/unit/construction/test_builder_equivalence.py` covering runner database/project/thread settings, forced SQL mode, standard validator rules, and absence of an initialization hook
- [X] T011 [P] [US1] Add a failing fresh-database test in `tests/integration/test_batch_fresh_database_parity.py` using `tests/fixtures/` inputs: batch under `NONE` must complete and match the canonical CLI output; repair canonical setup rather than retaining batch-specific self-healing if it fails
- [X] T012 [P] [US1] Add a failing CLI/batch/Studio parity matrix in `tests/integration/test_product_entrypoint_parity.py` for reference and Studio-realistic fixture configs, explicit multiset columns, isolated DBs, Studio attribution, and unchanged shared-DB SHA-256

### Implementation

- [X] T013 [US1] Migrate `OrchestratorWrapper.create_orchestrator` in `planalign_cli/integration/orchestrator_wrapper.py` to `build_orchestrator` with `InitializationPolicy.NONE`, preserving its public signature and progress callback behavior
- [X] T014 [P] [US1] Migrate `planalign_orchestrator/scenario_batch_runner.py` to `build_orchestrator` with `InitializationPolicy.NONE`; fix any missing canonical fresh-DB preparation exposed by T011 instead of adding a batch-only policy
- [X] T015 [P] [US1] Reduce `planalign_orchestrator/factory.py` to a temporary adapter over `build_orchestrator`; map an explicit `auto_initialize=True` request to fail-loud `SELF_HEALING` without registering a hook
- [X] T016 [P] [US1] Migrate or delete the direct `PipelineOrchestrator(...)` construction in `planalign_orchestrator/cli.py`
- [X] T017 [US1] Propagate an allowlisted Studio-origin marker from `planalign_api/services/simulation/service.py` through `planalign_cli/commands/simulate.py` into the canonical `entry_point`, while direct CLI runs remain `cli.simulate`
- [X] T018 [US1] Run T010–T012 plus the #455 harness for both fixture configurations, save parity evidence in `specs/120-unify-orchestrator-construction/product-parity.md`, and confirm the shared development database hash is unchanged

**Checkpoint**: The three product entry points construct and compute identically. This is the product-entry MVP; tooling-wide SC-002 completes in US2.

---

## Phase 4: User Story 2 — Observable Construction and Production Measurement (Priority: P2)

**Goal**: Persist the start-time signature and terminal executed schedule, migrate all tooling, and reconcile the provisional invocation counts.

**Independent Test**: A completed run has a start signature, a terminal ordered schedule, and the same semantic hash across all six required entry points.

### Tests first

- [X] T019 [P] [US2] Add failing old-schema and lifecycle tests in `tests/integration/test_construction_provenance.py`: idempotently evolve a pre-feature `run_metadata`, write only known signature fields at start, append count/ordered steps at completion, and fail loudly on required-schema errors
- [X] T020 [P] [US2] Add a failing six-entry-point signature matrix in `tests/integration/test_construction_signature_matrix.py` covering `cli.simulate`, `batch`, `studio`, `parity`, `invariant_test`, and `perf_harness` with literal database path and entry-point attribution excluded from the semantic hash
- [X] T021 [P] [US2] Add failing ordered-schedule capture tests in `tests/unit/construction/test_work_schedule_capture.py` covering sequence, command/selector, stage, year, runner kind, and final count

### Implementation

- [X] T022 [US2] Expose `ConstructionSignature` and live `WorkSchedule` on `ConstructionResult` and `PipelineOrchestrator` in `planalign_orchestrator/construction/builder.py`
- [X] T023 [US2] Capture every dbt invocation in execution order at the common runner boundary, with stage and year context, in `planalign_orchestrator/pipeline_orchestrator.py` and `planalign_orchestrator/construction/signature.py`
- [X] T024 [US2] Add idempotent start-record schema evolution and signature persistence to `planalign_orchestrator/run_metadata.py`; required provenance failures must propagate with correlation context rather than downgrade to informational logging
- [X] T025 [US2] Add the append-only terminal execution record and completion writer for finalized `invocation_count` and ordered schedule steps in `planalign_orchestrator/run_metadata.py`; never update final values onto the startup row
- [X] T026 [P] [US2] Set canonical entry-point values in product, parity, invariant, and performance callers and migrate `scripts/perf_profile/run_matrix.py` and `scripts/perf_profile/build_production_report.py` to consume the product-emitted signature
- [X] T027 [P] [US2] Surface start signatures and terminal schedules in parity/performance reporting under `scripts/perf_profile/`, preserving the distinction between wrapped runner calls and all dbt subprocess calls
- [X] T028 [US2] Run T019–T021 and capture the authoritative production schedule for the reference and Studio-realistic fixtures in `specs/120-unify-orchestrator-construction/work-schedule-baseline.md`; reconcile 38 wrapped calls versus 62 subprocess calls without treating either prior number as a gate

**Checkpoint**: SC-002 and FR-016 pass across all six entry points; #478 has an authoritative production schedule to optimize.

---

## Phase 5: User Story 3 — One Fail-Loud Fresh-Database Contract (Priority: P2)

**Goal**: Prove normal fresh-database behavior and explicit diagnostic self-healing both obey one attributable failure contract.

**Independent Test**: Forced critical initialization failure aborts with correlation context and zero authoritative outputs; normal fresh and pre-initialized runs match exactly.

### Tests first

- [X] T029 [P] [US3] Add a failing end-to-end forced-initialization-failure test in `tests/integration/test_initialization_contract.py` asserting abort, correlation/context/resolution details, and zero authoritative output rows
- [X] T030 [P] [US3] Add a fresh-versus-preinitialized parity test in `tests/integration/test_initialization_contract.py` using repository fixtures and explicit multiset columns

### Implementation and evidence

- [X] T031 [US3] Remove remaining self-healing initialization-hook registration and direct callers from `planalign_orchestrator/factory.py` and `planalign_orchestrator/pipeline/hooks.py`; preserve isolation for genuinely optional hooks and route explicit repair through the fail-loud executor from T008
- [X] T032 [US3] Run T029–T030 for CLI and batch isolated databases, document the single initialization contract and resolution guidance in `docs/guides/error_troubleshooting.md`, and record #467 closure evidence in `specs/120-unify-orchestrator-construction/initialization-evidence.md`

**Checkpoint**: No critical initialization failure is swallowed and no standard entry point installs implicit self-healing.

---

## Phase 6: User Story 4 — No Silently Ignored Execution Option (Priority: P3)

**Goal**: Unsupported execution-engine configuration is rejected consistently at validation.

**Independent Test**: Unsupported values fail before construction with a message naming the option; supported/unset values resolve identically through every entry point.

- [X] T033 [P] [US4] Add failing Pydantic and CLI tests in `tests/unit/config/test_execution_engine_validation.py` for supported, unset, and unsupported `optimization.execution_engine` values
- [X] T034 [US4] Implement Pydantic-v2 execution-engine validation in `planalign_orchestrator/config/` and reject unsupported values without silently defaulting
- [X] T035 [US4] Route engine validation through the canonical preflight in `planalign_orchestrator/construction/builder.py` and run T033 through representative CLI, batch, and Studio adapters

**Checkpoint**: Every accepted execution option is reachable and every unsupported value is rejected clearly.

---

## Phase 7: Polish and Cross-Cutting Validation

- [X] T036 [P] Remove temporary factory internals and migrate every direct-construction test site found by `rg` to the canonical seam with overrides; add a zero-match architectural assertion in `tests/unit/construction/test_no_direct_construction.py`
- [X] T037 [P] Update `CLAUDE.md`, README files, CLI help, `docs/`, and relevant feature specs to name the canonical seam; run and record a repository-wide `rg` audit proving no stale entry-point or execution-engine claim remains
- [X] T038 Run all six flows in `specs/120-unify-orchestrator-construction/quickstart.md` against isolated databases and confirm the shared development database SHA-256 is unchanged
- [X] T039 Run three repetitions of the deterministic 100,000-employee multi-year regression using `tests/fixtures/performance_census.py`, isolated databases, and `--threads 1`; verify median completion time and peak RSS increase by no more than 10% from T001 and document any regression and mitigation in `specs/120-unify-orchestrator-construction/performance-baseline.md`
- [X] T040 [P] Run `pytest -m fast` and confirm it remains under 10 seconds, run targeted/full integration suites with isolated `DATABASE_PATH`, and record constitution compliance in the PR review evidence — full suite 2,359 passed/4 expected skips; construction+config unit (24) and core integration (10: signature-matrix, provenance, initialization-contract, product-entrypoint parity, batch fresh-DB parity) re-verified green; ruff clean. Known pre-existing exception: `pytest -m fast` selects 1,700 tests (~125s), not <10s — a repo-wide marker/fixture cleanup tracked separately (not introduced by feature 120).
  - Functional gates passed: 1,700 fast tests and 2,359 full-suite tests passed. The existing 1,700-test fast marker takes 125.33s serially, so the constitution's `<10s` clause remains unmet and is documented in `review-evidence.md` rather than falsely closed.
- [X] T041 [P] Verify no setup TODO stubs remain in `planalign_orchestrator/construction/` and all tasks/tests use context-managed database access through `get_database_path()` where applicable
- [X] T042 Reproduce the deployed Feature 119 `run_execution_metadata` schema collision, evolve it in place without dropping historical fields or rows, and verify terminal schedule persistence against both a regression fixture and a disposable copy of a real scenario database
- [X] T043 Make Studio classify structured validation telemetry by record disposition rather than matching the rule's declared `severity: error`, with regression coverage for passed and failed records

---

## Dependencies and Delivery

- **Setup T001–T002** precedes behavioral changes so the pre-change performance envelope remains valid.
- **Foundational T003–T009** blocks every user story.
- **US1 T010–T018** establishes product-entry equivalence and is the MVP.
- **US2 T019–T028** follows US1 because it records the canonical production behavior and completes tooling-wide equality.
- **US3 T029–T032** relies on the explicit executor built in T008 but remains independently testable.
- **US4 T033–T035** can proceed after Foundational in parallel with US2/US3.
- **Polish T036–T043** follows all stories.

Parallel opportunities: T001/T002; T003/T004/T005; T010/T011/T012; T019/T020/T021; T029/T030; US4 alongside US2/US3; T036/T037/T040/T041.

## Guardrails

- Never validate into `dbt/simulation.duckdb`; hash it before and after behavioral validation.
- Compare authoritative outputs with bidirectional `EXCEPT ALL` over an explicit column list.
- Do not use 132 seconds, 38 wrapped calls, or 62 subprocess calls as acceptance thresholds until T028 reconciles the production schedule.
- Do not commit generated census, DuckDB files, or workspace data.
- Commit or publish changes only when explicitly requested by the user.
