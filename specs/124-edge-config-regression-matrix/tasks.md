---
description: "Actionable implementation tasks for Edge-Configuration Regression Matrix"
---

# Tasks: Edge-Configuration Regression Matrix

**Input**: Design documents from /specs/124-edge-config-regression-matrix/

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/matrix-interface.md, quickstart.md

**Organization**: Tasks are grouped by user story. The feature is test infrastructure; tests are included because the specification explicitly requires seeded mutation validation and independent end-to-end verification.

## Phase 1: Setup

**Purpose**: Establish the test-infrastructure paths and pytest/CI entry points.

- [X] T001 Create the planned test directories and package files in tests/edge_config/__init__.py and tests/fixtures/edge_config/
- [X] T002 [P] Register the edge_config_matrix pytest marker in pyproject.toml and preserve the existing multi_year_invariants marker semantics
- [X] T003 [P] Add the edge-config-matrix CI job and failure-only artifact upload in .github/workflows/ci.yml with a bounded timeout and the documented pytest command
- [X] T004 [P] Add the matrix command, case names, artifact location, and extension guidance to tests/TEST_INFRASTRUCTURE.md and tests/README.md

---

## Phase 2: Foundational

**Purpose**: Implement shared catalog, fixture, isolation, and diagnostic infrastructure that all user stories require.

- [X] T005 Define the immutable EdgeConfigScenario and ScenarioRun records, validation rules, and exactly-four catalog guard in tests/edge_config/catalog.py
- [X] T006 [P] Define shared violation/result types and formatting helpers with case, boundary, expected, observed, and bounded sample-row fields in tests/edge_config/assertions.py
- [X] T007 [P] Implement violation-query execution against read-only completed DuckDB outputs, including a maximum sample size of 20, in tests/edge_config/queries.py
- [X] T008 Implement case fixture loading, required-group validation, and effective-config identity reporting in tests/fixtures/edge_config_matrix.py
- [X] T009 Implement per-case temporary DuckDB execution through ConstructionSpec/build_orchestrator, capture simulation exceptions, and block assertions for incomplete runs in tests/fixtures/edge_config_matrix.py
- [X] T010 Add shared-dev-database signature protection, failure-database preservation, and concurrent-run-safe temporary paths in tests/fixtures/edge_config_matrix.py
- [X] T011 Write the matrix contract and catalog-shape tests for four unique cases, setup-failure semantics, simulation-failure semantics, and bounded diagnostics in tests/integration/test_edge_config_matrix.py
- [X] T012 [P] Add the common tiny census schema template and metadata conventions for labeled boundary groups in tests/fixtures/edge_config/README.md

**Checkpoint**: Shared runner and catalog are ready; each user story can add or verify its case behavior without changing isolation semantics.

---

## Phase 3: User Story 1 - Configuration branches are protected from regression (Priority: P1) 🎯 MVP

**Goal**: Exercise exactly four risky configuration combinations and prove each seeded business-rule mutation fails the relevant named case.

**Independent Test**: Run pytest -m edge_config_matrix -v on a known-good revision, then apply each isolated mutation (cutoff bypass, eligibility-suppression bypass, tenure-tier flattening, cap overflow) and confirm only the affected case reports a targeted failure.

### Tests for User Story 1

- [X] T013 [P] [US1] Add a red test for the broad_auto_enrollment_cutoff mutation and expected before/after-cutoff employee groups in tests/integration/test_edge_config_matrix.py
- [X] T014 [P] [US1] Add a red test for the new_hire_eligibility_suppression mutation and suppressed/control groups in tests/integration/test_edge_config_matrix.py
- [X] T015 [P] [US1] Add a red test for the tenure_graded_employer_match mutation and distinct service-band treatment in tests/integration/test_edge_config_matrix.py
- [X] T016 [P] [US1] Add a red test for the auto_escalation_low_cap mutation, including below/equal/above-cap starts, in tests/integration/test_edge_config_matrix.py

### Implementation for User Story 1

- [X] T017 [P] [US1] Create the broad_auto_enrollment_cutoff YAML config and labeled census fixture with employees on both sides of the early hire-date cutoff in tests/fixtures/edge_config/broad_auto_enrollment_cutoff.yaml and tests/fixtures/edge_config/broad_auto_enrollment_cutoff.csv
- [X] T018 [P] [US1] Create the new_hire_eligibility_suppression YAML config and labeled census fixture with suppressed new hires and eligible controls in tests/fixtures/edge_config/new_hire_eligibility_suppression.yaml and tests/fixtures/edge_config/new_hire_eligibility_suppression.csv
- [X] T019 [P] [US1] Create the tenure_graded_employer_match YAML config and labeled census fixture with distinct completed-service bands and stable expected match inputs in tests/fixtures/edge_config/tenure_graded_employer_match.yaml and tests/fixtures/edge_config/tenure_graded_employer_match.csv
- [X] T020 [P] [US1] Create the auto_escalation_low_cap YAML config and labeled census fixture with below-cap, at-cap, and above-cap starting rates in tests/fixtures/edge_config/auto_escalation_low_cap.yaml and tests/fixtures/edge_config/auto_escalation_low_cap.csv
- [X] T021 [US1] Add all four case descriptors to the catalog with documented one- or two-year horizons, boundary rules, expected groups, and configured override values in tests/edge_config/catalog.py
- [X] T022 [US1] Implement the four targeted violation queries for cutoff enrollment, eligibility suppression, tenure-graded match treatment, and escalation cap in tests/edge_config/queries.py
- [X] T023 [US1] Wire the parametrized end-to-end matrix test to run each catalog case and emit named actionable diagnostics in tests/integration/test_edge_config_matrix.py
- [X] T024 [US1] Run the known-good matrix and verify all four cases pass; run each seeded mutation and record that the relevant case fails without adding snapshot equality checks in tests/integration/test_edge_config_matrix.py

**Checkpoint**: User Story 1 is independently valuable as the focused regression safety net.

---

## Phase 4: User Story 2 - Analysts can trust targeted plan behavior (Priority: P2)

**Goal**: Make each case assert concrete enrollment, eligibility, match, and rate outcomes rather than merely checking that a simulation completed.

**Independent Test**: Run each named case with its boundary-crossing fixture and verify the targeted employee statuses, configured match treatment, and capped deferral rates from completed fact outputs.

- [X] T025 [P] [US2] Add assertions that in-boundary auto-enrollment/control employees and out-of-boundary employees produce the expected enrollment and eligibility statuses in tests/edge_config/assertions.py
- [X] T026 [P] [US2] Add assertions that suppressed new hires remain unenrolled/unmatched while eligible controls follow normal auto-enrollment in tests/edge_config/assertions.py
- [X] T027 [P] [US2] Add assertions that distinct tenure groups map to their configured match bands and expected employer-match treatment/amounts in tests/edge_config/assertions.py
- [X] T028 [P] [US2] Add assertions that below-, equal-, and above-cap starting rates never produce a resulting deferral rate above the configured cap in tests/edge_config/assertions.py
- [X] T029 [US2] Add effective-configuration and observed-value fields to every failure diagnostic and verify bounded affected employee/year samples in tests/integration/test_edge_config_matrix.py
- [X] T030 [US2] Add explicit fixture checks for omitted/default config blocks and conflicting base/override values in tests/fixtures/edge_config_matrix.py
- [X] T031 [US2] Validate that zero expected events are treated as intentional only when the case fixture declares the reason, in tests/integration/test_edge_config_matrix.py
- [X] T032 [US2] Run the four independent case selections and confirm each independently verifies its targeted business outcome without full-output snapshots in tests/integration/test_edge_config_matrix.py

**Checkpoint**: User Story 2 is independently testable as targeted business-behavior protection.

---

## Phase 5: User Story 3 - The matrix is safe and practical to run (Priority: P3)

**Goal**: Make local and pre-merge execution isolated, bounded, actionable, and safe under concurrent invocation.

**Independent Test**: Run pytest -m edge_config_matrix -v twice and concurrently; confirm equivalent case results, no shared database changes, bounded runtime, and preserved diagnostics for a deliberate failure.

- [X] T033 [P] [US3] Add a test that records and compares the shared dbt/simulation.duckdb signature before and after the complete matrix in tests/integration/test_edge_config_matrix.py
- [X] T034 [P] [US3] Add a concurrent-run test using independent pytest temporary roots and assert distinct database paths with equivalent case outcomes in tests/integration/test_edge_config_matrix.py
- [X] T035 [US3] Add failure-artifact assertions for local preservation and verify simulation errors are reported separately from business-rule failures in tests/integration/test_edge_config_matrix.py
- [X] T036 [US3] Execute the documented quickstart command twice with pytest duration reporting and confirm the complete matrix stays within five minutes in specs/124-edge-config-regression-matrix/quickstart.md
- [X] T037 [US3] Validate the edge-config-matrix GitHub Actions job, timeout, required-check naming, and failure artifact path in .github/workflows/ci.yml
- [X] T038 [US3] Confirm the matrix reuses Feature 113 support and does not duplicate general invariant or determinism checks in tests/edge_config/catalog.py and tests/TEST_INFRASTRUCTURE.md

**Checkpoint**: All three user stories are complete and the matrix is ready for regular pre-merge use.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency, documentation, and quality checks across the feature.

- [X] T039 [P] Add a traceability table mapping FR-001 through FR-014 and SC-001 through SC-007 to catalog, fixture, assertion, isolation, and CI tests in specs/124-edge-config-regression-matrix/contracts/matrix-interface.md
- [X] T040 [P] Document the final four case horizons, effective configuration defaults/overrides, fixture group labels, and expected outcomes in specs/124-edge-config-regression-matrix/data-model.md
- [X] T041 Run ruff/format checks on new Python test infrastructure and run git diff --check for all changed files in tests/edge_config/, tests/fixtures/edge_config_matrix.py, and tests/integration/test_edge_config_matrix.py
- [X] T042 Run the focused matrix, Feature 113 multi-year invariant suite, and the relevant fast test subset against isolated databases; record commands and outcomes in specs/124-edge-config-regression-matrix/quickstart.md
- [X] T043 Review all changed files for sensitive census/runtime artifacts and ensure no DuckDB contents or PII-bearing outputs are added to version control in .gitignore and specs/124-edge-config-regression-matrix/

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1) has no dependencies and establishes paths/markers/CI documentation.
- Foundational (Phase 2) depends on Setup and blocks all user-story work.
- User Story 1 depends on Foundational and delivers the MVP regression matrix.
- User Story 2 depends on Foundational and the case descriptors from User Story 1; it can begin in parallel after the shared runner is stable, but final integration uses the four descriptors.
- User Story 3 depends on Foundational and the runnable matrix; it can proceed in parallel with User Story 2 after the first green matrix run.
- Polish (Phase 6) depends on all desired stories being complete.

### User Story Dependencies

- US1 (P1): Foundational only; no dependency on other stories once the shared runner exists.
- US2 (P2): Foundational plus US1 catalog descriptors/fixtures for concrete behavior assertions.
- US3 (P3): Foundational plus a runnable US1 matrix; validates isolation and CI rather than adding business semantics.

### Dependency Graph

    Setup -> Foundational -> US1 -> Polish
                         -> US2
                         -> US3

US1 is the MVP. US2 strengthens outcome-level assertions using the same cases. US3 hardens execution and delivery. US2 and US3 can proceed in parallel after US1's first green run.

---

## Parallel Execution Examples

### User Story 1

    T013, T014, T015, T016  (mutation tests can be written in parallel)
    T017, T018, T019, T020  (four fixture/config pairs can be created in parallel)
    T022 and T023 follow the shared catalog/fixture interfaces.

### User Story 2

    T025, T026, T027, T028  (four assertion families touch separate functions)
    T029, T030, T031 follow the shared diagnostic/fixture result types.

### User Story 3

    T033, T034, T035 can be developed in parallel in separate test sections; T037 can proceed independently in CI configuration.

### Cross-cutting

    T039 and T040 can be documented in parallel; T041-T043 are final validation/review tasks.

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 Setup and Phase 2 Foundational.
2. Complete Phase 3 User Story 1.
3. Stop and validate with the known-good matrix plus the four seeded mutations.
4. Deliver the focused four-case regression safety net.

### Incremental Delivery

1. Add User Story 2 targeted business-outcome assertions.
2. Add User Story 3 isolation/concurrency/runtime/CI validation.
3. Complete Phase 6 documentation and quality checks.

### Parallel Team Strategy

After Foundational completes:
- Developer A: US1 case fixtures and mutation tests.
- Developer B: US2 assertion families.
- Developer C: US3 isolation and CI checks.

---

## Notes

- Every task uses the required checklist format: checkbox, sequential ID, optional P marker, required story label in story phases, and an exact file path.
- No task introduces product behavior, schema changes, public configuration fields, or full-output snapshots.
- Preserve the existing Feature 113 multi-year invariant/determinism suite as the general correctness source.
