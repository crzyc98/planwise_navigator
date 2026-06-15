---
description: "Task list for 095-fix-enrollment-snapshot"
---

# Tasks: Voluntary Enrollment Events Reflected in Annual Snapshot

**Input**: Design documents from `/specs/095-fix-enrollment-snapshot/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/data-quality-tests.md, quickstart.md

**Tests**: INCLUDED — required by Constitution Principle III (Test-First) and spec FR-010 (permanent automated guard, build-failing). The regression test must FAIL on the pre-fix database and PASS after the fix.

**Organization**: Tasks are grouped by user story. US1 (the accumulator fix) is the MVP and the shared root-cause fix that US2 and US3 verify propagation/persistence over.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3 (maps to spec user stories)
- All paths are absolute from repo root `/Users/nicholasamaral/Developer/fidelity_planalign/`

## Path Conventions

- dbt models: `dbt/models/...` (run dbt from `dbt/`, `--threads 1`)
- dbt tests: `dbt/models/marts/data_quality/` + `dbt/models/intermediate/schema.yml`
- Python tests: `tests/`

---

## Phase 1: Setup (Baseline & Branch)

**Purpose**: Establish the failing baseline so the fix is verifiable and reversible.

- [X] T001 Confirm on branch `095-fix-enrollment-snapshot` and that `dbt/simulation.duckdb` has a multi-year run (2025–2027); if absent, run `planalign simulate 2025-2027` to produce it.
- [X] T002 Capture the pre-fix baseline by running the reproduction queries from `specs/095-fix-enrollment-snapshot/quickstart.md` §1 and saving output to `specs/095-fix-enrollment-snapshot/baseline-prefix.txt` (expect 2026 `voluntary_enrollment` = 59 enrollees / 0 participating, `year_over_year_voluntary` = 1 / 0).

**Checkpoint**: Defect reproduced and recorded.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Scaffolding shared by all stories. No behavior change yet.

**⚠️ CRITICAL**: Must complete before user-story phases.

- [X] T003 Verify the `dbt/models/marts/data_quality/` directory and its `dbt_project.yml`/`schema.yml` wiring exist and are included in `dbt build`; note the existing data-quality test registration pattern (E080) to mirror.

**Checkpoint**: Test location and registration pattern confirmed.

---

## Phase 3: User Story 1 - Voluntary enrollees appear as participating with their deferral rate (Priority: P1) 🎯 MVP

**Goal**: Previously-unenrolled employees who voluntarily enroll show as `participating` with their selected deferral rate in `fct_workforce_snapshot`.

**Independent Test**: After the fix, every voluntary-category enrollee (net of opt-outs) in every simulation year shows `participation_status = 'participating'` with `current_deferral_rate > 0` — the quickstart §1 reconciliation shows `enrollees == participating` for all year/category rows.

### Tests for User Story 1 (write FIRST, must FAIL pre-fix) ⚠️

- [X] T004 [P] [US1] Create reconciliation data-quality model `dbt/models/marts/data_quality/dq_voluntary_enrollment_snapshot.sql` per `contracts/data-quality-tests.md` Contract 1: return offending rows for any voluntary enrollee (`event_category IN ('voluntary_enrollment','proactive_voluntary','year_over_year_voluntary')`, no same-year opt-out) whose matching `fct_workforce_snapshot` record is missing OR `participation_status <> 'participating'` OR `current_deferral_rate <= 0`.
- [X] T005 [US1] Register `dq_voluntary_enrollment_snapshot` as a build-failing test (severity `error`) in `dbt/models/marts/data_quality/schema.yml` (Contract 1 → FR-010), and confirm it currently FAILS against the pre-fix DB: `cd dbt && dbt test --select dq_voluntary_enrollment_snapshot --threads 1` (expect ~60 failing rows for 2026).
- [X] T006 [P] [US1] Add singular test `dbt/tests/assert_participation_deferral_consistency.sql` per Contract 3: fail rows in `fct_workforce_snapshot` where (`participation_status='participating'` AND `current_deferral_rate<=0`) OR (`participation_status='not_participating'` AND `current_deferral_rate>0`).

### Implementation for User Story 1

- [X] T007 [US1] Fix `is_enrolled_flag` precedence in the subsequent-year branch of `dbt/models/intermediate/int_deferral_rate_state_accumulator.sql` (≈ line 465): replace `COALESCE(ps.is_enrolled_flag, ne.employee_id IS NOT NULL, false)` with explicit precedence — opt-out → `false`, current-year new enrollment (`ne`) → `true`, else `COALESCE(ps.is_enrolled_flag, false)` (per research.md Decision 2 / data-model.md transition table).
- [X] T008 [US1] Fix the inclusion `WHERE` predicate in the same subsequent-year branch (≈ line 506) so a current-year enrollment is retained even when prior-year state is `false` (`ne.employee_id IS NOT NULL OR COALESCE(ps.is_enrolled_flag, false) = true`), preserving existing opt-out / carried-forward handling. Do NOT touch the `first_year_state` branch.
- [X] T009 [US1] Rebuild the accumulator-forward chain WITHOUT full-refresh, per affected year: `cd dbt && dbt run --select int_deferral_rate_state_accumulator+ --vars '{"simulation_year": 2026}' --threads 1` then the same for 2027 (never `--full-refresh` the accumulator — temporal state).
- [X] T010 [US1] Verify GREEN: re-run quickstart §1 reconciliation (all year/category rows `enrollees == participating`) and `dbt test --select dq_voluntary_enrollment_snapshot --threads 1` returns 0 rows; spot-check `EMP_2025_0000129` (2026) shows `participating`, `current_deferral_rate = 0.08`.

**Checkpoint**: US1 functional — voluntary enrollees participate with correct deferral rate; FR-001/002/003/005 satisfied.

---

## Phase 4: User Story 2 - Voluntary enrollees receive the correct employer match (Priority: P1)

**Goal**: Voluntary enrollees, now carrying a deferral rate, receive the configured employer match in the snapshot/match events.

**Independent Test**: For voluntary enrollees with a non-zero match formula, `fct_employer_match_events` (and the snapshot match field) show match > 0 equal to the formula output for their deferral rate and compensation.

**Depends on**: US1 (T007–T009) — match propagates through `int_employee_contributions` → `int_employee_match_calculations` → `fct_employer_match_events` once the accumulator retains the employee.

### Tests for User Story 2 (write FIRST) ⚠️

- [X] T011 [P] [US2] Add singular test `dbt/tests/assert_voluntary_enrollee_match_nonzero.sql` per Contract 2/FR-004: for voluntary enrollees (no same-year opt-out) with comp > 0 under a non-zero configured match formula, fail rows where `fct_employer_match_events` match amount is 0 or NULL.

### Implementation for User Story 2

- [X] T012 [US2] Rebuild the contribution/match chain for affected years: `cd dbt && dbt run --select int_employee_contributions+ --vars '{"simulation_year": 2026}' --threads 1` (and 2027); confirm no model changes are required — propagation only (research.md Decision 3).
- [X] T013 [US2] Verify GREEN: run quickstart §4 match spot-check (`EMP_2025_0000129`, 2026 → `employer_match > 0`) and `dbt test --select assert_voluntary_enrollee_match_nonzero --threads 1` returns 0 rows.

**Checkpoint**: US2 functional — match correctly applied to voluntary enrollees; FR-004 satisfied.

---

## Phase 5: User Story 3 - Voluntary enrollment carries forward across years (Priority: P2)

**Goal**: A voluntary enrollment persists into later years' snapshots (until opt-out), continuing to carry a rate and match.

**Independent Test**: An employee who voluntarily enrolled in 2026 with no later change events remains `participating` with the same deferral rate (and non-zero match) in 2027; an employee who opted out in a later year shows not participating that year.

**Depends on**: US1 fix (carry-forward path); independently verifiable.

### Tests for User Story 3 (write FIRST) ⚠️

- [X] T014 [P] [US3] Add multi-year persistence test `dbt/tests/assert_voluntary_enrollment_persists.sql` per Contract 5/FR-007: fail rows where an employee enrolled (voluntary) in year Y with no subsequent opt-out/unenroll is not `participating` (or rate changed without an escalation/match-response reason) in year Y+1.
- [X] T015 [P] [US3] Add cross-category reconciliation test `dbt/tests/assert_enrollment_category_reconciliation.sql` per Contract 4/FR-009: per `simulation_year` and category, assert `enrollment_events_net_of_optouts - snapshot_participants = 0` for voluntary categories.

### Implementation for User Story 3

- [X] T016 [US3] Verify GREEN: run `cd dbt && dbt test --select assert_voluntary_enrollment_persists assert_enrollment_category_reconciliation --threads 1` (0 failing rows) and quickstart §6 persistence query for `EMP_2025_0000129` across 2026–2027.

**Checkpoint**: US3 functional — persistence and reconciliation hold across years; FR-006/007/009 satisfied.

---

## Phase 6: FR-008 Same-Year Enroll-then-Opt-Out Prorated Window (Priority: P2 / Edge — DEFERRED, design review)

**Goal**: An employee who voluntarily enrolls and opts out in the same year is credited contributions/match for the active enrollment window (enrollment effective date → opt-out effective date), while year-end status remains not participating.

**Independent Test**: For a same-year enroll+opt-out employee, year-end snapshot shows not participating with deferral rate 0, AND contributions/match for the active-window days are > 0 (proportional to the enrolled fraction of the year).

**⚠️ Scope note**: `int_employee_contributions` currently prorates by EMPLOYMENT window only (hire→termination), not enrollment window (research.md Decision 4). This phase introduces NEW logic and is flagged for separate design review; year-end status (opt-out wins) is already correct after US1. Do not bundle into the US1 MVP.

### Tests for FR-008 (write FIRST)

- [ ] T017 [P] Add test `dbt/tests/assert_same_year_enroll_optout_window.sql` asserting: year-end `participation_status='not_participating'` and `current_deferral_rate=0` for same-year enroll+opt-out employees, AND their active-window contribution > 0 once implemented. Initially register as severity `warn` (per contracts/ Non-contract) so it does not block the US1–US3 delivery.

### Implementation for FR-008

- [ ] T018 Design and document the active-enrollment-fraction approach in `specs/095-fix-enrollment-snapshot/research.md` (append a "Phase C design" subsection): derive enrolled fraction from enrollment/opt-out effective dates and apply it to the contribution base in `int_employee_contributions`.
- [ ] T019 Implement enrollment-window proration in `dbt/models/intermediate/events/int_employee_contributions.sql` (multiply the contribution base by the enrolled-fraction for same-year enroll+opt-out employees), keeping employment-window proration intact.
- [ ] T020 Rebuild contributions+ and flip T017 test severity to `error`; verify GREEN.

**Checkpoint**: FR-008 fully satisfied (deferred deliverable).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T021 [P] Add/extend descriptions and test docs for `int_deferral_rate_state_accumulator` `is_enrolled_flag` semantics in `dbt/models/intermediate/schema.yml` (document the fixed precedence so the invariant is discoverable).
- [ ] T022 [P] (Optional) Add pytest integration assertion `tests/test_voluntary_enrollment_snapshot.py` (marked `integration`) that builds/queries a multi-year DB and asserts voluntary-enrollee reconciliation, mirroring Contract 1/5 for CI outside dbt.
- [ ] T023 Run full build to confirm no regressions to other enrollment categories: `cd dbt && dbt build --threads 1 --fail-fast` and `pytest -m fast`.
- [ ] T024 Execute the full `specs/095-fix-enrollment-snapshot/quickstart.md` end-to-end (steps 1–6) and confirm all expected post-fix outputs; update `baseline-prefix.txt` companion `baseline-postfix.txt` for the audit trail.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: After Setup. Light (test-location confirmation).
- **US1 (Phase 3)**: After Foundational. The core fix — BLOCKS US2 and US3 propagation/persistence verification.
- **US2 (Phase 4)**: After US1 implementation (T007–T009). Propagation-only.
- **US3 (Phase 5)**: After US1 implementation. Independently testable.
- **FR-008 (Phase 6)**: After US1; independent of US2/US3. Deferred — can ship later.
- **Polish (Phase 7)**: After US1–US3 (Phase 6 optional before/after).

### User Story Dependencies

- **US1 (P1)**: Independent core fix — MVP.
- **US2 (P1)**: Depends on US1 fix (match propagates through the corrected accumulator).
- **US3 (P2)**: Depends on US1 fix (carry-forward path); test independent.

### Within Each User Story

- Tests written and FAILING before implementation (T004/T005 fail → T007/T008 fix → T010 green).
- Model fix before rebuild; rebuild before verification.

### Parallel Opportunities

- T004 and T006 [P] (different files) can be written together; T005 depends on T004.
- T011, T014, T015 [P] test files can be authored in parallel once US1 fix lands.
- T021, T022 [P] in Polish can run together.

---

## Parallel Example: User Story 1 tests

```bash
# Author US1 test artifacts together (different files):
Task: "Create dq_voluntary_enrollment_snapshot.sql (Contract 1)"          # T004
Task: "Create assert_participation_deferral_consistency.sql (Contract 3)" # T006
# Then T005 registers + confirms RED, before the model fix (T007/T008).
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → reproduce defect (T001–T002).
2. Phase 2 Foundational (T003).
3. Phase 3 US1: RED test (T004–T006) → accumulator fix (T007–T008) → rebuild (T009) → GREEN (T010).
4. **STOP and VALIDATE**: voluntary enrollees now participate with correct deferral rate. This alone resolves the user's reported defect.

### Incremental Delivery

1. US1 (MVP) → ship the core fix + permanent regression guard.
2. US2 → verify match propagation (no model change expected).
3. US3 → verify multi-year persistence + reconciliation.
4. FR-008 (Phase 6) → deferred prorated-window enhancement after design review.
5. Polish → full build, docs, audit artifacts.

---

## Notes

- [P] = different files, no dependencies.
- Never `--full-refresh` the temporal accumulators (`int_deferral_rate_state_accumulator`) mid-simulation — it destroys prior-year state.
- The single accumulator fix (T007–T008) resolves deferral rate, participation, AND match (US1 + US2) because all three read from it.
- Verify each test FAILS on the pre-fix DB before applying the model change (TDD Red → Green).
- Commit after each logical group; the regression test (T004/T005) is the permanent FR-010 guard.
