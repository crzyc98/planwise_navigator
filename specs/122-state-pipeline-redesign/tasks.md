---
description: "Task list for Feature 122 — Normalize the Event & Workforce-State Pipeline"
---

# Tasks: Normalize the Event & Workforce-State Pipeline

**Input**: Design documents from `/specs/122-state-pipeline-redesign/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: REQUIRED. The feature specification mandates graph contracts, exact parity, failure semantics, determinism, and full-scale validation; Constitution III requires tests before implementation. Every behavioral change follows Red-Green-Refactor and uses an isolated database.

**Organization**: Frozen-baseline validation is foundational. Fresh run databases/latest-success reads are promoted to first-class US1 because they are a user-facing safety boundary. The remaining phases follow US2–US5 in priority order; within US3, each consumer migration has its own blocking full-scale checkpoint.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and does not depend on an incomplete task.
- **[Story]**: `[US1]` through `[US5]`; setup, foundational, and polish tasks have no story label.
- Every path is repository-relative. Behavioral runs must never target `dbt/simulation.duckdb`.

## Path Conventions

- Orchestrator/validation: `planalign_orchestrator/`, `planalign_cli/`, `scripts/perf_profile/`
- API/Studio: `planalign_api/`, `planalign_studio/`
- dbt: `dbt/models/` with commands run from `dbt/` and `--threads 1`
- Tests: `tests/unit/`, `tests/api/`, `tests/integration/`, `tests/fixtures/`
- Checked evidence/contracts: `specs/122-state-pipeline-redesign/`
- Ignored heavy evidence: `var/state_pipeline_validation/`

---

## Phase 1: Setup (Checked Fixtures and Evidence Layout)

**Purpose**: Lock the reviewable inventories and evidence format before baseline capture or product changes.

- [X] T001 Create the phase/checkpoint evidence ledger with baseline identity, pass/fail fields, isolated artifact locations, and approval rules in `specs/122-state-pipeline-redesign/phase-gates.md`.
- [X] T002 [P] Create the production-SQL graph fixture listing the expected event-candidate set, five ownership classes, mart inventory, and intentional audit sinks in `tests/fixtures/state_pipeline_graph_contract.yaml`.
- [X] T003 [P] Create PII-safe representative workforce-transition expectations derived only from `tests/fixtures/invariant_census.csv` in `tests/fixtures/state_pipeline_characterization.yaml`.
- [X] T004 [P] Audit the five relation-column exclusions against their dbt SQL definitions and finalize exact non-wildcard reasons in `specs/122-state-pipeline-redesign/contracts/parity-exclusions.yaml`.

**Checkpoint**: Checked fixtures define what is compared and what may be excluded; no product behavior has changed.

---

## Phase 2: Foundational — Frozen Parity Gate

**Purpose**: Establish trustworthy behavior comparison before changing run storage or the event/state graph.

**⚠️ CRITICAL**: No user-story implementation may begin until the frozen A+B baseline gate passes.

### Tests for the frozen-baseline validator (write first, must fail)

- [X] T005 [P] Add unit cases for exact schema order/type/nullability, one-sided missing relations, explicitly both-absent marts, bidirectional `EXCEPT ALL`, duplicate multiplicity, and exact relation-column exclusions in `tests/unit/test_change_validation.py`.
- [X] T006 [P] Add unit cases for typed characterization/phase records, canonical config and input fingerprints, baseline-ID continuity, ordered phase/checkpoint enforcement, unknown/duplicate exclusions, and PII/path rejection in `tests/unit/test_state_pipeline_validation.py`.
- [X] T007 [P] Add unit cases for code/dirty-tree, normalized config, census/seed, construction, DB, invocation, and per-node execution fingerprints in `tests/unit/test_state_pipeline_profile.py`.
- [X] T008 [P] Add an env-driven characterization regression that verifies a supplied A+B DB against the checked aggregate artifact without embedding paths or employee rows in `tests/integration/test_state_pipeline_characterization.py`.

### Implement the frozen-baseline validator

- [X] T009 Implement versioned Pydantic models, exclusion loading, characterization serialization, phase/checkpoint ordering, file guards, and PII-safe validation in `planalign_orchestrator/state_pipeline_validation.py`.
- [X] T010 Extend mart discovery/comparison to require exact schemas, distinguish one-sided and both-absent relations, apply relation-scoped exclusions, use bidirectional `EXCEPT ALL`, and report duplicate/event-transition metrics in `planalign_orchestrator/change_validation.py`.
- [X] T011 Wire explicit frozen `--baseline-db`, `--candidate-db`, `--characterization`, `--exclusions`, `--phase`, and optional `--checkpoint` inputs without changing the existing moving-HEAD mode in `planalign_cli/commands/validate_change.py` and `planalign_cli/main.py`.
- [X] T012 Implement canonical input/code/construction fingerprints and baseline/candidate labels in `scripts/perf_profile/profile_config.py`, `scripts/perf_profile/run_matrix.py`, and `scripts/perf_profile/dbt_timing.py`.
- [X] T013 Generate one clean 60,040-employee, 2025–2029 A+B database from revision `c6ad648` (or a verified equivalent) in a disposable git worktree, verify its metadata/fingerprints, and commit only aggregate output to `specs/122-state-pipeline-redesign/baseline-characterization.json`.
- [X] T014 Run `tests/integration/test_state_pipeline_characterization.py` against the ignored frozen DB, capture the shared-dev-DB signature, and record the passing `baseline_characterization` gate in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/baseline_characterization/gate.json`.

**Checkpoint**: A verified, PII-safe characterization points to one ignored frozen A+B reference and every later phase must use that baseline ID.

---

## Phase 3: User Story 1 — Safe Reruns Preserve Latest Successful Results (Priority: P1) 🎯 MVP

**Goal**: Give every managed single/batch attempt a fresh database, retain failed partial attempts, serve the latest success with explicit active-run warnings, promote success atomically, and preserve the two-second read target.

**Independent Test**: Hash a successful run and the shared DB, start a new run, verify every scenario read warns while result reads stay on the old success within the latency target, inject failure/cancellation without changing selection, then complete a third run and observe one atomic switch; repeat through managed batch execution.

### Tests for User Story 1 (write first, must fail)

- [x] T015 [P] [US1] Add atomic pointer tests covering canonical UUIDs, containment, completed-target validation, fsync/replace, failure immutability, corrupt-pointer fail-closed behavior, and no-pointer legacy behavior in `tests/unit/test_current_result.py`.
- [x] T016 [P] [US1] Extend resolver tests for pointer-selected DB/run ID, active-attempt context, legacy fallback only without a pointer, resolved-run config/year ownership, and traversal/integrity failures in `tests/unit/test_database_path_resolver.py`.
- [x] T017 [P] [US1] Add service tests for exclusive run-directory allocation, run-local CLI/database environment, success finalization order, failed/cancelled partial DB retention, no scenario/shared DB writes, and a sub-600-line facade seam in `tests/unit/simulation/test_simulation_service.py`.
- [x] T018 [P] [US1] Update archival/result tests to require in-place run finalization with no DB copy, atomic terminal metadata, run-local exports, and actual selected `run_id`/archived year range in `tests/unit/simulation/test_run_archiver.py`, `tests/unit/simulation/test_result_handlers.py`, and `tests/unit/simulation/test_results_reader.py`.
- [x] T019 [P] [US1] Add storage tests proving pointer helpers are atomic, automatic completion never prunes prior runs, explicit deletion handles the pointer target safely, and older run signatures remain unchanged in `tests/unit/storage/test_workspace_storage.py` and `tests/unit/storage/test_run_cleanup.py`.
- [x] T020 [P] [US1] Add an OpenAPI-derived inventory test covering every scenario-scoped GET/read plus cases for old-success bodies during a running attempt, `X-PlanAlign-Run-Warning`/`X-PlanAlign-Active-Run-Id`/`X-PlanAlign-Result-Run-Id`, no-success behavior, failure rollback, success switch, pointer integrity failure, CORS exposure, unchanged bodies, and pointer-selected export in `tests/api/test_scenario_read_consistency.py` and `tests/api/test_openapi_contract.py`.
- [x] T021 [P] [US1] Add batch-path tests proving `SimulationService` owns terminal status, a failed caught execution cannot be overwritten as completed, and every batch scenario receives a distinct run DB in `tests/api/test_batch_run_lifecycle.py`.
- [x] T022 [P] [US1] Add isolated end-to-end run lifecycle coverage plus idle/active representative read-latency checks (p95 ≤2 seconds) in `tests/integration/test_run_database_isolation.py` and `tests/performance/test_scenario_read_latency.py`, hashing prior successful/failed run artifacts and `dbt/simulation.duckdb` across running, injected failure, cancellation, rerun, and atomic promotion.

### Implement immutable run storage

- [x] T023 [US1] Implement typed `CurrentResultPointer` and `ResolvedScenarioReadContext`, atomic pointer publication/read validation, active-attempt context, and fail-closed integrity errors in `planalign_api/services/current_result.py`.
- [x] T024 [US1] Integrate current-result helpers, exclusive run allocation, explicit deletion semantics, and no automatic completion pruning in `planalign_api/storage/workspace_storage.py`.
- [x] T025 [US1] Update pointer-first resolution to return the selected run ID/config context while preserving legacy scenario/workspace/project fallback only when no pointer exists in `planalign_api/services/database_path_resolver.py`.
- [x] T026 [P] [US1] Extract process construction, environment/database-path injection, streaming, cancellation, and subprocess error handling from the oversized facade into `planalign_api/services/simulation/run_execution.py` with no behavior change outside the new seam.
- [x] T027 [US1] Make `SimulationService` allocate/use a never-before-used run-local DB, finalize authoritative artifacts before promotion, leave the pointer untouched on failure/cancellation, and remain below approximately 600 lines in `planalign_api/services/simulation/service.py`.
- [x] T028 [US1] Finalize already-run-local archives without copying a scenario DB, retain failed DBs, perform atomic terminal metadata writes, and select the resolved run for exports in `planalign_api/services/simulation/run_archiver.py` and `planalign_api/services/simulation/result_handlers.py`.
- [x] T029 [US1] Return the resolver-selected run ID and derive years/config from that run rather than current scenario config in `planalign_api/services/simulation/results_reader.py`, `planalign_api/services/analytics_service.py`, `planalign_api/services/comparison_service.py`, `planalign_api/services/config_diff_service.py`, `planalign_api/services/timeline_service.py`, `planalign_api/services/vesting_service.py`, `planalign_api/services/winners_losers_service.py`, and `planalign_api/services/ndt_service.py`.
- [x] T030 [US1] Make `SimulationService` the single terminal-status authority for batch attempts and propagate its actual outcome in `planalign_api/routers/batch.py`.
- [x] T031 [US1] Implement shared scenario-read warning/header aggregation in `planalign_api/services/scenario_read_warning.py` and `planalign_api/main.py`; supply multi-scenario context from `planalign_api/routers/simulations.py`, `planalign_api/routers/scenarios.py`, `planalign_api/routers/analytics.py`, `planalign_api/routers/comparison.py`, `planalign_api/routers/ndt.py`, `planalign_api/routers/timeline.py`, and `planalign_api/routers/vesting.py`, and make the OpenAPI-derived inventory fail any uncovered scenario read without mutating response bodies or attempt status.
- [x] T032 [US1] Expose the three run-consistency headers through CORS and the generated API contract in `planalign_api/main.py`, `tests/api/snapshots/openapi_schema.json`, and `specs/122-state-pipeline-redesign/contracts/scenario-read-consistency.yaml`.
- [x] T033 [P] [US1] Add centralized header interception and a deduplicated global in-progress banner without per-route response changes in `planalign_studio/services/api.ts` and `planalign_studio/components/Layout.tsx`.
- [x] T034 [US1] Run the focused API/unit/integration suites and `tests/performance/test_scenario_read_latency.py` against fresh isolated paths, require idle and active-run p95 reads ≤2 seconds, build the Studio, and record the passing `run_database_isolation` gate in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/run_database_isolation/gate.json`.

**Checkpoint**: US1 is independently shippable—every managed attempt is isolated from first write, latest-success reads and warnings work within the latency target, and no event/state behavior has changed.

---

## Phase 4: User Story 2 — Immutable Facts Published Exactly Once (Priority: P2)

**Goal**: Assemble the active SQL candidates once, publish `fct_yearly_events` once per year, and stop STATE_ACCUMULATION from rebuilding it while preserving every mart exactly.

**Independent Test**: A fresh isolated 60,040-employee, 2025–2029 run executes `fct_yearly_events` and `fct_workforce_snapshot` once per effective year; no current-year candidate reads the current-year fact; every built mart, event count, schema, ID/sequence, and duplicate multiplicity matches the frozen A+B DB.

### Tests for User Story 2 (write first, must fail)

- [x] T035 [P] [US2] Add manifest/workflow tests for the exact active SQL candidate set, no current-year fact ancestry, one execution of each publication node from `run_results.json`, and absence of `fct_yearly_events` from STATE_ACCUMULATION in `tests/unit/orchestrator/test_pipeline_graph_contract.py`.
- [x] T036 [P] [US2] Add an env-driven full-scale event-publication test for exact mart schemas/content, grouped event counts, deterministic IDs/sequences, and duplicate multiplicity in `tests/integration/test_state_pipeline_parity.py`.
- [x] T037 [P] [US2] Add dbt contracts for current-year assembly scope/completeness and unchanged event/snapshot publication grains in `dbt/models/intermediate/schema.yml` and `dbt/models/marts/schema.yml`.

### Implementation for User Story 2

- [x] T038 [US2] Extract the active SQL union and deterministic sequencing projection from the fact into `dbt/models/intermediate/int_current_year_events.sql`, preserving the exact accepted candidate columns, casts, IDs, ordering, and duplicate behavior.
- [x] T039 [US2] Make `dbt/models/marts/fct_yearly_events.sql` a thin incremental publisher of `int_current_year_events` with the existing schema and scenario/plan/year partition replacement semantics; leave inactive Polars compatibility remnants untouched unless surgically required for active SQL compilation.
- [x] T040 [US2] Remove the second event-fact build from normal and calibration STATE_ACCUMULATION schedules while preserving standard and sharded single-publication behavior in `planalign_orchestrator/pipeline/workflow.py` and `planalign_orchestrator/pipeline/event_generation_executor.py`.
- [x] T041 [US2] Run the dbt contracts and node-execution assertions on an isolated multi-year candidate, confirming the active production manifest neither selects nor requires legacy Polars execution; record targeted evidence in `var/state_pipeline_validation/event_publication/targeted.json`.
- [x] T042 [US2] Run the complete 60,040-employee, 2025–2029 frozen-baseline gate and record `event_publication` only after exact all-mart parity, event counts, duplicate metrics, file guards, and per-node publication counts pass in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/event_publication/gate.json`.

**Checkpoint**: US2 is independently shippable—immutable facts publish once per year in each fresh run DB, with accepted outputs unchanged. Do not begin consumer migration if T042 fails.

---

## Phase 5: User Story 3 — One Authoritative Workforce-State Relation (Priority: P3)

**Goal**: Prove a workforce-only accumulator in shadow, establish a strict prior-year projection, migrate each benefit consumer separately, compose the public snapshot, and remove both redundant state relations only after parity.

**Independent Test**: For every 2025–2029 employee/year, the shadow workforce projection matches accepted workforce columns; each migrated consumer preserves exact marts; the final snapshot is a composition rather than event replay; removed models have zero manifest/workflow consumers.

### Tests for User Story 3 (write first, must fail)

- [x] T043 [P] [US3] Add dbt/manifest contracts for the four-column workforce key, no hard-coded scope, workforce-only schema, first-year behavior, strict N-1 self-read, and explicit separation of workforce/enrollment/deferral state with no all-purpose relation in `dbt/models/intermediate/schema.yml` and `tests/unit/orchestrator/test_pipeline_graph_contract.py`.
- [x] T044 [P] [US3] Add explicit enrollment-projection contracts for earlier-year-only/non-authoritative behavior plus workforce-projection tests for first-year empty state, N-1-only rows, scenario/plan containment, deterministic rebuilds, and closed connections in `tests/unit/orchestrator/test_enrollment_projection.py` and `tests/unit/orchestrator/test_workforce_state_projection.py`.
- [x] T045 [P] [US3] Add env-driven per-year/per-column shadow comparison and representative synthetic transition assertions in `tests/integration/test_workforce_state_shadow_parity.py`.
- [x] T046 [P] [US3] Add consumer and snapshot parity cases that localize eligibility, employee contribution, employer core, match, proration, and composition differences in `tests/integration/test_state_pipeline_parity.py`.

### Shadow accumulator and prior-year boundary

- [x] T047 [US3] Implement incremental `int_workforce_state_accumulator` from census/prior self-state plus current workforce events, keyed by scenario/plan/employee/year and containing only the fields in `data-model.md`, in `dbt/models/intermediate/int_workforce_state_accumulator.sql` and `dbt/models/intermediate/schema.yml`.
- [x] T048 [US3] Add the accumulator as a shadow STATE_ACCUMULATION node without changing any production consumer or removing any command boundary in `planalign_orchestrator/pipeline/workflow.py`.
- [x] T049 [US3] Run the full shadow comparison for all 60,040 employees and years 2025–2029; block on any column/year divergence and record `shadow_workforce/accumulator` evidence in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/shadow_workforce/accumulator/gate.json`.
- [x] T050 [US3] Implement a disposable, strictly-prior `workforce_state_projection` with typed lifecycle/cleanup in `planalign_orchestrator/workforce_state_projection.py`, declare it in `dbt/models/sources.yml`, and build it before foundation/event generation in `planalign_orchestrator/pipeline_orchestrator.py`.
- [x] T051 [US3] Replace prior-snapshot dynamic relation lookups with the declared projection source in `dbt/models/intermediate/int_active_employees_prev_year_snapshot.sql`, `dbt/models/intermediate/int_prev_year_workforce_summary.sql`, and `dbt/models/intermediate/int_prev_year_workforce_by_level.sql`.
- [x] T052 [US3] Run the full frozen-baseline gate after projection migration and record `shadow_workforce/projection` evidence in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/shadow_workforce/projection/gate.json`.

### Migrate benefit consumers one at a time

- [x] T053 [US3] Repoint employer eligibility to canonical workforce state without changing eligibility semantics in `dbt/models/intermediate/int_employer_eligibility.sql`, then run and record the full gate at `var/state_pipeline_validation/consumers_migrated/employer_eligibility/gate.json` before continuing.
- [x] T054 [US3] Repoint employee contributions to workforce, enrollment, and deferral state while removing independent workforce/proration replay in `dbt/models/intermediate/events/int_employee_contributions.sql`, then run and record the full gate at `var/state_pipeline_validation/consumers_migrated/employee_contributions/gate.json`.
- [x] T055 [US3] Repoint employer core to workforce state plus employer eligibility while removing duplicated status/tenure/age/proration replay in `dbt/models/intermediate/int_employer_core_contributions.sql`, then run and record the full gate at `var/state_pipeline_validation/consumers_migrated/employer_core/gate.json`.
- [x] T056 [US3] Repoint employee match to workforce state, contributions, and employer eligibility without changing match semantics in `dbt/models/intermediate/events/int_employee_match_calculations.sql`, then run and record the full gate at `var/state_pipeline_validation/consumers_migrated/employee_match/gate.json`.
- [x] T057 [US3] Run the aggregate consumer parity/invariant suite and publish the passing `consumers_migrated` gate in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/consumers_migrated/gate.json`.

### Compose the snapshot and remove redundant state

- [x] T058 [US3] Rewrite `dbt/models/marts/fct_workforce_snapshot.sql` as a schema-identical composition of canonical workforce, enrollment, deferral, contribution, core, and match relations with no independent workforce-event replay.
- [x] T059 [US3] Run exact full-scale snapshot/all-mart parity before deleting legacy state and record `snapshot_composed_legacy_removed/composed` evidence in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/snapshot_composed_legacy_removed/composed/gate.json`.
- [x] T060 [US3] Remove `dbt/models/intermediate/int_employee_state_by_year.sql` and `dbt/models/intermediate/int_workforce_snapshot_optimized.sql`; remove their schema entries and normal/calibration selections in `dbt/models/intermediate/schema.yml` and `planalign_orchestrator/pipeline/workflow.py` only after manifest audits show zero consumers.
- [x] T061 [US3] Run full-scale parity plus explicit enrollment-projection/domain-separation contracts, Feature 107 enrollment reconstruction, and Feature 112 post-termination integrity, then publish `snapshot_composed_legacy_removed` in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/snapshot_composed_legacy_removed/gate.json`.

**Checkpoint**: US3 is complete—one workforce-only accumulator is authoritative, enrollment and deferral remain separately authoritative, the enrollment projection remains disposable/prior-only, every benefit consumer uses authoritative state, and redundant relations are gone with full-scale proof.

---

## Phase 6: User Story 4 — Machine-Verifiable Dependency Order and Ownership (Priority: P4)

**Goal**: Make current-year order, stage ownership, candidate completeness, temporal exceptions, and audit sinks enforceable from the compiled production manifest and workflow.

**Independent Test**: Graph-contract tests pass on normal and calibration workflows with no current-year fact feedback, hidden temporal lookup, ownership overlap, manual event exclusions, missing candidate, dependency gap, or undocumented staged sink.

### Tests for User Story 4 (write first, must fail)

- [x] T062 [P] [US4] Complete manifest tests for transitive current-year ancestry, exact candidate coverage, accumulator/projection-only temporal escape hatches, and no dynamic snapshot lookup in `tests/unit/orchestrator/test_pipeline_graph_contract.py`.
- [x] T063 [P] [US4] Add tests for mutually exclusive ownership tags, no executor manual exclusions, and every staged node having a model consumer or checked audit-sink exemption in `tests/unit/orchestrator/test_pipeline_stage_ownership.py`.
- [x] T064 [P] [US4] Add normal/calibration workflow closure tests proving removed models are absent and every selected dependency is prepublished or inside its selection, plus calibration output/failure regression coverage without a new run-publication lifecycle, in `tests/unit/orchestrator/test_workflow_graph_contract.py` and `tests/test_calibration_workflow.py`.

### Implementation for User Story 4

- [x] T065 [US4] Configure distinct `EVENT_CANDIDATE`, `EVENT_PUBLICATION`, `DOMAIN_STATE`, `BENEFIT_CALCULATION`, and `SNAPSHOT_PUBLICATION` ownership in `dbt/dbt_project.yml`, `dbt/models/intermediate/int_current_year_events.sql`, `dbt/models/intermediate/int_workforce_state_accumulator.sql`, `dbt/models/intermediate/int_employer_eligibility.sql`, `dbt/models/intermediate/int_employer_core_contributions.sql`, `dbt/models/marts/fct_yearly_events.sql`, `dbt/models/marts/fct_employer_match_events.sql`, and `dbt/models/marts/fct_workforce_snapshot.sql`, preserving the six top-level orchestration stages.
- [x] T066 [US4] Relocate contribution and match models from `dbt/models/intermediate/events/` to `dbt/models/intermediate/`, move their schema declarations from `dbt/models/intermediate/events/schema.yml` to `dbt/models/intermediate/schema.yml`, and preserve relation names while removing inherited event ownership.
- [x] T067 [US4] Remove manual contribution/match excludes and select the ownership-complete active SQL graph in `planalign_orchestrator/pipeline/event_generation_executor.py`.
- [x] T068 [US4] Encode intentional publication/audit sinks and stage model constants from the checked fixture in `planalign_core/constants.py` and `tests/fixtures/state_pipeline_graph_contract.yaml`, rejecting any unlisted orphan.
- [x] T069 [US4] Compile the production-SQL manifest, run all graph contracts, calibration output/failure regressions, and a full-scale frozen-baseline simulation candidate, then record `snapshot_composed_legacy_removed/graph_contract` evidence in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/snapshot_composed_legacy_removed/graph_contract/gate.json`.

**Checkpoint**: US4 is complete—the normal and calibration graphs describe execution order, calibration compatibility remains green, and automated contracts prevent hidden cycles, ownership drift, incomplete candidate sets, and orphaned staged models.

---

## Phase 7: User Story 5 — One STATE_ACCUMULATION Invocation (Priority: P5)

**Goal**: Collapse the now-normalized state stage to one invocation per year with no command-level full-refresh exception while preserving diagnostics, partial failure state, exact behavior, and resource limits.

**Independent Test**: A full isolated 2025–2029 run records one STATE_ACCUMULATION command per year, no state `--full-refresh`, exactly one publication execution per fact/year, correct injected failure attribution, exact all-mart parity, and median peak RSS within 10% of A+B.

### Tests for User Story 5 (write first, must fail)

- [x] T070 [P] [US5] Update schedule tests to require one dependency-closed STATE_ACCUMULATION command per year and no state-stage full-refresh group/flag; capture the whole-run invocation total as reported evidence without asserting 20 or any other fixed total in `tests/unit/test_stage_invocation_grouping.py` and `tests/unit/orchestrator/test_year_executor.py`.
- [x] T071 [P] [US5] Extend injected-failure tests to require failing model/stage/year/correlation context and retained partial outputs in the failed run DB under the consolidated selection in `tests/integration/test_batched_failure_attribution.py` and `tests/unit/orchestrator/test_pipeline_stage_failure.py`.
- [x] T072 [P] [US5] Add consolidated-schedule assertions for node execution counts, invocation metadata, rerun isolation, and no later event-fact rebuild while treating the aggregate invocation total as observational evidence in `tests/integration/test_state_pipeline_parity.py` and `tests/integration/test_run_database_isolation.py`.

### Implementation for User Story 5

- [x] T073 [US5] Extract optional parallel/legacy stage strategies from the oversized executor into `planalign_orchestrator/pipeline/stage_execution_strategies.py`, preserving behavior and bringing `planalign_orchestrator/pipeline/year_executor.py` below approximately 600 lines before schedule changes.
- [x] T074 [US5] Remove the scratch-snapshot full-refresh exception/grouping and execute the normalized STATE_ACCUMULATION selection once per year in `planalign_orchestrator/pipeline/year_executor.py` and `planalign_orchestrator/pipeline/workflow.py`.
- [x] T075 [US5] Run targeted schedule, failure-attribution, partial-failure, cancellation, stale-rerun, determinism, Feature 107, Feature 112, and calibration compatibility suites against fresh isolated DBs and store outcomes in `var/state_pipeline_validation/state_stage_consolidated/regressions.json`.
- [x] T076 [US5] Run the authoritative 60,040-employee, 2025–2029 candidate against the frozen A+B DB and require exact schema/content/count/duplicate parity, shared/prior-run file guards, one state invocation/year, and no state full-refresh while only recording the aggregate invocation total in `var/state_pipeline_validation/state_stage_consolidated/parity.json`.
- [x] T077 [US5] Run at least three warm baseline and candidate repetitions for both reference and Studio workloads, capture wall/CPU/model/dbt/residue time and node/invocation counts, and enforce candidate median peak RSS ≤110% of baseline using `scripts/perf_profile/run_matrix.py` and `var/state_pipeline_validation/state_stage_consolidated/performance.json`.
- [x] T078 [US5] Publish the final `state_stage_consolidated` decision, including the measured schedule and aggregate invocation total as non-gating evidence, in `specs/122-state-pipeline-redesign/phase-gates.md` and `var/state_pipeline_validation/state_stage_consolidated/gate.json`; do not ship consolidation if T075–T077 fail.

**Checkpoint**: US5 is complete—the simpler schedule is a proven consequence of the normalized DAG, and the observed whole-run invocation total was never used to force it.

---

## Phase 8: Polish, Full Regression, and Handoff

**Purpose**: Validate the whole feature, documentation, module boundaries, and user-visible warning surface.

- [x] T079 [P] Run `pytest -m fast`, the targeted API/unit suites, and all Feature 122 tests; record duration/coverage and keep the fast suite under the constitutional target in `specs/122-state-pipeline-redesign/phase-gates.md`.
- [x] T080 [P] Run `ruff check` plus `mypy planalign_orchestrator/ planalign_cli/ planalign_core/ planalign_api/ --ignore-missing-imports`, verify touched Python modules stay within complexity/parameter/module-size limits, and record results in `specs/122-state-pipeline-redesign/phase-gates.md`.
- [x] T081 [P] Build the Studio with `planalign_studio/package.json`, verify the global warning banner against the API contract, and confirm OpenAPI snapshot stability in `specs/122-state-pipeline-redesign/phase-gates.md`.
- [x] T082 Execute `specs/122-state-pipeline-redesign/quickstart.md` end to end using newly allocated isolated paths; verify `dbt/simulation.duckdb` and every pre-existing run/archive signature are unchanged and record the final acceptance matrix in `specs/122-state-pipeline-redesign/phase-gates.md`.
- [x] T083 [P] Publish the before/after DAG, schedule, resource evidence, compatibility notes, and explicit SQL-only/legacy-Polars non-goal in `docs/perf/state-pipeline-redesign.md` and `CHANGELOG.md` without including PII-bearing paths or golden data.

**Checkpoint**: Feature 122 is ready for review with complete checked contracts and ignored reproducible evidence; no shared or historical database was used as a validation target.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; begin immediately.
- **Foundational (Phase 2)**: Depends on Setup. T005–T014 establish the frozen baseline and block every user story.
- **US1 (Phase 3)**: Depends on the foundation. It establishes safe fresh managed attempts/latest-success reads and is the first independently shippable increment.
- **US2 (Phase 4)**: Depends on the passing US1 `run_database_isolation` gate and delivers the `event_publication` gate.
- **US3 (Phase 5)**: Depends on US2. Its internal order is strict: shadow accumulator → full gate → prior projection → full gate → one consumer plus full gate at a time → snapshot composition gate → deletion → final gate.
- **US4 (Phase 6)**: Depends on US3 because the final graph/ownership and calibration contracts require the canonical state, migrated consumers, composed snapshot, and removed legacy relations.
- **US5 (Phase 7)**: Depends on US4. The command boundary is removed only after the normalized normal/calibration graph is machine-verifiable and full-scale clean.
- **Polish (Phase 8)**: Depends on all desired user stories and final phase gates.

### User Story Dependencies

- **US1 (P1)**: No dependency on another user story after the frozen baseline; independently testable and the suggested MVP.
- **US2 (P2)**: Requires US1's fresh managed-run isolation so every parity candidate is rebuilt safely.
- **US3 (P3)**: Requires US2's single immutable event publication as stable accumulator input.
- **US4 (P4)**: Requires US3's canonical accumulator/projection and completed consumer migration to express the final graph and calibration selections.
- **US5 (P5)**: Requires US4's dependency-closed graph; it cannot be attempted safely earlier.

### Within Every Behavioral Checkpoint

1. Write the named tests and confirm they fail for the intended reason.
2. Implement only the scoped change.
3. Run targeted tests on a new isolated DB.
4. Run the full 60,040-employee, 2025–2029 gate against the same frozen baseline where required.
5. Verify shared/prior-run signatures and baseline ID.
6. Record the gate before starting the next migration.

### Parallel Opportunities

- Setup: T002–T004 can run in parallel after T001 defines the evidence ledger.
- Foundational validation: T005–T008 can run in parallel; T009–T012 affect separate modules after those tests are red.
- US1: T015–T022 can be authored in parallel after T014 freezes the baseline. T026 and T033 can proceed in parallel with pointer/storage implementation because they touch isolated API/Studio seams.
- US2: T035–T037 can be written in parallel before T038–T040.
- US3: T043–T046 can be written in parallel. Consumer implementations are intentionally sequential because each requires a full gate.
- US4: T062–T064 can be written in parallel before ownership changes.
- US5: T070–T072 can be written in parallel before executor extraction/consolidation.
- Polish: T079–T081 and T083 can run in parallel; T082 is the final serial acceptance pass.

---

## Parallel Example: User Story 1

```text
Task T015: "Write atomic current-result pointer tests"
Task T020: "Write exhaustive scenario-read warning/header contracts"
Task T022: "Write isolated run lifecycle and representative read-latency checks"
```

## Parallel Example: User Story 2

```text
Task T035: "Write manifest/workflow publication contracts"
Task T036: "Write full-scale event publication parity"
Task T037: "Write dbt assembly/publication contracts"
```

## Parallel Example: User Story 3

```text
Task T043: "Write workforce/domain-separation contracts"
Task T044: "Write enrollment and workforce projection contracts"
Task T045: "Write per-year shadow state parity"
Task T046: "Write localized benefit/snapshot parity"
```

## Parallel Example: User Story 4

```text
Task T062: "Write ancestry and temporal-boundary graph tests"
Task T063: "Write ownership and audit-sink tests"
Task T064: "Write normal/calibration dependency and regression contracts"
```

## Parallel Example: User Story 5

```text
Task T070: "Write one-command/no-full-refresh schedule tests"
Task T071: "Write consolidated failure-attribution tests"
Task T072: "Write node-count evidence and rerun-isolation assertions"
```

---

## Implementation Strategy

### MVP First: Foundation + User Story 1

1. Complete Phase 1 checked fixtures.
2. Complete Phase 2 frozen baseline.
3. Complete Phase 3 fresh managed-run isolation/latest-success reads.
4. Stop and validate US1 independently, including idle/active read latency.

This MVP prevents reruns from disturbing prior results, preserves failure artifacts, exposes active-run warnings, and atomically promotes success without taking on the pipeline redesign.

### Incremental Delivery

1. **Foundation** → trusted frozen parity.
2. **US1** → isolated managed attempts, latest-success reads, warnings, atomic promotion, and latency gate.
3. **US2** → events publish once; full gate.
4. **US3 shadow** → prove canonical workforce state and explicit domain/projection contracts before consumers.
5. **US3 consumers** → move one consumer, run one full gate, repeat.
6. **US3 snapshot/removal** → compose, prove, remove, prove again.
7. **US4** → enforce normalized normal/calibration graphs and clean ownership.
8. **US5** → consolidate only after every semantic guard passes; report total invocations without an exact-count gate.
9. **Polish** → full suites, performance, quickstart, and handoff.

### Stop Rules

- Any shadow divergence blocks consumer migration.
- Any consumer parity failure keeps that consumer on its prior implementation.
- Any unlisted schema/content/count/duplicate difference fails the phase.
- Any pointer/file-guard failure blocks all pipeline work.
- Any idle or active-run p95 read latency above two seconds blocks US1.
- Any calibration dependency/output/failure regression blocks US4 and therefore US5.
- Any final RSS regression above 10% or diagnostics regression prevents STATE_ACCUMULATION consolidation from shipping.
- Invocation count is reported from evidence; it is never used to waive a semantic gate.

---

## Notes

- `[P]` means different files and no dependency on an unfinished task; it does not permit parallel writes to the same DuckDB.
- Full-scale gates are intentionally serial and always use the same verified A+B baseline.
- Heavy DBs, configs, census paths, logs, and machine gate JSON remain ignored; only aggregate PII-safe evidence is checked in.
- Direct CLI behavior remains caller-managed; fresh run directories are the Studio/API single and batch contract.
- Existing response bodies remain compatible; only the documented warning/result headers are additive.
- Deprecated Polars remnants are not restored or broadly cleaned up.
- Do not commit or create branches unless explicitly requested by the maintainer.
