# Tasks: Per-Design Plan Parameters

**Input**: Design documents from `/specs/632-per-design-plan-parameters/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: This feature uses TDD. Contract and integration tests precede each behavioral implementation.

## Phase 1: Setup and Guardrails

**Purpose**: Verify the existing project boundary and establish the feature-owned fixture/test structure.

- [X] T001 Verify repository ignore files already cover Python, dbt, DuckDB, Node, environment, and temporary artifacts in `.gitignore`, `.dockerignore`, and frontend lint configuration without changing unrelated rules
- [X] T002 Create deterministic fixture package structure in `tests/fixtures/plan_design_parameters/` and register only the fixtures required by `tests/integration/test_plan_design_parameters.py`

---

## Phase 2: Foundational Configuration and Relations

**Purpose**: Build the typed keyed configuration and relation contracts required by every user story.

**Critical**: No behavioral model conversion begins until this phase passes.

- [X] T003 Add failing Pydantic tests for exact design-set equality, rate bounds, interval ordering, same-family compatibility, and deterministic serialization in `tests/unit/orchestrator/test_config.py`
- [X] T004 Add failing export/fingerprint tests for legacy absence, keyed deterministic output, and full-design-set provenance in `tests/unit/orchestrator/test_config_export.py` and `tests/test_run_metadata.py`
- [X] T005 Implement typed per-design match, core, auto-enrollment, escalation, and eligibility models plus validation in `planalign_orchestrator/config/plan_design.py`
- [X] T006 Wire `plan_design_parameters` through `planalign_orchestrator/config/loader.py`, `planalign_orchestrator/config/safety.py`, and `planalign_orchestrator/config/__init__.py`
- [X] T007 Implement deterministic keyed dbt export while preserving legacy scalar exports in `planalign_orchestrator/config/export.py`
- [X] T008 Add the machine-checked exported-var disposition registry and coverage assertion in `planalign_orchestrator/config/export.py` and `tests/test_dbt_var_coverage.py`
- [X] T009 Add failing executable empty/cardinality contract tests in `dbt/tests/test_plan_design_parameter_relations.sql`
- [X] T010 Implement typed empty-safe macros in `dbt/macros/get_plan_design_parameters.sql`, `dbt/macros/get_plan_design_match_tiers.sql`, and `dbt/macros/get_plan_design_core_graded_schedule.sql`

**Checkpoint**: Typed config/export tests and macro relation contracts pass; legacy golden export is unchanged.

---

## Phase 3: User Story 1 — Two Designs Use Different Match Parameters (Priority: P1) MVP

**Goal**: Apply same-family match tiers, rates, caps, and derived ceilings by assigned employee design.

**Independent Test**: In an isolated 2025–2027 run, $80,000 employees deferring 4% tie to $2,400 under 100%-on-3% and $1,600 under 50%-on-6%, with independent caps and matching fact/snapshot amounts.

- [X] T011 [US1] Add failing same-family match fixtures and per-employee Decimal tie-out tests in `tests/fixtures/plan_design_parameters/` and `tests/integration/test_plan_design_parameters.py`
- [X] T012 [US1] Convert match tiers and caps to design-keyed joins while retaining the legacy scalar Jinja branch in `dbt/models/intermediate/int_employee_match_calculations.sql`
- [X] T013 [US1] Make derived match-max ceilings design-aware in `dbt/macros/resolve_match_magnet_ceiling.sql`, `dbt/models/intermediate/int_voluntary_enrollment_decision.sql`, `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql`, and `dbt/models/intermediate/events/int_deferral_match_response_events.sql`
- [X] T014 [US1] Harden touched match/eligibility joins with available scenario, design, employee, and year keys and update match schema/tests in `dbt/models/intermediate/schema.yml` and `dbt/tests/`

**Checkpoint**: US1 hand tie-outs, cardinality, facts, snapshots, and multi-year stickiness pass independently.

---

## Phase 4: User Story 2 — Other Plan Levers Vary by Design (Priority: P1)

**Goal**: Resolve core, enrollment, escalation, and eligibility parameters by assigned design.

**Independent Test**: An isolated edge configuration proves independent core amounts, enrollment populations/dates/defaults, escalation increments/caps, and waiting-day boundaries for both designs over 2025–2027.

- [X] T015 [US2] Add failing core/enrollment/escalation/eligibility edge fixtures and boundary assertions in `tests/fixtures/plan_design_parameters/` and `tests/integration/test_plan_design_parameters.py`
- [X] T016 [US2] Convert flat core rate and service-graded schedule to design-keyed relations with a legacy scalar branch in `dbt/models/intermediate/int_employer_core_contributions.sql`
- [X] T017 [US2] Redesign `dbt/models/intermediate/int_plan_eligibility_determination.sql` as the assignment-aware authoritative eligibility relation; retain staging waiting dates only for the legacy scalar path and override them from the authoritative keyed relation in snapshots
- [X] T018 [US2] Move plan eligibility after assignment in `planalign_orchestrator/pipeline/workflow.py` and update `tests/test_workflow_schedule.py`, `tests/unit/test_tier_b_stage_merge.py`, `tests/fixtures/state_pipeline_graph_contract.yaml`, and execution metadata
- [X] T019 [US2] Route `dbt/models/intermediate/events/int_eligibility_events.sql`, `dbt/models/intermediate/int_voluntary_enrollment_decision.sql`, and `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql` through the authoritative design-aware eligibility relation
- [X] T020 [US2] Apply design default rate, window, and scope in `dbt/models/intermediate/int_enrollment_events.sql` after joining `int_plan_design_assignment_accumulator`
- [X] T021 [US2] Apply design escalation increment/cap consistently in `dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql`, `dbt/models/intermediate/int_deferral_rate_state_accumulator.sql`, `dbt/models/intermediate/events/int_deferral_match_response_events.sql`, and escalation data-quality models
- [X] T022 [US2] Update schema documentation and convert scalar-based expected-value dbt tests to resolve parameters by design in `dbt/models/intermediate/schema.yml`, `dbt/models/marts/data_quality/`, and `dbt/tests/`

**Checkpoint**: US2 edge configuration passes independently without cross-design leakage or pipeline cycles.

---

## Phase 5: User Story 3 — Existing Single-Design Behavior Is Unchanged (Priority: P1)

**Goal**: Prove legacy scalar runs and equivalent one-entry keyed runs have identical deterministic business rows.

**Independent Test**: Deterministic 40- and 149-row census slices produce bidirectional `EXCEPT ALL` counts of 0/0 and stable ordered row hashes across canonical marts, excluding only documented wall-clock metadata.

- [X] T023 [US3] Add scalar-versus-keyed bidirectional `EXCEPT ALL` and ordered-row-hash parity coverage at census sizes 40 and 149 in `tests/integration/test_plan_design_parameters.py`
- [X] T024 [US3] Remove any legacy-path SQL/export drift found by parity tests without weakening comparison coverage in the affected config, macro, or dbt consumer files
- [X] T025 [US3] Run and record the isolated 2025–2027 scalar-versus-keyed parity gate in `specs/632-per-design-plan-parameters/quickstart.md`

**Checkpoint**: The single-design hard gate passes at both census sizes across the full multi-year invariant fixture.

---

## Phase 6: User Story 4 — Invalid Configurations Fail Explicitly and Empty SQL Is Valid (Priority: P2)

**Goal**: Reject partial/mismatched design terms before execution while preserving schema-valid empty macro relations.

**Independent Test**: Missing, extra, duplicate, incompatible, overlapping, and empty-required schedules fail Pydantic validation; optional empty macro inputs execute and return zero typed rows.

- [X] T026 [US4] Add negative configuration and optional-empty relation cases to `tests/unit/orchestrator/test_config.py`, `tests/unit/orchestrator/test_config_export.py`, and `dbt/tests/test_plan_design_parameter_relations.sql`
- [X] T027 [US4] Refine configuration and macro errors so they name the design, lever, and invalid ids/bounds in `planalign_orchestrator/config/plan_design.py` and the new dbt macros
- [X] T028 [US4] Add a full isolated run proving assignment plus optional empty inactive-family schedules remains valid in `tests/integration/test_plan_design_parameters.py`

**Checkpoint**: All invalid cases fail before dbt and all allowed empty relations execute successfully.

---

## Phase 7: Polish and Cross-Cutting Validation

**Purpose**: Complete documentation, quality gates, and acceptance evidence.

- [X] T029 Reconcile implementation with `specs/632-per-design-plan-parameters/contracts/lever-disposition.md` and document vesting as deferred without claiming dbt coverage
- [X] T030 Run targeted Ruff, Black, config/export tests, dbt parse/tests with `--threads 1`, the dedicated integration suite, and `pytest -m fast`; record exact pass/fail coverage in `specs/632-per-design-plan-parameters/quickstart.md`
- [X] T031 Run `git diff --check`, verify no shared `dbt/simulation.duckdb` mutation, review the final diff for unrelated changes, and mark all completed tasks in `specs/632-per-design-plan-parameters/tasks.md`

---

## Dependencies and Execution Order

- Phase 1 has no dependency.
- Phase 2 depends on Phase 1 and blocks every user story.
- US1 and US2 both depend on the keyed config/relation foundation; execute US1 first because match is the headline MVP and validates the relation pattern.
- US3 depends on US1 and US2 because it validates the complete converted surface.
- US4 depends on the stable config/macro contracts from Phases 2–5.
- Polish depends on all selected user stories.

## Parallel Opportunities

- Test fixture data and Python configuration tests may be prepared independently before touching shared config files.
- Macro files are independent of Python model implementation once the export contract is fixed.
- US1 match conversion and US2 eligibility research touch different primary models, but final integration is sequential because enrollment/match-response models overlap.
- Documentation reconciliation can run alongside the final isolated validation campaign.

## Implementation Strategy

1. Build and verify the strict keyed configuration/export foundation.
2. Deliver US1 match calculations as the independently testable MVP.
3. Extend the proven relation pattern to core, enrollment, escalation, and eligibility.
4. Enforce the single-design compatibility hard gate before negative-case polish.
5. Finish with complete isolated validation and no vesting overclaim.
