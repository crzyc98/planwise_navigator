# Tasks: Post-Termination Event Integrity

**Input**: Design documents from `/specs/112-post-termination-integrity/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `quickstart.md`

**Tests**: Required by the feature specification and constitution. Write each listed test first, confirm that it fails for the intended reason, then implement the corresponding behavior.

**Organization**: Tasks are grouped by user story so diagnosis, correction, determinism, and audit verification remain independently testable increments.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel after its stated prerequisites because it changes a different file and does not depend on another incomplete parallel task.
- **[Story]**: Maps implementation work to a user story from `spec.md`.
- Every task names the exact file containing its durable change or recorded verification result.

## Phase 1: Setup (Shared Test Infrastructure)

**Purpose**: Protect the supplied archive, establish PII-free fixtures, and create an isolated test harness before behavioral work.

- [X] T001 [P] Record SHA-256 hashes and modification times for the supplied run archive and confirm the approved 73/95/106/94/91 safe baseline in `specs/112-post-termination-integrity/research.md` without persisting employee-level rows
- [X] T002 [P] Create synthetic scenario/plan/employee event fixtures covering experienced termination, same-year new-hire termination, duplicate terms, prior-year termination, same-day events, missing dates, and cross-scope rows in `tests/fixtures/post_termination_events.py`
- [X] T003 Create the isolated DuckDB integration harness and feature test markers using the shared synthetic fixtures in `tests/integration/test_post_termination_event_integrity.py`

---

## Phase 2: Foundational Validation Semantics (Blocking Prerequisites)

**Purpose**: Establish one independent definition of a post-termination violation before changing any event producer.

**⚠️ CRITICAL**: Confirm T004 and T005 fail against the pre-correction behavior before completing T006.

- [X] T004 [P] Add failing table-driven tests for before/on/after termination, earliest duplicate termination, prior-year termination, scenario/plan isolation, normalized event types, excluded termination rows, null/missing effective dates (excluded from sequence comparison and never counted as valid; caught by the existing `not_null` test on `fct_yearly_events.effective_date`), and exact ERROR counts in `tests/test_validation_framework.py`
- [X] T005 [P] Rewrite the post-termination branch to use earliest scoped termination semantics and privacy-safe aggregate failure rows in `dbt/tests/data_quality/test_integrity_violations.sql`
- [X] T006 Implement lifetime earliest-termination lookup scoped by scenario ID and plan design ID while preserving configurable columns, strict same-day allowance, ERROR severity, and exact affected-record counts in `planalign_orchestrator/validation.py`
- [X] T007 Run the focused Python validation tests and isolated dbt compilation with `--threads 1`, then record the passing commands and outcomes in `specs/112-post-termination-integrity/quickstart.md`

**Checkpoint**: Python and dbt now agree on the invariant and can detect injected violations independently of generator fixes.

---

## Phase 3: User Story 1 - Establish the Root Cause (Priority: P1) 🎯 Diagnostic MVP

**Goal**: Reproduce and explain all affected events using deterministic safe aggregates with no persisted employee-level evidence.

**Independent Test**: Against the archived baseline, safe categories sum to 73, 95, 106, 94, and 91 by year and 459 overall; output contains no employee identifiers, exact dates, compensation, event details, or physical paths.

### Tests for User Story 1

- [X] T008 [US1] Add safe root-cause aggregation helpers that emit only year, event type, termination cohort, generation path, state source, and positive affected count in `tests/fixtures/post_termination_events.py`
- [X] T009 [US1] Add integration assertions for deterministic category order, yearly/grand-total reconciliation, generation-path classification, and prohibited PII fields in `tests/integration/test_post_termination_event_integrity.py`

### Implementation for User Story 1

- [X] T010 [US1] Execute the read-only aggregate diagnosis against the supplied archive, reconcile the 459 records to eligibility, enrollment, and enrollment_change (opt-out) paths and current-year state sources, document that contribution and deferral-state events derive solely from corrected enrollment/eligibility state (defining the correction boundary for FR-022 and US2 acceptance scenario 3), and finalize the before-change evidence in `specs/112-post-termination-integrity/research.md`

**Checkpoint**: The root cause is reproducible, fully reconciled, and safe to share without exposing employee records.

---

## Phase 4: User Story 2 - Prevent Invalid Post-Termination Events (Priority: P1)

**Goal**: Prevent later non-termination candidates from entering the authoritative event stream while retaining valid events before or on termination.

**Independent Test**: The synthetic isolated scenario produces zero post-termination fact events across eligibility, enrollment, opt-out, promotion, merit, and configured deferral paths; injected bad fact rows still fail the independent validator with exact counts.

### Tests for User Story 2

- [X] T011 [P] [US2] Add failing producer-boundary cases for experienced employees, same-year hires, valid same-day candidates, invalid later candidates, enrollment pre-deduplication fallback, and prior-year terminated employees in `tests/integration/test_post_termination_event_integrity.py`
- [X] T012 [P] [US2] Add failing workflow assertions that termination sources precede every boundary consumer and that explicit workflow/executor model lists contain eligibility and match-response entries consistently in `tests/unit/orchestrator/test_post_termination_workflow.py`

### Implementation for User Story 2

- [X] T013 [US2] Create the EVENT_GENERATION-tagged ephemeral earliest-date relation over experienced and new-hire termination sources in `dbt/models/intermediate/events/int_employee_termination_dates.sql` (contingency: if T011's prior-year-terminated cases fail because a generator state source surfaces prior-year terminated employees, widen this relation to lifetime-earliest termination per scenario/plan/employee before proceeding to T015–T019)
- [X] T014 [P] [US2] Document the termination-boundary model, cohort values, keys, effective-date rules, and not-null/uniqueness expectations in `dbt/models/intermediate/schema.yml`
- [X] T015 [P] [US2] Filter census and new-hire eligibility candidates against the shared cutoff while retaining dates on or before termination in `dbt/models/intermediate/events/int_eligibility_events.sql`
- [X] T016 [P] [US2] Filter the combined auto, proactive, voluntary, year-over-year, and opt-out candidates against the shared cutoff before prioritization and deduplication in `dbt/models/intermediate/int_enrollment_events.sql`
- [X] T017 [P] [US2] Apply the shared cutoff to promotion candidates so early-year terminations cannot receive later promotions in `dbt/models/intermediate/events/int_promotion_events.sql`
- [X] T018 [P] [US2] Replace the duplicated local termination-date union with the shared cutoff while preserving existing raise-date behavior in `dbt/models/intermediate/events/int_merit_events.sql`
- [X] T019 [P] [US2] Apply the shared cutoff to configured deferral-escalation candidates while retaining valid same-day changes in `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql`
- [X] T020 [P] [US2] Place the shared boundary and all consumers in deterministic EVENT_GENERATION order without changing accumulator/fact ordering in `planalign_orchestrator/pipeline/workflow.py`
- [X] T021 [P] [US2] Align the executor’s explicit sequential model list with the workflow, including eligibility and match-response parity, in `planalign_orchestrator/pipeline/event_generation_executor.py`
- [X] T022 [US2] Compile the affected dbt graph and run the synthetic integration suite against `/tmp/planalign-112/synthetic.duckdb`, recording zero violations and retained same-day cases in `specs/112-post-termination-integrity/quickstart.md`

**Checkpoint**: Event producers enforce the boundary before authoritative emission, while independent validation remains capable of detecting deliberately injected bad rows.

---

## Phase 5: User Story 3 - Preserve Determinism and Downstream Integrity (Priority: P2)

**Goal**: Prove that the correction remains deterministic, reconciles annual workforce state, and does not regress unsupported configuration compatibility or runtime materially.

**Independent Test**: Two complete isolated 2026–2030 runs from identical inputs produce identical ordered event/reconciliation/validation aggregates, zero annual workforce variance, zero sequence failures, and runtime within the 10% budget.

### Tests for User Story 3

- [X] T023 [P] [US3] Add ordered aggregate comparison helpers that exclude UUIDs and audit timestamps while covering event counts, workforce reconciliation, and validation outcomes in `tests/fixtures/post_termination_events.py`
- [X] T024 [US3] Add multi-year determinism, zero-reconciliation-variance, prior-year non-resurrection, and explainable-delta assertions in `tests/integration/test_post_termination_event_integrity.py`
- [X] T025 [P] [US3] Add a compatibility test proving legacy Polars configuration continues to export the supported SQL event-generation mode in `tests/unit/orchestrator/test_config_export.py`

### Implementation and Verification for User Story 3

- [X] T026 [US3] Run the first complete 2026–2030 simulation with archived-equivalent fingerprints into `/tmp/planalign-112/corrected.duckdb` and record yearly counts, validation outcomes, reconciliation totals, and elapsed time in `specs/112-post-termination-integrity/quickstart.md`
- [X] T027 [US3] Repeat the complete simulation into `/tmp/planalign-112/repeat.duckdb`, compare ordered aggregate fingerprints to T026, and document all pre-correction deltas in `specs/112-post-termination-integrity/research.md`
- [X] T028 [US3] Measure equivalent isolated full-run performance against the 183.42-second baseline using the best of three runs on an otherwise idle machine; the gate passes if the best run is ≤201.76 seconds (110% of baseline), otherwise profile the boundary joins before accepting; record all three timings and the accepted measurement in `specs/112-post-termination-integrity/quickstart.md`

**Checkpoint**: Corrected multi-year behavior is balanced, deterministic, explainable, and within the performance budget.

---

## Phase 6: User Story 4 - Produce a Verifiable Audit Outcome (Priority: P3)

**Goal**: Preserve every yearly validation result and demonstrate a corrected Studio run whose tamper-evident report is fully verified.

**Independent Test**: A copied-workspace Studio run generates an unchanged-schema report with no missing evidence, PASS/0 event-sequence rows for all five years, zero reconciliation variance, fully verified disposition, and a matching independently computed digest.

### Tests for User Story 4

- [X] T029 [P] [US4] Add failing capture tests proving a later passing year cannot overwrite an earlier failed-error or warning disposition and all yearly affected counts remain exact in `tests/unit/test_provenance_capture.py`
- [X] T030 [P] [US4] Add telemetry tests proving PASS emits zero, FAIL emits the exact safe aggregate count, and no employee-level details enter validation records in `tests/test_telemetry_emitter.py`
- [X] T031 [US4] Add an archived-run integration case with five PASS/0 event-sequence results, complete reconciliation, no missing evidence, and independently verified digest in `tests/integration/test_run_provenance_report.py`

### Implementation and Verification for User Story 4

- [X] T032 [US4] Recompute manifest validation disposition from all captured yearly results using failed-error then failed-warning then passed precedence in `planalign_api/services/provenance/capture.py`
- [X] T033 [US4] Run the corrected scenario through Studio using `/tmp/planalign-112/workspaces`, download and independently verify its report, and record the new run ID, disposition, PASS/0 rows, digest result, and unchanged baseline hashes in `specs/112-post-termination-integrity/quickstart.md`

**Checkpoint**: Reviewers receive a fully verified corrected artifact, while historical run evidence remains immutable.

---

## Phase 7: Polish & Cross-Cutting Quality Gates

**Purpose**: Finish documentation and apply repository-wide quality gates after all desired stories are complete.

- [X] T034 [P] Document why validation failures produce an incomplete rather than unverifiable report and how to resolve post-termination failures in `docs/guides/run_provenance_report.md`
- [X] T035 Run affected-model dbt compilation/tests from `dbt/` with `DATABASE_PATH=/tmp/planalign-112/quality.duckdb` and `--threads 1`, then record exact commands and outcomes in `specs/112-post-termination-integrity/quickstart.md`
- [X] T036 Run Ruff, feature-scoped mypy, focused pytest, and the complete fast suite, resolving only feature-related failures and recording results in `specs/112-post-termination-integrity/quickstart.md`
- [X] T037 Confirm `git diff --check`, zero changes to the supplied archive hashes/mtimes, no employee-level data in new artifacts, and evidence for every success criterion in `specs/112-post-termination-integrity/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; T001 and T002 can start in parallel, then T003 uses T002.
- **Foundational validation (Phase 2)**: Depends on Setup; blocks corrective implementation. T004 and T005 are written first in parallel, T006 implements the Python behavior, and T007 proves parity.
- **User Story 1 (Phase 3)**: Depends on Setup and foundational semantics. It establishes the safe root-cause evidence used to judge correction deltas.
- **User Story 2 (Phase 4)**: Depends on foundational semantics and the US1 baseline. T011/T012 must fail before T013–T021 implement producer changes.
- **User Story 3 (Phase 5)**: Depends on US2 because determinism and reconciliation must exercise corrected producers.
- **User Story 4 (Phase 6)**: Capture/telemetry tests can begin after Foundation, but final provenance integration and Studio acceptance depend on US2; the final corrected audit outcome also consumes US3 evidence.
- **Polish (Phase 7)**: Depends on every story selected for delivery.

### User Story Dependency Graph

```text
Setup → Foundational Validation → US1 Diagnosis → US2 Correction → US3 Determinism
                                      │               │              │
                                      └───────────────┴──────────────┴→ US4 Audit Outcome
```

### Within Each User Story

- Write tests first and confirm they fail for the intended missing behavior.
- Establish shared boundary/data semantics before modifying consumers.
- Filter candidate events before event prioritization and authoritative emission.
- Run focused synthetic checks before complete multi-year simulations.
- Record only safe aggregates and immutable artifact fingerprints.

### Parallel Opportunities

- T001 and T002 can run concurrently.
- T004 and T005 can run concurrently because they change Python and dbt validation tests separately.
- After T013, T014–T019 can be divided by model file; T020 and T021 can then run concurrently.
- After US2, T023 and T025 can run concurrently.
- T029 and T030 can run concurrently; T031 can be written while T032 is implemented after T029 fails.
- T034 can run alongside final technical quality checks.

---

## Parallel Example: User Story 2

```text
Prerequisite: T013 completes the shared termination-boundary relation.

Parallel task A: T015 — eligibility cutoff in dbt/models/intermediate/events/int_eligibility_events.sql
Parallel task B: T016 — enrollment cutoff in dbt/models/intermediate/int_enrollment_events.sql
Parallel task C: T017 — promotion cutoff in dbt/models/intermediate/events/int_promotion_events.sql
Parallel task D: T018 — merit cutoff reuse in dbt/models/intermediate/events/int_merit_events.sql
Parallel task E: T019 — deferral cutoff in dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql
```

## Parallel Example: User Story 4

```text
Parallel task A: T029 — provenance disposition tests in tests/unit/test_provenance_capture.py
Parallel task B: T030 — safe telemetry tests in tests/test_telemetry_emitter.py
After T029 fails: T032 — aggregate disposition implementation in planalign_api/services/provenance/capture.py
```

---

## Implementation Strategy

### Diagnostic MVP (User Story 1)

1. Complete Setup and Foundational Validation.
2. Complete US1 safe diagnostic evidence.
3. Stop and confirm that all 459 baseline violations are reconciled without PII.

This is the smallest independently demonstrable story. It identifies the defect but does not yet satisfy the user's correction goal.

### Recommended First Deliverable (User Stories 1 and 2)

1. Complete the diagnostic MVP.
2. Add the shared termination boundary and generator-level enforcement.
3. Confirm synthetic zero-violation behavior while injected invalid facts still fail validation.

This is the first deliverable that actually corrects the simulation event stream.

### Incremental Delivery

1. **US1**: Reproducible safe root-cause evidence.
2. **US2**: Correct generator behavior and preserve independent validation.
3. **US3**: Prove multi-year determinism, reconciliation, and performance.
4. **US4**: Produce and independently verify the corrected enterprise audit artifact.

## Notes

- `[P]` tasks operate on different files after their prerequisites are satisfied.
- All DuckDB behavioral writes use `/tmp/planalign-112`; the supplied archive and shared development database remain read-only.
- Run dbt only from `dbt/` with `--threads 1`.
- Do not add a fact-level cleanup filter, validator exclusion, severity downgrade, inferred rehire, or employee-level diagnostic artifact.
- Do not commit or create additional branches unless the user requests it.
