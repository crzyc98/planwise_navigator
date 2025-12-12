# Tasks: Centralize Age/Tenure Band Definitions

**Input**: Design documents from `/specs/001-centralize-band-definitions/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

All paths are relative to repository root. This is a dbt project:
- Seeds: `dbt/seeds/`
- Models: `dbt/models/`
- Macros: `dbt/macros/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create baseline event counts for regression testing before any changes

- [x] T001 Capture baseline event counts by running simulation and recording counts in dbt/seeds/baseline_event_counts.csv
- [x] T002 [P] Create macros directory structure at dbt/macros/bands/

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create seed files and macros that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 [P] Create age band seed file at dbt/seeds/config_age_bands.csv with columns: band_id, band_label, min_value, max_value, display_order
- [x] T004 [P] Create tenure band seed file at dbt/seeds/config_tenure_bands.csv with columns: band_id, band_label, min_value, max_value, display_order
- [x] T005 [P] Create staging model at dbt/models/staging/stg_config_age_bands.sql
- [x] T006 [P] Create staging model at dbt/models/staging/stg_config_tenure_bands.sql
- [x] T007 Create assign_age_band macro at dbt/macros/bands/assign_age_band.sql that generates CASE expression from seed data
- [x] T008 Create assign_tenure_band macro at dbt/macros/bands/assign_tenure_band.sql that generates CASE expression from seed data
- [x] T009 Run dbt seed --threads 1 to load seed files and verify they load correctly
- [x] T010 Run dbt run --select stg_config_age_bands stg_config_tenure_bands --threads 1 to verify staging models

**Checkpoint**: Foundation ready - seed files and macros exist, user story implementation can begin

---

## Phase 3: User Story 1 - Data Administrator Updates Band Boundaries (Priority: P1) 🎯 MVP

**Goal**: Replace hardcoded band definitions in all 12 files with macro calls, enabling single-source configuration changes

**Independent Test**: Modify a band boundary in the seed file, run dbt build, verify all models use the updated boundary

### Schema Tests for User Story 1

- [x] T011 [P] [US1] Create schema tests for config_age_bands in dbt/models/staging/schema.yml (unique, not_null, accepted_values)
- [x] T012 [P] [US1] Create schema tests for config_tenure_bands in dbt/models/staging/schema.yml (unique, not_null, accepted_values)
- [x] T013 [US1] Run dbt test --select stg_config_age_bands stg_config_tenure_bands --threads 1 to verify schema tests pass

### Migration: Event Generation Macros (4 files)

- [x] T014 [P] [US1] Replace hardcoded age/tenure bands in dbt/macros/events/events_hire_sql.sql with macro calls
- [x] T015 [P] [US1] Replace hardcoded age/tenure bands in dbt/macros/events/events_termination_sql.sql with macro calls
- [x] T016 [P] [US1] Replace hardcoded age/tenure bands in dbt/macros/events/events_promotion_sql.sql with macro calls
- [x] T017 [P] [US1] Replace hardcoded age/tenure bands in dbt/macros/events/events_merit_sql.sql with macro calls
- [x] T018 [US1] Run dbt build --threads 1 and compare event counts to baseline (regression test after macro migration)

### Migration: Event Generation Models (3 files)

- [x] T019 [P] [US1] Replace hardcoded age/tenure bands in dbt/models/intermediate/events/int_termination_events.sql with macro calls
- [x] T020 [P] [US1] Replace hardcoded age/tenure bands in dbt/models/intermediate/events/int_promotion_events.sql with macro calls
- [x] T021 [P] [US1] Replace hardcoded age/tenure bands in dbt/models/intermediate/events/int_merit_events.sql with macro calls
- [x] T022 [US1] Run dbt build --threads 1 and compare event counts to baseline (regression test after model migration)

### Migration: Foundation Model (1 file)

- [x] T023 [US1] Replace hardcoded age/tenure bands in dbt/models/intermediate/int_baseline_workforce.sql with macro calls
- [x] T024 [US1] Run dbt build --threads 1 and compare event counts to baseline (regression test)

### Migration: Monitoring Models (2 files)

- [x] T025 [P] [US1] N/A - Monitoring models use validation ranges (18-70 age, 0-50 tenure), not band assignment CASE statements
- [x] T026 [P] [US1] N/A - Monitoring models use validation ranges (18-70 age, 0-50 tenure), not band assignment CASE statements
- [x] T027 [US1] Run dbt build --threads 1 and compare event counts to baseline (final regression test) - PASSED 0% diff

**Checkpoint**: All 8 files with band definitions migrated (4 macros + 3 event models + 1 foundation). Band configuration changes now require editing only 1 file.

---

## Phase 4: User Story 2 - Developer Maintains Band Logic (Priority: P2)

**Goal**: Ensure band logic is discoverable and reusable for future development

**Independent Test**: A developer can create a new model using the band macros without reading existing implementations

### Implementation for User Story 2

- [x] T028 [US2] Add inline documentation comments to dbt/macros/bands/assign_age_band.sql explaining usage and [min, max) convention
- [x] T029 [US2] Add inline documentation comments to dbt/macros/bands/assign_tenure_band.sql explaining usage and [min, max) convention
- [x] T030 [US2] Update dbt/models/staging/schema.yml with comprehensive descriptions for band seed tables
- [x] T031 [US2] Verify macro documentation by running dbt docs generate and reviewing in dbt docs serve

**Checkpoint**: Developer can discover and understand band system from dbt docs alone

---

## Phase 5: User Story 3 - Auditor Validates Band Consistency (Priority: P3)

**Goal**: Enable auditors to verify band definitions are consistent and correctly applied

**Independent Test**: Auditor can inspect config_age_bands.csv and config_tenure_bands.csv as authoritative source

### Implementation for User Story 3

- [x] T032 [P] [US3] Create custom test for band gaps validation at dbt/tests/data_quality/test_age_band_no_gaps.sql
- [x] T033 [P] [US3] Create custom test for band overlaps validation at dbt/tests/data_quality/test_age_band_no_overlaps.sql
- [x] T034 [P] [US3] Create custom test for tenure band gaps at dbt/tests/data_quality/test_tenure_band_no_gaps.sql
- [x] T035 [P] [US3] Create custom test for tenure band overlaps at dbt/tests/data_quality/test_tenure_band_no_overlaps.sql
- [x] T036 [US3] Run dbt test --threads 1 to verify all custom validation tests pass - 4/4 PASS
- [x] T037 [US3] Run final regression test comparing event counts to baseline (SC-003, SC-004 validation) - ALL PASS

**Checkpoint**: Auditors can verify band integrity via dbt tests and seed files

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and cleanup

- [x] T038 [P] Update quickstart.md at specs/001-centralize-band-definitions/quickstart.md with actual file paths
- [x] T039 [P] Add band configuration section to CLAUDE.md documenting the new macros
- [x] T040 Remove baseline_event_counts.csv from dbt/seeds/ (no longer needed after migration complete)
- [x] T041 Run full dbt build --threads 1 and dbt test --threads 1 to verify final state - 26/26 band tests PASS

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion
- **User Story 2 (Phase 4)**: Depends on User Story 1 completion (macros must exist)
- **User Story 3 (Phase 5)**: Depends on User Story 1 completion (migration must be done)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - This is the core migration
- **User Story 2 (P2)**: Can start after US1 completes - Adds documentation to existing macros
- **User Story 3 (P3)**: Can start after US1 completes - Adds validation tests for existing seeds

### Within Each User Story

- Schema tests before migrations (ensure seed data is valid)
- Migrate incrementally with regression test after each batch
- Run dbt build after each migration batch to catch issues early

### Parallel Opportunities

- T003, T004 (seed files) can run in parallel
- T005, T006 (staging models) can run in parallel
- T014-T017 (macro migrations) can run in parallel
- T019-T021 (model migrations) can run in parallel
- T025, T026 (monitoring migrations) can run in parallel
- T032-T035 (validation tests) can run in parallel

---

## Parallel Example: Phase 2 Foundational

```bash
# Launch seed file creation in parallel:
Task: "Create age band seed file at dbt/seeds/config_age_bands.csv"
Task: "Create tenure band seed file at dbt/seeds/config_tenure_bands.csv"

# Then launch staging models in parallel:
Task: "Create staging model at dbt/models/staging/stg_config_age_bands.sql"
Task: "Create staging model at dbt/models/staging/stg_config_tenure_bands.sql"
```

## Parallel Example: US1 Macro Migration

```bash
# Launch all macro migrations in parallel:
Task: "Replace hardcoded bands in dbt/macros/events/events_hire_sql.sql"
Task: "Replace hardcoded bands in dbt/macros/events/events_termination_sql.sql"
Task: "Replace hardcoded bands in dbt/macros/events/events_promotion_sql.sql"
Task: "Replace hardcoded bands in dbt/macros/events/events_merit_sql.sql"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (capture baseline)
2. Complete Phase 2: Foundational (seeds + macros)
3. Complete Phase 3: User Story 1 (migrate all 12 files)
4. **STOP and VALIDATE**: Compare event counts to baseline (must be 0% difference)
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test regression → Deploy (MVP!)
3. Add User Story 2 → Documentation complete → Deploy
4. Add User Story 3 → Validation tests complete → Deploy
5. Each story adds value without breaking previous stories

### Success Criteria Mapping

| Success Criterion | Task(s) |
|-------------------|---------|
| SC-001: 100% files migrated | T014-T027 |
| SC-002: 1 file for changes | T003-T004 (seed files) |
| SC-003: 0% event count diff | T018, T022, T024, T027, T037 |
| SC-004: Byte-identical hazards | T018, T022, T024, T027 |
| SC-005: 90% duplication reduction | T007-T008 (macros) |
| SC-006: 100% validation coverage | T032-T036 |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Regression tests after each migration batch catch issues early
- dbt tests validate band configuration integrity
- Commit after each task or logical group
