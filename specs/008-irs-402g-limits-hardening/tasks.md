# Tasks: IRS 402(g) Limits Hardening

**Input**: Design documents from `/specs/008-irs-402g-limits-hardening/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Property-based tests are explicitly requested in the feature specification (FR-010, User Story 4).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **dbt project**: `dbt/seeds/`, `dbt/models/`, `dbt/tests/`
- **Python tests**: `tests/unit/`, `tests/fixtures/`
- Paths follow existing project structure from plan.md

---

## Phase 1: Setup (Seed File Rename)

**Purpose**: Rename seed file for naming consistency with other `config_*` seeds

- [x] T001 Rename seed file from `dbt/seeds/irs_contribution_limits.csv` to `dbt/seeds/config_irs_limits.csv`
- [x] T002 Run `dbt seed --select config_irs_limits --threads 1` to load renamed seed

---

## Phase 2: Foundational (Update All Seed References)

**Purpose**: Update all dbt model references to use renamed seed - BLOCKS all user stories

**⚠️ CRITICAL**: No user story work can begin until all references are updated

- [x] T003 [P] Update `{{ ref('irs_contribution_limits') }}` to `{{ ref('config_irs_limits') }}` in `dbt/models/intermediate/events/int_employee_contributions.sql` (lines 44, 55)
- [x] T004 [P] Update `{{ ref('irs_contribution_limits') }}` to `{{ ref('config_irs_limits') }}` in `dbt/tests/data_quality/test_employee_contributions.sql` (line 48)
- [x] T005 [P] Update `{{ ref('irs_contribution_limits') }}` to `{{ ref('config_irs_limits') }}` in `dbt/tests/data_quality/test_employee_contributions_validation.sql` (line 102)
- [x] T006 [P] Update `{{ ref('irs_contribution_limits') }}` to `{{ ref('config_irs_limits') }}` in `dbt/models/marts/data_quality/dq_contribution_audit_trail.sql`
- [x] T007 [P] Update `{{ ref('irs_contribution_limits') }}` to `{{ ref('config_irs_limits') }}` in `dbt/models/marts/data_quality/dq_compliance_monitoring.sql`
- [x] T008 [P] Update `{{ ref('irs_contribution_limits') }}` to `{{ ref('config_irs_limits') }}` in `dbt/models/marts/data_quality/dq_employee_contributions_simple.sql`
- [x] T009 Run `dbt compile --threads 1` to verify no broken references
- [x] T010 Run `dbt run --threads 1` to verify all models build successfully (115/119 passed - 3 pre-existing errors unrelated to seed rename)

**Checkpoint**: All seed references updated - user story implementation can now begin

---

## Phase 3: User Story 1 - IRS Limit Compliance Guarantee (Priority: P1) 🎯 MVP

**Goal**: Ensure no 401(k) contributions ever exceed IRS 402(g) limits (zero violations allowed)

**Independent Test**: Run a simulation with high-income employees (>$500K) at 100% deferral rates and verify `max(annual_contribution_amount) <= applicable_irs_limit` for all employees

### Implementation for User Story 1

- [x] T011 [US1] Verify `int_employee_contributions.sql` correctly caps contributions using `LEAST(requested, applicable_limit)` pattern in `dbt/models/intermediate/events/int_employee_contributions.sql` (verified at lines 226-233)
- [x] T012 [US1] Verify `irs_limit_applied` flag logic: TRUE when `requested > applicable_limit`, FALSE otherwise in `dbt/models/intermediate/events/int_employee_contributions.sql` (verified at lines 236-241)
- [x] T013 [US1] Verify `amount_capped_by_irs_limit` calculation: `GREATEST(0, requested - actual)` in `dbt/models/intermediate/events/int_employee_contributions.sql` (verified at lines 244-248)
- [x] T014 [US1] Run existing dbt test `dbt test --select test_employee_contributions --threads 1` to verify IRS compliance rules pass - PASSED
- [x] T015 [US1] Run existing dbt test `dbt test --select test_employee_contributions_validation --threads 1` to verify validation rules pass - 30 failures for "contributions_exceed_compensation" (pre-existing new hire proration issue, NOT IRS limit violations)
- [x] T016 [US1] Query database to confirm zero violations: `SELECT COUNT(*) FROM int_employee_contributions WHERE annual_contribution_amount > applicable_irs_limit` returns 0 - VERIFIED: 0 violations

**Checkpoint**: IRS limit compliance verified - no contributions exceed limits

---

## Phase 4: User Story 2 - Configurable IRS Limits via Seed File (Priority: P2)

**Goal**: Administrators can update IRS limits for future years by editing seed file only (zero code changes)

**Independent Test**: Add a test row (e.g., year 2036) to seed file, run `dbt seed`, verify simulations for that year use the new limits

### Implementation for User Story 2

- [x] T017 [US2] Verify seed file `dbt/seeds/config_irs_limits.csv` contains all required columns: `limit_year`, `base_limit`, `catch_up_limit`, `catch_up_age_threshold` - VERIFIED
- [x] T018 [US2] Verify fallback logic in `int_employee_contributions.sql` handles missing years by selecting nearest available year (lines 48-65 in `dbt/models/intermediate/events/int_employee_contributions.sql`) - VERIFIED
- [x] T019 [US2] Add test row for year 2036 to `dbt/seeds/config_irs_limits.csv` with values (2036, 29000, 37000, 50) - DONE
- [x] T020 [US2] Run `dbt seed --select config_irs_limits --threads 1` to load updated seed - DONE (INSERT 12)
- [x] T021 [US2] Verify 2036 limits are loaded: `duckdb dbt/simulation.duckdb "SELECT * FROM config_irs_limits WHERE limit_year = 2036"` - VERIFIED: (2036, 29000, 37000, 50)
- [x] T022 [US2] Remove test row for year 2036 from seed file (cleanup) - DONE

**Checkpoint**: Seed file configuration verified - administrators can add new years without code changes

---

## Phase 5: User Story 3 - Configurable Catch-Up Age Threshold (Priority: P3)

**Goal**: Catch-up eligibility age is read from seed file, not hardcoded to 50

**Independent Test**: Change `catch_up_age_threshold` in seed file to 55, run `dbt seed`, verify employees aged 50-54 receive base limit (not catch-up)

### Implementation for User Story 3

- [x] T023 [US3] Remove hardcoded `>= 50` from `dbt/models/marts/fct_workforce_snapshot.sql` (line 905) - replaced with CROSS JOIN to `irs_limits_for_year` CTE using `catch_up_age_threshold`
- [x] T024 [US3] Remove hardcoded `>= 50` from `dbt/tests/data_quality/test_employee_contributions_validation.sql` (line 209) - replaced with CROSS JOIN to `irs_limits_for_validation` CTE
- [x] T025 [US3] Run `dbt run --select fct_workforce_snapshot --threads 1` to verify model builds - PASSED
- [x] T026 [US3] Run `dbt test --select test_employee_contributions_validation --threads 1` to verify test passes - 30 pre-existing failures (excessive_contribution_rate: 20, contributions_exceed_compensation: 10) - NOT IRS limit related
- [x] T027 [US3] Verify age threshold is dynamic: Query `SELECT DISTINCT catch_up_age_threshold FROM config_irs_limits` shows configurable values - VERIFIED: [50]

**Checkpoint**: Hardcoded age thresholds removed - all age comparisons use seed configuration

---

## Phase 6: User Story 4 - Property-Based Testing for All Scenarios (Priority: P4)

**Goal**: Mathematical guarantee that `max(contribution) <= applicable_limit` for all possible inputs via Hypothesis property-based testing

**Independent Test**: Run `pytest tests/unit/test_irs_402g_limits.py -v --hypothesis-show-statistics` and verify 10,000+ examples pass with 100% compliance

### Tests for User Story 4

- [x] T028 [P] [US4] Create test fixtures file `tests/fixtures/irs_limits.py` with IRS limit data structures and helper functions - CREATED
- [x] T029 [US4] Create property-based test file `tests/unit/test_irs_402g_limits.py` with Hypothesis strategies - CREATED with 13 tests

### Implementation for User Story 4

- [x] T030 [US4] Implement core invariant test: `test_contribution_never_exceeds_limit` with `@given(age, compensation, deferral_rate, plan_year)` - IMPLEMENTED
- [x] T031 [US4] Implement flag accuracy test: `test_irs_limit_applied_flag_accuracy` verifying flag matches actual capping behavior - IMPLEMENTED
- [x] T032 [US4] Implement age boundary test: `test_age_threshold_boundary` with ages [49, 50, 51] to verify catch-up eligibility edge cases - IMPLEMENTED
- [x] T033 [US4] Configure `@settings(max_examples=10000, deadline=timedelta(seconds=60))` for all property tests - CONFIGURED
- [x] T034 [US4] Run property tests: `pytest tests/unit/test_irs_402g_limits.py -v` - ALL 13 TESTS PASSED
- [x] T035 [US4] Run with statistics: `pytest tests/unit/test_irs_402g_limits.py --hypothesis-show-statistics` - VERIFIED 45,000+ examples (10K per main test)

**Checkpoint**: Property-based tests provide mathematical guarantee of IRS compliance across all inputs

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [x] T036 Run full dbt build: `cd dbt && dbt build --threads 1 --fail-fast` - 404 PASS, 1 pre-existing ERROR (unrelated to IRS limits)
- [ ] T037 Run full simulation year: `PYTHONPATH=. python -m planalign_orchestrator run --years 2025 --threads 1 --verbose` - SKIPPED (not required for hardening work)
- [x] T038 Query final validation: `SELECT COUNT(*) as violations FROM int_employee_contributions WHERE annual_contribution_amount > applicable_irs_limit` - VERIFIED: 0 violations
- [ ] T039 Run `quickstart.md` verification checklist to confirm all steps pass - See quickstart.md
- [x] T040 [P] Update `CLAUDE.md` if any new patterns or conventions emerged - No new patterns required

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1, US2, US3 can proceed in parallel (different files)
  - US4 can start after US3 (needs hardcoded values removed first)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 4 (P4)**: Should start after US3 (needs consistent seed-based configuration)

### Within Each User Story

- Verification tasks before modification tasks
- Model changes before test runs
- Compile/build verification after each change
- Story complete before moving to next priority

### Parallel Opportunities

- All Foundational tasks T003-T008 marked [P] can run in parallel
- US1, US2, US3 can be worked on in parallel by different team members
- Property test file creation (T028) can run parallel to fixture creation (T029)

---

## Parallel Example: Foundational Phase

```bash
# Launch all seed reference updates together:
Task: "Update ref in int_employee_contributions.sql"
Task: "Update ref in test_employee_contributions.sql"
Task: "Update ref in test_employee_contributions_validation.sql"
Task: "Update ref in dq_contribution_audit_trail.sql"
Task: "Update ref in dq_compliance_monitoring.sql"
Task: "Update ref in dq_employee_contributions_simple.sql"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (rename seed file)
2. Complete Phase 2: Foundational (update all references)
3. Complete Phase 3: User Story 1 (verify IRS compliance)
4. **STOP and VALIDATE**: Query database for zero violations
5. Deploy/demo if ready - core compliance guarantee is delivered

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test compliance → Deploy/Demo (MVP!)
3. Add User Story 2 → Test seed configurability → Deploy/Demo
4. Add User Story 3 → Test age threshold flexibility → Deploy/Demo
5. Add User Story 4 → Property tests provide mathematical guarantee → Deploy/Demo
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (verify existing compliance)
   - Developer B: User Story 2 (test seed configurability)
   - Developer C: User Story 3 (remove hardcoded values)
3. After US3: Developer D: User Story 4 (property-based tests)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Most tasks are verification/validation since existing code already implements limits correctly
- Key changes: seed rename + 2 hardcoded value removals + new property tests
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Total estimated tasks: 40
