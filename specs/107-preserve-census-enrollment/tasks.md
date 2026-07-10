# Tasks: Preserve Census Enrollment

**Input**: Design documents from `/specs/107-preserve-census-enrollment/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required by FR-011, FR-012, Constitution Principle III, and the performance/scalability constitution gates. Write each listed test before its production change and confirm the expected failure.

**Organization**: Shared event-authority, projection, reset, and timing infrastructure is Foundational. Each user story then has independent tests and checkpoints.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: May run in parallel because it changes a different file and has no incomplete dependency.
- **[Story]**: Maps tasks to US1, US2, or US3.
- Every task includes exact file paths.

## Phase 1: Setup (Shared Test Infrastructure)

**Purpose**: Provide isolated deterministic scenario fixtures and set-wise enterprise-scale inputs.

- [ ] T001 Create reusable two-scenario, two-plan, fixed-seed census/config/database fixtures plus set-wise 100K employee and 200K history generators in tests/fixtures/census_enrollment.py
- [ ] T002 Export the feature fixtures for pytest discovery in tests/fixtures/__init__.py and tests/conftest.py

---

## Phase 2: Foundational (Blocking Event Authority and Execution Safety)

**Purpose**: Establish safe reset semantics, a fact-authoritative cycle-breaking projection, pre-event validation, declared dbt dependencies, and enforceable performance tooling.

**⚠️ CRITICAL**: No user-story implementation begins until this phase passes.

### Tests First

- [ ] T003 [P] Add failing omitted-mode and explicit one-time reset tests in tests/unit/orchestrator/test_cleanup_scoping.py
- [ ] T004 [P] Add failing start-year-only FOUNDATION and no-mid-run-temporal-refresh command tests in tests/unit/orchestrator/test_year_executor.py
- [ ] T005 [P] Add failing baseline replay, fact precedence, deterministic tie-break, prior-year cutoff, scenario/plan scope, atomic retry, uniqueness, and reconciliation tests in tests/unit/orchestrator/test_enrollment_projection.py
- [X] T006 [P] Add failing tests proving dependency validation and projection rebuild occur after FOUNDATION but before every SQL/hybrid EVENT_GENERATION path, with failure preventing event execution and preserving diagnostic context, in tests/unit/orchestrator/test_pipeline.py
- [X] T007 [P] Add a failing 100K employee/200K history projection test with exact row-count, uniqueness, <=30-second, <=1,024-MiB RSS, <=15% runtime-regression, and <=20% RSS-regression assertions in tests/performance/test_census_enrollment_performance.py
- [X] T008 [P] Add failing subprocess timeout, nonzero exit, and successful-under-budget tests for the 10-second fast-suite gate in tests/unit/scripts/test_check_fast_suite_runtime.py

### Implementation

- [X] T009 [P] Resolve omitted clear mode to year-scoped cleanup while preserving explicit one-time `all` reset behavior in planalign_orchestrator/pipeline/state_manager.py
- [X] T010 [P] Make FOUNDATION full refresh start-year-only, prevent global temporal refresh after the start year, and retain safe model-specific exceptions in planalign_orchestrator/pipeline/year_executor.py
- [ ] T011 Implement atomic `enrollment_decision_projection` rebuild from int_baseline_workforce plus prior scenario/plan-scoped fct_yearly_events, including deterministic replay, fact provenance, reconciliation, and structured failures, in planalign_orchestrator/pipeline/enrollment_projection.py
- [X] T012 [P] Declare the projection source and create the explicit-column, current-context staging boundary in dbt/models/sources.yml, dbt/models/staging/stg_prior_enrollment_state.sql, and dbt/models/staging/schema.yml
- [X] T013 Invoke prior-year validation and projection rebuild after FOUNDATION and before all event-generation paths, and retain STATE_ACCUMULATION validation as defense, in planalign_orchestrator/pipeline_orchestrator.py and planalign_orchestrator/pipeline/year_executor.py
- [X] T014 Remove self-history and raw accumulator reads by making all enrollment decision paths use `ref('stg_prior_enrollment_state')` in dbt/models/intermediate/int_enrollment_events.sql, dbt/models/intermediate/int_voluntary_enrollment_decision.sql, and dbt/models/intermediate/int_proactive_voluntary_enrollment.sql
- [ ] T015 Document and test the shared projection lineage and input contract in dbt/models/intermediate/schema.yml and dbt/models/staging/schema.yml
- [X] T016 Implement the hard timeout wrapper with `--max-seconds` and child exit-code propagation in scripts/check_fast_suite_runtime.py
- [X] T017 Run the complete Foundational unit slice and `dbt compile --select stg_prior_enrollment_state int_enrollment_events int_voluntary_enrollment_decision int_proactive_voluntary_enrollment --threads 1` from dbt/, following specs/107-preserve-census-enrollment/quickstart.md

**Checkpoint**: Census plus prior immutable facts are the only projection inputs; every enrollment path uses the declared staging ref; failures stop before event generation; reset and timing controls pass.

---

## Phase 3: User Story 1 - Preserve Existing Participation (Priority: P1) 🎯 MVP

**Goal**: Protect census-enrolled participants from year-two duplicate enrollment, new-enrollee opt-out, and default-rate replacement.

**Independent Test**: The isolated broad-auto-enrollment scenario keeps the census participant enrolled at 5%, emits no year-two enrollment, and emits no resulting opt-out unless an authoritative prior fact legitimately changed status.

### Tests First

- [ ] T018 [P] [US1] Add failing isolated assertions for zero duplicate enrollment, zero same-year auto-enrollment opt-out, retained status, retained 5% rate, and fact-event-over-census precedence in tests/integration/test_census_enrollment_persistence.py
- [ ] T019 [P] [US1] Add a failing invariant excluding census participants from year-two enrollment when no authoritative intervening status fact permits re-enrollment in dbt/tests/test_census_participants_not_reenrolled.sql

### Implementation

- [ ] T020 [US1] Apply projected `is_enrolled`, `ever_opted_out`, enrollment date, rate, and fact provenance to existing-participant exclusion and opt-out eligibility in dbt/models/intermediate/int_enrollment_events.sql
- [ ] T021 [US1] Run the US1 integration assertions and `test_census_participants_not_reenrolled` selector against the isolated two-year database using specs/107-preserve-census-enrollment/quickstart.md

**Checkpoint**: US1 passes independently after Foundational work; census participation changes only when an authoritative prior fact supports it.

---

## Phase 4: User Story 2 - Preserve Correct Enrollment Decisions (Priority: P2)

**Goal**: Preserve applicable auto/voluntary opportunities for genuinely unenrolled employees without including existing participants.

**Independent Test**: Enabled and disabled configurations keep the never-enrolled control in the correct eligible population and the census participant out; an emitted event is required only when the fixture probability is `1.0`.

### Tests First

- [ ] T022 [P] [US2] Add failing enabled/disabled eligibility-population assertions and deterministic-probability-1.0 event assertions in tests/integration/test_census_enrollment_persistence.py
- [ ] T023 [P] [US2] Add a failing invariant that tests eligible decision-population membership rather than stochastic event occurrence in dbt/tests/test_enrollment_population_split.sql

### Implementation

- [ ] T024 [US2] Update auto, voluntary, and proactive eligibility filters to consume projected current status and opt-out history while preserving genuinely unenrolled controls in dbt/models/intermediate/int_enrollment_events.sql, dbt/models/intermediate/int_voluntary_enrollment_decision.sql, and dbt/models/intermediate/int_proactive_voluntary_enrollment.sql
- [ ] T025 [US2] Run the enabled/disabled integration variants and `test_enrollment_population_split` selector using specs/107-preserve-census-enrollment/quickstart.md

**Checkpoint**: US2 passes independently after Foundational work; eligibility is deterministic and event realization is tested only under forced probability.

---

## Phase 5: User Story 3 - Retain Auditable Multi-Year State (Priority: P3)

**Goal**: Retain every completed year, prove scenario/run isolation, reproduce fixed-seed outcomes, and trace participant lineage in under five minutes.

**Independent Test**: Two isolated scenario/plan runs retain their own yearly state and facts without mutation or leakage; a sampled participant reconciles census, facts, projection, accumulator, and snapshot in <300 seconds; repeated fixed-seed results match.

### Tests First

- [ ] T026 [P] [US3] Add failing completed-year compensation-history and diagnostic-context tests in tests/unit/orchestrator/test_stage_validator.py
- [ ] T027 [US3] Add failing retained-year, accumulator continuity, and fixed-seed enrollment fingerprint assertions in tests/integration/test_census_enrollment_persistence.py
- [ ] T028 [US3] Add failing two-database scenario/plan identity assertions and verify run B leaves run A checksums and row counts unchanged in tests/integration/test_census_enrollment_persistence.py
- [ ] T029 [US3] Add a failing monotonic-time participant trace that reconciles census, authoritative facts, projection provenance, accumulator, and snapshot in <300 seconds in tests/integration/test_census_enrollment_persistence.py
- [ ] T030 [P] [US3] Add a failing invariant for missing start-to-current years in compensation and required accumulators in dbt/tests/test_multi_year_state_history_retained.sql
- [ ] T031 [P] [US3] Add failing EVENT_GENERATION fail-fast coverage for a missing prior year in tests/integration/test_year_dependency_validation.py

### Implementation

- [ ] T032 [US3] Validate and log retained start/current compensation counts plus projection reconciliation context during FOUNDATION/event-boundary validation in planalign_orchestrator/pipeline/stage_validator.py and planalign_orchestrator/pipeline/enrollment_projection.py
- [ ] T033 [US3] Run US3 unit/integration tests and `test_multi_year_state_history_retained`, `test_enrollment_continuity`, and `test_enrollment_architecture` selectors using specs/107-preserve-census-enrollment/quickstart.md

**Checkpoint**: US3 passes independently; retained history, authoritative lineage, isolation, reproducibility, fail-closed behavior, and the <300-second audit outcome are proven.

---

## Phase 6: Performance, Documentation, and Cross-Cutting Validation

**Purpose**: Enforce constitutional scale/timing gates and complete operational guidance.

- [X] T034 Execute the 100K/200K-row projection performance test, record the first accepted baseline in benchmark_baselines/census_enrollment_projection_sql_baseline.json, and reject absolute or 15%-runtime/20%-RSS regressions through tests/performance/test_census_enrollment_performance.py
- [X] T035 Execute the complete fast suite through scripts/check_fast_suite_runtime.py with `--max-seconds 10` and resolve any budget violation without weakening the threshold
- [X] T036 [P] Document fact-authoritative projection behavior, safe clear modes, year-dependency/projection failure diagnostics, timed participant tracing, and rerun guidance in docs/guides/error_troubleshooting.md
- [ ] T037 Run every command and selector in specs/107-preserve-census-enrollment/quickstart.md, reconcile FR-001 through FR-012 and SC-001 through SC-007, and document any remaining limitation in that file

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup**: T002 depends on T001.
- **Foundational**: T003-T008 may be authored in parallel. T009 follows T003; T010 follows T004; T011 follows T005 and T007; T012 follows T005; T013 follows T006, T010, and T011; T014 follows T011-T013; T015 follows T012-T014; T016 follows T008; T017 follows T009-T016.
- **US1**: Depends only on Foundational. T018-T019 may run in parallel; T020 follows both; T021 follows T020.
- **US2**: Depends only on Foundational. T022-T023 may run in parallel; T024 follows both; T025 follows T024.
- **US3**: Depends only on Foundational. T026, T030, and T031 may run in parallel; T027-T029 are sequential edits to one integration file; T032 follows T026-T031; T033 follows T032.
- **Final phase**: T034 follows T007 and T011; T035 follows T008 and T016; T036 may run in parallel; T037 follows every selected story and T034-T036.

### User Story Dependency Graph

```text
Setup -> Foundational -> US1
                    \-> US2
                    \-> US3

US1 + US2 + US3 + performance gates -> final verification
```

### User Story Independence

- **US1**: Uses only the shared projection and proves census-participant preservation.
- **US2**: Uses only the shared projection and proves eligible-population correctness; it no longer depends on US1 implementation.
- **US3**: Uses shared projection/orchestration contracts and proves retention, isolation, auditability, and replay independently of US1/US2 SQL adjustments.

## Parallel Opportunities

- T003-T008 target separate test files and can be authored concurrently.
- T009, T010, T012, and T016 target separate implementation files after their tests fail.
- T018 and T019 can run in parallel for US1.
- T022 and T023 can run in parallel for US2.
- T026, T030, and T031 can run in parallel for US3.
- US1, US2, and US3 can start concurrently after Foundational completion.
- T036 can run while performance and fast-suite gates execute.

## Parallel Examples

### User Story 1

```text
T018: tests/integration/test_census_enrollment_persistence.py
T019: dbt/tests/test_census_participants_not_reenrolled.sql
```

### User Story 2

```text
T022: tests/integration/test_census_enrollment_persistence.py
T023: dbt/tests/test_enrollment_population_split.sql
```

### User Story 3

```text
T026: tests/unit/orchestrator/test_stage_validator.py
T030: dbt/tests/test_multi_year_state_history_retained.sql
T031: tests/integration/test_year_dependency_validation.py
```

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational phases.
2. Complete US1.
3. Run T021 and demonstrate census participation remains at 5% with no invalid year-two enrollment/opt-out.

### Incremental Delivery

1. Establish fact authority, safe refresh semantics, projection contract, and hard timing tools.
2. Deliver US1 census protection.
3. Deliver US2 eligibility preservation.
4. Deliver US3 history, isolation, auditability, and reproducibility.
5. Enforce 100K and fast-suite gates, publish diagnostics, and run full verification.

## Notes

- Never use `dbt/simulation.duckdb` for integration or performance tests.
- `fct_yearly_events` is the only post-census enrollment authority.
- The projection is disposable and rebuilt on retry/resume.
- Enrollment dbt models must use `ref('stg_prior_enrollment_state')`; raw fact, accumulator, projection, and self-history reads are prohibited.
- Eligibility tests assert population membership; event tests use probability `1.0`.
- dbt commands run from `dbt/` with `--threads 1`.
