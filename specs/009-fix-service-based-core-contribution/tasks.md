# Tasks: Fix Service-Based Core Contribution Calculation

**Input**: Design documents from `/specs/009-fix-service-based-core-contribution/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: dbt tests included as specified in plan.md (Constitution Check III: Test-First Development)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **dbt models**: `dbt/models/intermediate/`
- **dbt macros**: `dbt/macros/`
- **dbt tests**: `dbt/tests/`
- **Integration tests**: `tests/integration/`
- **Fixtures**: `tests/fixtures/`

---

## Phase 1: Setup

**Purpose**: Prepare development environment and verify prerequisites

- [X] T001 Verify `int_workforce_snapshot_optimized` has `current_tenure` field by running: `duckdb dbt/simulation.duckdb "DESCRIBE int_workforce_snapshot_optimized"`
- [X] T002 Verify configuration export includes graded schedule by checking `/workspace/planalign_orchestrator/config/export.py` lines 621-631
- [X] T003 Create feature branch backup of `dbt/models/intermediate/int_employer_core_contributions.sql`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create shared macro and test infrastructure that all user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create tier lookup macro `get_tiered_core_rate` in `dbt/macros/get_tiered_core_rate.sql`
- [X] T005 Add dbt variable declarations for `employer_core_status` and `employer_core_graded_schedule` at lines 38-47 in `dbt/models/intermediate/int_employer_core_contributions.sql`
- [X] T006 Extend `snapshot_flags` CTE to include `FLOOR(current_tenure) AS years_of_service` in `dbt/models/intermediate/int_employer_core_contributions.sql` lines 193-199

**Checkpoint**: Foundation ready - macro exists and tenure data is available for tier lookup

---

## Phase 3: User Story 1 - Apply Service-Based Core Rates (Priority: P1) 🎯 MVP

**Goal**: Fix the core bug - ensure employees receive contribution rates based on their years of service when graded-by-service is configured

**Independent Test**: Configure a 2-tier scenario (0-9 years: 6%, 10+ years: 8%) and verify employees with different tenure levels receive different rates

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T007 [P] [US1] Create dbt test for 2-tier service schedule verification in `dbt/tests/test_service_tier_core_contributions.sql`
- [X] T008 [P] [US1] Create dbt test for flat-rate regression (no service tiers) in `dbt/tests/test_flat_rate_core_contributions.sql`

### Implementation for User Story 1

- [X] T009 [US1] Update contribution calculation (line 246) to use tier lookup macro when `employer_core_status = 'graded_by_service'` in `dbt/models/intermediate/int_employer_core_contributions.sql`
- [X] T010 [US1] Update rate output field (line 274) to reflect actual applied rate in `dbt/models/intermediate/int_employer_core_contributions.sql`
- [X] T011 [US1] Handle edge case: new hires (0 years tenure) get first tier rate in `dbt/models/intermediate/int_employer_core_contributions.sql`
- [X] T012 [US1] Handle edge case: tenure exceeding all tiers gets highest tier rate in `dbt/models/intermediate/int_employer_core_contributions.sql`
- [X] T013 [US1] Validate fix by running: `cd dbt && dbt run --select int_employer_core_contributions --threads 1`
- [X] T014 [US1] Run acceptance scenario 1: Verify employee with 5 years tenure gets 6% rate
- [X] T015 [US1] Run acceptance scenario 2: Verify employee with 15 years tenure gets 8% rate
- [X] T016 [US1] Run acceptance scenario 3: Verify employee with exactly 10 years tenure gets 8% rate
- [X] T017 [US1] Run acceptance scenario 4: Verify flat-rate scenario still works (regression test)

**Checkpoint**: Core bug is fixed - employees receive correct tiered rates. MVP complete.

---

## Phase 4: User Story 2 - Verify Multi-Tier Service Schedules (Priority: P2)

**Goal**: Ensure 3+ tier configurations work correctly (e.g., 0-2y: 4%, 3-5y: 5%, 6-10y: 6%, 11+y: 8%)

**Independent Test**: Configure a 4-tier service schedule and verify each tier applies correctly

### Tests for User Story 2

- [X] T018 [P] [US2] Create dbt test for 4-tier service schedule in `dbt/tests/test_multi_tier_core_contributions.sql`

### Implementation for User Story 2

- [X] T019 [US2] Verify tier lookup macro handles 4+ tiers correctly by reviewing `dbt/macros/get_tiered_core_rate.sql`
- [X] T020 [US2] Create test configuration with 4 service tiers in `tests/fixtures/service_tier_scenarios.py`
- [X] T021 [US2] Run acceptance scenario: Verify each of 4 tiers applies to appropriate tenure range
- [X] T022 [US2] Run acceptance scenario: Verify tier boundary employee (tenure crossing tier during year) uses tenure at contribution date

**Checkpoint**: Multi-tier configurations verified - complex graded schedules work correctly

---

## Phase 5: User Story 3 - Maintain Audit Trail for Service-Based Rates (Priority: P3)

**Goal**: Ensure contribution events include the applied service tier for audit/compliance purposes

**Independent Test**: Review contribution events and verify each includes applied tenure and rate

### Tests for User Story 3

- [X] T023 [P] [US3] Create dbt test to verify `applied_years_of_service` field is populated in `dbt/tests/test_audit_trail_core_contributions.sql`

### Implementation for User Story 3

- [X] T024 [US3] Add `applied_years_of_service` column to output SELECT in `dbt/models/intermediate/int_employer_core_contributions.sql`
- [X] T025 [US3] Update model schema to document new audit field in `dbt/models/intermediate/schema.yml`
- [X] T026 [US3] Verify audit trail by querying: `duckdb dbt/simulation.duckdb "SELECT employee_id, applied_years_of_service, core_contribution_rate FROM int_employer_core_contributions WHERE simulation_year = 2025 LIMIT 20"`
- [X] T027 [US3] Run acceptance scenario: Compare employee tenure to applied rate and verify match

**Checkpoint**: Audit trail complete - all contribution events show applied service tier

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [X] T028 [P] Update model header comment in `dbt/models/intermediate/int_employer_core_contributions.sql` to document graded-by-service support
- [X] T029 Run full validation using quickstart.md script
- [X] T030 Run regression test: Verify existing simulations without graded-by-service produce identical results
- [X] T031 [P] Update `dbt/models/intermediate/schema.yml` with new column descriptions
- [X] T032 Cleanup any debug code or temporary files

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verify prerequisites
- **Foundational (Phase 2)**: Depends on Setup - creates macro and extends CTE
- **User Story 1 (Phase 3)**: Depends on Foundational - implements core fix
- **User Story 2 (Phase 4)**: Depends on US1 completion - verifies multi-tier
- **User Story 3 (Phase 5)**: Depends on US1 completion - adds audit fields
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) ←── BLOCKS ALL USER STORIES
    ↓
    ├── Phase 3 (US1: Core Fix) 🎯 MVP
    │       ↓
    │   ├── Phase 4 (US2: Multi-Tier) ←── Can start after US1
    │   └── Phase 5 (US3: Audit Trail) ←── Can start after US1
    │           ↓
    └── Phase 6 (Polish) ←── After desired stories complete
```

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Fix contribution calculation before adding audit fields
- Validate with acceptance scenarios before marking complete

### Parallel Opportunities

- **Phase 2**: T004, T005, T006 touch different parts of the model - can be parallelized carefully
- **Phase 3**: T007, T008 are independent test files - can run in parallel
- **Phase 4 & 5**: Can run in parallel after Phase 3 completes (US2 and US3 are independent)
- **Phase 6**: T028, T031 touch different files - can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch tests for User Story 1 together:
Task: "Create dbt test for 2-tier service schedule in dbt/tests/test_service_tier_core_contributions.sql"
Task: "Create dbt test for flat-rate regression in dbt/tests/test_flat_rate_core_contributions.sql"

# After implementation, run acceptance scenarios together (different queries):
Task: "Run acceptance scenario 1: Verify 5-year tenure gets 6%"
Task: "Run acceptance scenario 2: Verify 15-year tenure gets 8%"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (3 tasks)
2. Complete Phase 2: Foundational (3 tasks)
3. Complete Phase 3: User Story 1 (11 tasks)
4. **STOP and VALIDATE**: Run all acceptance scenarios
5. Deploy/demo if ready - core bug is fixed!

### Incremental Delivery

1. Setup + Foundational → Foundation ready (6 tasks)
2. Add User Story 1 → Test independently → **MVP deployed** (11 tasks)
3. Add User Story 2 → Test multi-tier → Enhanced (5 tasks)
4. Add User Story 3 → Test audit trail → Compliance ready (5 tasks)
5. Polish → Production ready (5 tasks)

### Single Developer Strategy

Work phases sequentially:
1. Phase 1 + 2: Foundation (~1 hour)
2. Phase 3: Core fix (~2 hours) → **MVP**
3. Phase 4 + 5: Enhancements (~1 hour)
4. Phase 6: Polish (~30 min)

---

## Notes

- All file modifications are in `dbt/models/intermediate/int_employer_core_contributions.sql` (~320 lines)
- New macro goes in `dbt/macros/get_tiered_core_rate.sql`
- New tests go in `dbt/tests/` directory
- Run `dbt compile --select int_employer_core_contributions` to verify Jinja syntax
- Run `dbt test --select int_employer_core_contributions` to run associated tests
- Use `--threads 1` for work laptop stability
- Commit after each phase checkpoint
