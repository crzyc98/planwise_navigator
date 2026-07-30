# Tasks: Age-Banded Employer Core Contributions

**Input**: Design documents from `/specs/125-age-banded-core/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [configuration/UI contract](contracts/configuration-and-ui.md), [quickstart.md](quickstart.md)

**Tests**: Tests are required by the feature specification and constitution. Write each listed test before the related implementation, and run behavioral tests only against an isolated DuckDB database.

**Organization**: Tasks are grouped by user story after shared configuration prerequisites so each story has a clear independent verification path.

## Format: `[ID] [P?] [Story] Description`

- **[P]** marks work that can proceed in parallel once its dependencies are complete.
- **[US#]** maps a task to the corresponding user story in [spec.md](spec.md).

## Phase 1: Setup

**Purpose**: Establish checked-in fixtures and documentation inputs shared by implementation and isolated integration tests.

- [X] T001 [P] Add reusable valid, boundary-age, and empty age-banded core schedule fixture builders in `tests/fixtures/service_tier_scenarios.py`.
- [X] T002 [P] Document the new direct-YAML `age_schedule` and Studio `core_age_schedule` examples in `planalign_orchestrator/config/simulation_config.yaml` using decimal contribution rates.

---

## Phase 2: Foundational Configuration and Export Plumbing

**Purpose**: Make the schedule a validated, portable plan-design input before any UI or calculation can rely on it.

**⚠️ CRITICAL**: Complete this phase before user-story implementation.

- [X] T003 Add failing load-time validation coverage for valid, empty, gapped, overlapping, reversed/equal, negative-rate, and nonfinal-open-ended core age schedules in `tests/unit/config/test_core_contribution_validation.py`.
- [X] T004 Add failing direct-YAML and `dc_plan` export coverage, including decimal-to-percentage conversion and empty-schedule fallback, in `tests/unit/orchestrator/test_config_export.py`.
- [X] T005 Implement typed core age-tier fields, valid core-mode recognition, and contiguous `[min, max)` schedule validation in `planalign_orchestrator/config/workforce.py` and `planalign_orchestrator/config/loader.py`.
- [X] T006 Export direct `employer_core_contribution.age_schedule` as `employer_core_age_schedule` with `{min_age, max_age, rate}` and a single decimal-to-percentage conversion in `planalign_orchestrator/config/export.py`.
- [X] T007 Export Studio `dc_plan.core_age_schedule` through the same transient dbt-var contract and preserve its raw nested core config in `planalign_orchestrator/config/export.py`.
- [X] T008 Run `pytest tests/unit/config/test_core_contribution_validation.py tests/unit/orchestrator/test_config_export.py -q` and correct any compatibility regression in `planalign_orchestrator/config/{workforce.py,loader.py,export.py`.

**Checkpoint**: Validated age schedules can reach dbt through both supported configuration paths; invalid schedules fail before simulation.

---

## Phase 3: User Story 1 — Configure an Age-Banded Core Contribution (Priority: P1) 🎯 MVP

**Goal**: An administrator can select, edit, save, reopen, and accurately review an age-banded core design in Studio.

**Independent Test**: Configure contiguous age tiers in Studio, save and reopen the plan design, then confirm the read-only plan modal and scenario comparison show `Age-Banded` with the same ranges and rates.

### Implementation for User Story 1

- [X] T009 [P] [US1] Add `AgeCoreTier`, `dcCoreAgeSchedule` form state, defaults, config hydration, and decimal payload serialization in `planalign_studio/components/config/{types.ts,constants.ts,ConfigContext.tsx,buildConfigPayload.ts}`.
- [X] T010 [US1] Add the `age_banded` core-mode option and a reusable-style age-tier editor with add/remove controls and `[min, max)` guidance in `planalign_studio/components/config/DCPlanSection.tsx`.
- [X] T011 [US1] Reuse `validateMatchTiers` for age gaps and overlaps and show tier warnings in the age-tier editor in `planalign_studio/components/config/DCPlanSection.tsx`.
- [X] T012 [P] [US1] Add the age-banded label and age-schedule table to the read-only core contribution view in `planalign_studio/components/PlanDesignModal.tsx`.
- [X] T013 [P] [US1] Add the `age_banded` branch to `derivePlanSummary` so comparison text does not fall through to flat rate in `planalign_studio/components/ScenarioCostComparison.tsx`.
- [ ] T014 [US1] Run `cd planalign_studio && npm run build` and manually verify the saved/reopened plan-design flow described in `specs/125-age-banded-core/contracts/configuration-and-ui.md`.

**Checkpoint**: User Story 1 is independently usable: administrators can configure and accurately review an age-banded plan design.

---

## Phase 4: User Story 2 — Apply the Correct Annual Age-Based Contribution Rate (Priority: P1)

**Goal**: A multi-year simulation applies annual age-tier rates correctly and keeps the audited rate aligned with contribution dollars for every core mode.

**Independent Test**: Run an isolated multi-year scenario containing exact boundary ages, an employee who crosses a tier between years, and a mid-year hire; verify rate selection and amount/rate consistency.

### Tests for User Story 2

- [X] T015 [P] [US2] Add an isolated-DB integration test for exact age boundaries, annual tier migration, mid-year-hire compensation proration, and empty-schedule flat fallback in `tests/integration/test_age_banded_core_contributions.py`.
- [X] T016 [P] [US2] Add regression assertions that flat, service-graded, and points-based fixtures preserve their contribution results and that each amount agrees with its audit rate in `tests/integration/test_age_banded_core_contributions.py`.

### Implementation for User Story 2

- [X] T017 [US2] Create `get_age_banded_core_rate` with descending lower-bound ordering, explicit `[min, max)` checks, percentage-to-decimal conversion, and flat fallback in `dbt/macros/get_age_banded_core_rate.sql`.
- [X] T018 [US2] Add the age schedule var and one shared `core_rate_expr` that serves age-banded, points-based, service-graded, and flat modes at both amount and audit-rate sites in `dbt/models/intermediate/int_employer_core_contributions.sql`.
- [X] T019 [US2] Update core-contribution model documentation and add/adjust rate-consistency coverage in `dbt/models/intermediate/schema.yml` and `dbt/tests/test_age_banded_core_contributions.sql`.
- [X] T020 [US2] Run the new integration and dbt tests against a disposable `DATABASE_PATH` database, never `dbt/simulation.duckdb`, and fix failures in `tests/integration/test_age_banded_core_contributions.py` or `dbt/models/intermediate/int_employer_core_contributions.sql`.

**Checkpoint**: User Story 2 is independently testable: every employee-year receives the correct age-banded rate, and the same expression explains the audited rate and contribution amount.

---

## Phase 5: User Story 3 — Prevent Invalid Age Schedules (Priority: P2)

**Goal**: Administrators are blocked early from saving or running schedules with invalid age coverage or rates.

**Independent Test**: Load malformed YAML and Studio-originated plan configurations and verify clear validation failures; enter tier gaps/overlaps in Studio and verify visible warnings before a run.

### Tests for User Story 3

- [X] T021 [P] [US3] Extend `tests/unit/config/test_core_contribution_validation.py` to exercise equivalent direct-YAML and `dc_plan` invalid schedules and assert diagnostic messages identify the offending boundary or rate.

### Implementation for User Story 3

- [X] T022 [US3] Ensure the core schedule validator rejects every contract violation before export while retaining the empty `age_banded` fallback in `planalign_orchestrator/config/{workforce.py,loader.py}`.
- [X] T023 [US3] Ensure Studio age-tier input prevents negative values and renders the shared gap/overlap warnings and interval convention in `planalign_studio/components/config/DCPlanSection.tsx`.
- [X] T024 [US3] Run the focused validation/export tests and the Studio build from `specs/125-age-banded-core/quickstart.md`; update the relevant files only for defects found.

**Checkpoint**: User Story 3 prevents schedule mistakes from quietly changing employer cost.

---

## Phase 6: Compliance Caveat and Cross-Cutting Polish

**Purpose**: Preserve transparent 401(a)(4) communication, complete regression checks, and confirm end-to-end delivery.

- [X] T025 Add a failing age-banded 401(a)(4) caveat test, including successful early-return cases, while preserving service-risk assertions in `tests/test_ndt_401a4.py`.
- [X] T026 Set the existing 401(a)(4) risk flag/detail for every successful age-banded result without changing the numerical pass/fail calculation in `planalign_api/services/ndt_service.py`.
- [X] T027 Update the risk-warning heading, detailed text, and compact label to be accurate for both service and age-banded caveats in `planalign_studio/components/NDTTesting.tsx`.
- [X] T028 [P] Update the Studio 401(a)(4) response type only if the implementation changes the response contract; otherwise verify the existing fields remain sufficient in `planalign_studio/services/api.ts` and `tests/api/snapshots/openapi_schema.json`.
- [ ] T029 Run the complete isolated-DB validation sequence in `specs/125-age-banded-core/quickstart.md`, including `planalign batch --scenarios age_banded_core --clean`, and record any follow-up issues without expanding scope.
- [X] T030 Review changed configuration/model documentation for the annual-age convention and no-reporting-band dependency in `dbt/models/intermediate/{int_employer_core_contributions.sql,schema.yml}` and `planalign_orchestrator/config/simulation_config.yaml`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Start immediately.
- **Foundational (Phase 2)**: Depends on T001–T002 and blocks all user stories.
- **US1 (Phase 3)**: Depends on T003–T008; may run in parallel with US2 and US3 after the foundational phase.
- **US2 (Phase 4)**: Depends on T003–T008 and the shared fixture from T001; its dbt work does not depend on Studio work.
- **US3 (Phase 5)**: Depends on T003–T008; it can proceed in parallel with the UI and calculation stories.
- **Polish (Phase 6)**: Depends on the relevant user-story work; T029 is last.

### User Story Dependencies

- **US1 (P1)**: Uses the validated payload contract from Phase 2; otherwise independent.
- **US2 (P1)**: Uses the exported schedule contract from Phase 2; otherwise independent.
- **US3 (P2)**: Uses the typed schedule model from Phase 2; otherwise independent.

### Parallel Opportunities

- T001 and T002 can proceed in parallel.
- T003 and T004 are independent test-first tasks.
- After Phase 2, T009, T012, T013, T015, T016, and T021 touch independent files and can proceed in parallel.
- T025 can begin alongside user-story work because the NDT caveat uses the existing response transport, though T026/T027 must follow it.

## Parallel Execution Examples

### User Story 1

```text
Task: T009 — Studio form type/default/load/save wiring
Task: T012 — Read-only modal schedule rendering
Task: T013 — Scenario comparison summary copy
```

### User Story 2

```text
Task: T015 — Isolated age-banded calculation integration test
Task: T016 — Existing-mode regression and audit consistency test
```

### User Story 3

```text
Task: T021 — Invalid direct-YAML and Studio configuration tests
Task: T023 — Age-tier input constraints and visible editor warnings
```

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1 so an administrator can configure and accurately review the new design.
3. Complete US2 before treating the feature as financially usable; validate it with its isolated multi-year test.
4. Complete US3 to ensure invalid schedules cannot silently reprice participants.

### Incremental Delivery

1. Validated configuration and export contract.
2. Configurable and accurately described Studio plan design.
3. Correct annual calculation with regression protection.
4. Early schedule validation and transparent nondiscrimination caveat.

## Notes

- All behavioral simulation tests use a disposable `DATABASE_PATH` or `planalign batch --clean` scenario database.
- Do not run dbt behavioral validation against `dbt/simulation.duckdb`.
- The nondiscrimination work is a caveat surface only; no cross-testing or legal qualification logic is added.
