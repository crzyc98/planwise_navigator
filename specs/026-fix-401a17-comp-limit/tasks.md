# Tasks: Fix 401(a)(17) Compensation Limit for Employer Contributions

**Input**: Design documents from `/specs/026-fix-401a17-comp-limit/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: This feature includes a dbt data quality test per Constitution Principle III (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **dbt project**: `dbt/` at repository root
- Seeds: `dbt/seeds/`
- Models: `dbt/models/intermediate/`
- Tests: `dbt/tests/data_quality/`

---

## Phase 1: Setup (Configuration Data)

**Purpose**: Add 401(a)(17) compensation limits to configuration

- [x] T001 Add `compensation_limit` column to `dbt/seeds/config_irs_limits.csv` with values for years 2025-2035

---

## Phase 2: Foundational (Load Configuration)

**Purpose**: Ensure the seed data is loaded before model changes

**⚠️ CRITICAL**: Seed must be loaded before any model changes are tested

- [x] T002 Run `dbt seed --select config_irs_limits --threads 1` to load updated configuration
- [x] T003 Verify seed loaded correctly by querying `SELECT * FROM config_irs_limits WHERE limit_year = 2026`

**Checkpoint**: Configuration data ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Accurate Match Calculations (Priority: P1) 🎯 MVP

**Goal**: Cap employer match calculations at IRS 401(a)(17) limit for high earners

**Independent Test**: Run simulation with $400K+ employee and verify match ≤ 4% × $360,000 = $14,400 (2026)

### Test for User Story 1

- [x] T004 [US1] Create compliance test `dbt/tests/data_quality/test_401a17_compliance.sql` that returns violations (match amounts exceeding cap)

### Implementation for User Story 1

- [x] T005 [US1] Add `irs_compensation_limits` CTE to `dbt/models/intermediate/events/int_employee_match_calculations.sql` to fetch 401(a)(17) limit
- [x] T006 [US1] Modify deferral-based match cap calculation (lines 226-235) in `dbt/models/intermediate/events/int_employee_match_calculations.sql` to use `LEAST(eligible_compensation, irs_401a17_limit)`
- [x] T007 [US1] Modify service-based match calculation (line 128) in `dbt/models/intermediate/events/int_employee_match_calculations.sql` to use `LEAST(eligible_compensation, irs_401a17_limit)`
- [x] T008 [US1] Run `dbt run --select int_employee_match_calculations --threads 1 --vars "simulation_year: 2026"` to rebuild model
- [x] T009 [US1] Verify high earners have capped match amounts by querying `SELECT * FROM int_employee_match_calculations WHERE eligible_compensation > 360000`

**Checkpoint**: User Story 1 complete - match calculations now respect 401(a)(17) limit

---

## Phase 4: User Story 2 - Accurate Core Contribution Calculations (Priority: P1)

**Goal**: Cap employer core contribution calculations at IRS 401(a)(17) limit for high earners

**Independent Test**: Run simulation with $400K+ employee and verify core ≤ 2% × $360,000 = $7,200 (2026)

### Test for User Story 2

- [x] T010 [US2] Extend `dbt/tests/data_quality/test_401a17_compliance.sql` to include core contribution violations (if not already added in T004)

### Implementation for User Story 2

- [x] T011 [US2] Add `irs_compensation_limits` CTE to `dbt/models/intermediate/int_employer_core_contributions.sql` to fetch 401(a)(17) limit
- [x] T012 [US2] Modify core contribution calculation (lines 262-268) in `dbt/models/intermediate/int_employer_core_contributions.sql` to use `LEAST(compensation, irs_401a17_limit)`
- [x] T013 [US2] Modify contribution rate calculation (lines 275-303) in `dbt/models/intermediate/int_employer_core_contributions.sql` to use same capped compensation
- [x] T014 [US2] Run `dbt run --select int_employer_core_contributions --threads 1 --vars "simulation_year: 2026"` to rebuild model
- [x] T015 [US2] Verify high earners have capped core amounts by querying `SELECT * FROM int_employer_core_contributions WHERE eligible_compensation > 360000`

**Checkpoint**: User Story 2 complete - core contributions now respect 401(a)(17) limit

---

## Phase 5: User Story 3 - Multi-Year Limit Tracking (Priority: P2)

**Goal**: Verify correct year-specific limits are applied in multi-year simulations

**Independent Test**: Run 2025-2027 simulation and verify each year uses its respective limit

### Implementation for User Story 3

- [x] T016 [US3] Run multi-year simulation: `planalign simulate 2025-2027` or equivalent dbt commands
- [x] T017 [US3] Verify year-specific limits by querying:
  ```sql
  SELECT simulation_year,
         MAX(employer_match_amount) AS max_match,
         MAX(employer_core_amount) AS max_core
  FROM int_employee_match_calculations m
  JOIN int_employer_core_contributions c USING (employee_id, simulation_year)
  WHERE m.eligible_compensation > 400000
  GROUP BY simulation_year
  ORDER BY simulation_year
  ```
- [x] T018 [US3] Confirm 2025 uses $350K limit, 2026 uses $360K limit, 2027 uses $370K limit

**Checkpoint**: User Story 3 complete - multi-year simulations use correct per-year limits

---

## Phase 6: User Story 4 - Audit Trail (Priority: P3)

**Goal**: Add audit visibility to track when 401(a)(17) capping was applied

**Independent Test**: Query high earners and verify `irs_401a17_limit_applied` flag is TRUE

### Implementation for User Story 4

- [x] T019 [US4] Add `irs_401a17_limit_applied` boolean field to `dbt/models/intermediate/events/int_employee_match_calculations.sql` output: `eligible_compensation > lim.irs_401a17_limit AS irs_401a17_limit_applied`
- [x] T020 [US4] Add `irs_401a17_limit_applied` boolean field to `dbt/models/intermediate/int_employer_core_contributions.sql` output: `compensation > lim.irs_401a17_limit AS irs_401a17_limit_applied`
- [x] T021 [US4] Run `dbt run --select int_employee_match_calculations int_employer_core_contributions --threads 1 --vars "simulation_year: 2026"` to rebuild both models
- [x] T022 [US4] Verify audit field by querying:
  ```sql
  SELECT employee_id, eligible_compensation, irs_401a17_limit_applied
  FROM int_employee_match_calculations
  WHERE simulation_year = 2026
  ORDER BY eligible_compensation DESC
  LIMIT 10
  ```

**Checkpoint**: User Story 4 complete - audit trail shows when capping was applied

---

## Phase 7: Polish & Validation

**Purpose**: Final validation and documentation

- [x] T023 Run full compliance test: `dbt test --select test_401a17_compliance --threads 1`
- [ ] T024 Run `dbt build --threads 1 --fail-fast` to ensure no regressions
- [ ] T025 Execute quickstart.md verification queries to confirm expected results
- [ ] T026 Verify no violations for employees below 401(a)(17) limit (contribution calculations unchanged)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 - seed must be updated first
- **User Story 1 (Phase 3)**: Depends on Phase 2 - configuration must be loaded
- **User Story 2 (Phase 4)**: Depends on Phase 2 - can run parallel to US1
- **User Story 3 (Phase 5)**: Depends on US1 + US2 - needs both models updated
- **User Story 4 (Phase 6)**: Can start after Phase 2 - audit field is additive
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

```
Phase 1 (Setup)
    │
    v
Phase 2 (Foundational)
    │
    ├──────────┬──────────┐
    v          v          v
 US1 (P1)   US2 (P1)   US4 (P3)
 Match      Core       Audit
    │          │          │
    └────┬─────┘          │
         v                │
      US3 (P2)            │
      Multi-year          │
         │                │
         └───────┬────────┘
                 v
            Phase 7 (Polish)
```

### Parallel Opportunities

- **US1 and US2**: Different files, can run in parallel after Phase 2
- **US4 (audit field)**: Can be implemented in parallel with US1/US2 since it's additive
- **T005-T007 and T011-T013**: Model changes are in different files, can be developed in parallel

---

## Parallel Example: User Stories 1 & 2

```bash
# After Phase 2 (Foundational) completes, launch in parallel:

# Developer A: User Story 1 (Match)
Task: "Add irs_compensation_limits CTE to int_employee_match_calculations.sql"
Task: "Modify match cap calculation to use LEAST()"

# Developer B: User Story 2 (Core)
Task: "Add irs_compensation_limits CTE to int_employer_core_contributions.sql"
Task: "Modify core calculation to use LEAST()"

# Both can merge, then run Phase 5 (US3) for multi-year validation
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002-T003)
3. Complete Phase 3: User Story 1 - Match (T004-T009)
4. Complete Phase 4: User Story 2 - Core (T010-T015)
5. **STOP and VALIDATE**: Run compliance test (T023)
6. Deploy if passing - MVP complete!

### Incremental Delivery

1. Setup + Foundational → Configuration ready
2. Add User Story 1 → Match calculations compliant → Can demo
3. Add User Story 2 → Core contributions compliant → Can demo
4. Add User Story 3 → Multi-year validation → Full verification
5. Add User Story 4 → Audit trail → Compliance reporting ready

### Estimated Task Count by Story

| Phase | Story | Tasks | Parallel |
|-------|-------|-------|----------|
| 1 | Setup | 1 | - |
| 2 | Foundational | 2 | - |
| 3 | US1 (Match) | 6 | 2 |
| 4 | US2 (Core) | 6 | 2 |
| 5 | US3 (Multi-year) | 3 | - |
| 6 | US4 (Audit) | 4 | 2 |
| 7 | Polish | 4 | 2 |
| **Total** | - | **26** | **8** |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- All dbt commands use `--threads 1` for stability (per Constitution VI)
- Verification queries can be run via `duckdb dbt/simulation.duckdb "..."`
- Commit after each phase or logical group
- Stop at any checkpoint to validate story independently
