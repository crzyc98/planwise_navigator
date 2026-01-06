# Tasks: Service-Based Match Contribution Tiers

**Input**: Design documents from `/specs/010-fix-match-service-tiers/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: dbt tests included per Constitution Principle III (Test-First Development)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **dbt models**: `dbt/models/intermediate/events/`
- **dbt macros**: `dbt/macros/`
- **Python orchestrator**: `planalign_orchestrator/config/`
- **Frontend**: `planalign_studio/components/`
- **Tests**: `tests/` (Python), `dbt/tests/` (SQL)

---

## Phase 1: Setup

**Purpose**: Verify existing infrastructure and prepare for implementation

- [x] T001 Verify dbt environment works: `cd dbt && dbt debug --threads 1`
- [x] T002 [P] Review existing `get_tiered_core_rate` macro pattern in dbt/macros/get_tiered_core_rate.sql
- [x] T003 [P] Review existing match calculation model in dbt/models/intermediate/events/int_employee_match_calculations.sql
- [x] T004 [P] Review config export pattern in planalign_orchestrator/config/export.py (lines 620-668)

**Checkpoint**: Codebase patterns understood, ready for foundational work

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create dbt variable defaults and macro that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Add `employer_match_status` variable with default 'deferral_based' in dbt/dbt_project.yml
- [x] T006 Add `employer_match_graded_schedule` variable with empty default in dbt/dbt_project.yml
- [x] T007 Create `get_tiered_match_rate` macro in dbt/macros/get_tiered_match_rate.sql following core pattern
- [x] T008 Add dbt test for `get_tiered_match_rate` macro in dbt/tests/test_tiered_match_rate.sql

**Checkpoint**: Foundation ready - macro exists, variables declared, user story implementation can now begin

---

## Phase 3: User Story 1 - Configure Service-Based Match Rates (Priority: P1) 🎯 MVP

**Goal**: Enable service-based match calculation via dbt variables (backend only)

**Independent Test**: Run dbt with `employer_match_status: 'graded_by_service'` and verify employees with different tenure receive correct match rates

### Tests for User Story 1

- [x] T009 [P] [US1] Create dbt schema test for service-based match in dbt/models/intermediate/schema.yml (updated existing entry)
- [x] T010 [P] [US1] Create dbt data test for tier boundary calculation in dbt/tests/test_service_match_boundaries.sql

### Implementation for User Story 1

- [x] T011 [US1] Add variable declarations to int_employee_match_calculations.sql header: `employer_match_status`, `employer_match_graded_schedule`
- [x] T012 [US1] Add years_of_service join CTE from int_workforce_snapshot_optimized in dbt/models/intermediate/events/int_employee_match_calculations.sql
- [x] T013 [US1] Add conditional branch for service-based calculation in dbt/models/intermediate/events/int_employee_match_calculations.sql
- [x] T014 [US1] Implement service-based match calculation: rate × min(deferral%, max_deferral_pct) × compensation
- [x] T015 [US1] Add `applied_years_of_service` audit field to output columns
- [x] T016 [US1] Update config export in planalign_orchestrator/config/export.py to export `employer_match_status`
- [x] T017 [US1] Add `employer_match_graded_schedule` transformation in planalign_orchestrator/config/export.py (follow core pattern lines 626-645)
- [x] T018 [US1] Verify backward compatibility: run existing deferral-based simulation unchanged

**Checkpoint**: Service-based match works via dbt variables. Test with quickstart.md examples:
```bash
cd dbt && dbt run --select int_employee_match_calculations --vars '{
  "simulation_year": 2025,
  "employer_match_status": "graded_by_service",
  "employer_match_graded_schedule": [
    {"min_years": 0, "max_years": 5, "rate": 50, "max_deferral_pct": 6},
    {"min_years": 5, "max_years": null, "rate": 100, "max_deferral_pct": 6}
  ]
}' --threads 1
```

---

## Phase 4: User Story 2 - UI Configuration for Service-Based Match (Priority: P2)

**Goal**: Enable service-based match configuration through PlanAlign Studio UI

**Independent Test**: Create service-based match schedule in UI, save, and verify it persists correctly to scenario config

### Implementation for User Story 2

- [ ] T019 [P] [US2] Add `ServiceMatchTier` TypeScript interface in planalign_studio/components/ConfigStudio.tsx
- [ ] T020 [P] [US2] Add `dcMatchStatus` state field: 'deferral_based' | 'graded_by_service' in planalign_studio/components/ConfigStudio.tsx
- [ ] T021 [US2] Add match status toggle (radio buttons or dropdown) in DC Plan section of planalign_studio/components/ConfigStudio.tsx
- [ ] T022 [US2] Add service tier editor component (similar to core contribution tiers) in planalign_studio/components/ConfigStudio.tsx
- [ ] T023 [US2] Add tier validation (no gaps, no overlaps) in UI before save in planalign_studio/components/ConfigStudio.tsx
- [ ] T024 [US2] Wire service tier config to API save payload in planalign_studio/components/ConfigStudio.tsx
- [ ] T025 [US2] Test UI round-trip: configure tiers → save → reload → verify persisted

**Checkpoint**: UI configuration works end-to-end. Users can configure service-based match tiers without editing files.

---

## Phase 5: User Story 3 - Audit Trail for Applied Service Tier (Priority: P3)

**Goal**: Provide compliance visibility into which service tier was applied per employee

**Independent Test**: Run simulation with service-based match, query output for `applied_years_of_service` field

### Implementation for User Story 3

- [ ] T026 [US3] Verify `applied_years_of_service` field is included in int_employee_match_calculations.sql output (completed in T015)
- [ ] T027 [US3] Add `applied_years_of_service` to fct_workforce_snapshot if downstream reports need it in dbt/models/marts/fct_workforce_snapshot.sql
- [ ] T028 [US3] Create dbt test validating applied_years_of_service matches expected tiers in dbt/tests/test_audit_years_of_service.sql
- [ ] T029 [US3] Document audit field in specs/010-fix-match-service-tiers/quickstart.md with example query

**Checkpoint**: Compliance officers can query `applied_years_of_service` to audit tier assignments.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, cleanup, and documentation

- [ ] T030 [P] Run full simulation end-to-end with service-based match: `planalign simulate 2025-2027 --verbose`
- [ ] T031 [P] Run dbt tests: `cd dbt && dbt test --threads 1`
- [ ] T032 Verify backward compatibility: run existing scenario without service-based config
- [ ] T033 Run quickstart.md validation steps to confirm documentation accuracy
- [ ] T034 [P] Update CLAUDE.md with feature reference if needed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational - MUST complete before US2/US3
- **User Story 2 (Phase 4)**: Depends on US1 (needs backend to work)
- **User Story 3 (Phase 5)**: Depends on US1 (needs audit field to exist)
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

```
US1 (Backend) ──┬──► US2 (UI) ──────────────────► Polish
                │
                └──► US3 (Audit) ────────────────► Polish
```

- **User Story 1 (P1)**: Foundational → Backend-only, no external dependencies
- **User Story 2 (P2)**: Requires US1 backend to function, but can be developed in parallel
- **User Story 3 (P3)**: Requires US1 audit field, minimal additional work

### Within Each User Story

- Tests MUST be written first (T009, T010)
- Variable declarations before logic changes
- Core logic before config export
- Config export before UI integration

### Parallel Opportunities

- T002, T003, T004 can run in parallel (different files, read-only)
- T009, T010 can run in parallel (separate test files)
- T019, T020 can run in parallel (different state declarations)
- T030, T031, T034 can run in parallel (independent validation)

---

## Parallel Example: Phase 3 (User Story 1)

```bash
# Launch tests for User Story 1 together:
Task: T009 "Create dbt schema test for service-based match in dbt/models/intermediate/events/schema.yml"
Task: T010 "Create dbt data test for tier boundary calculation in dbt/tests/test_service_match_boundaries.sql"

# After T011 (variable declarations), T012 and T013 can proceed:
Task: T012 "Add years_of_service join CTE"
Task: T013 "Add conditional branch for service-based calculation"

# Config export tasks can run in parallel with dbt model work:
Task: T016 "Update config export for employer_match_status"
Task: T017 "Add employer_match_graded_schedule transformation"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T008)
3. Complete Phase 3: User Story 1 (T009-T018)
4. **STOP and VALIDATE**: Test via dbt variables per quickstart.md
5. Deploy/demo backend-only service-based matching

### Incremental Delivery

1. Setup + Foundational → Macro and variables ready
2. Add User Story 1 → Test via CLI → Deploy (MVP!)
3. Add User Story 2 → Test UI → Deploy (full user experience)
4. Add User Story 3 → Test audit queries → Deploy (compliance complete)

### Single Developer Strategy

Execute in order: T001 → T034 (serial execution, ~2-3 hours estimated)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify dbt tests fail before implementing model changes
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Use `--threads 1` for all dbt commands per Constitution Principle VI
