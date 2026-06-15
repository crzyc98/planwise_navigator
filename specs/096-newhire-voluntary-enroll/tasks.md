# Tasks: New Hires Voluntarily Enroll in Their Hire Year

**Feature**: 096-newhire-voluntary-enroll
**Input**: Design documents from `/specs/096-newhire-voluntary-enroll/`
**Prerequisites**: plan.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: REQUIRED — Constitution Principle III (Test-First) and FR-012 mandate a permanent
data-quality regression test. Tasks are ordered test-first within each story.

**Organization**: Tasks grouped by user story (US1/US2/US3 from spec.md) for independent
implementation and testing.

## Conventions

- dbt singular data-quality tests live in `dbt/tests/` as `assert_*.sql` (return 0 rows = pass),
  tagged `data_quality`.
- All dbt commands run from `/dbt` with `--threads 1`.
- Validation scenario DB:
  `workspaces/049771e9-0a4a-44a3-84ce-d9aabd6dbdcf/scenarios/d3ab5ad3-224c-4a30-a1a9-6a123ae09d4d/simulation.duckdb`

---

## Phase 1: Setup

- [X] T001 Capture the failing baseline: run the two reproduction queries in `specs/096-newhire-voluntary-enroll/quickstart.md` against the validation scenario DB and save output to `specs/096-newhire-voluntary-enroll/baseline-prefix.txt` (confirm 0 hire-year new hires in `int_employee_compensation_by_year` and every NH cohort first-enrolls post-hire-year).

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Pin the exact edit points and shared values all stories depend on. No behavior change yet.

- [X] T002 In `dbt/models/intermediate/int_voluntary_enrollment_decision.sql`, annotate the `active_workforce` CTE (the candidate source `FROM int_employee_compensation_by_year`) and the `enrollment_decisions` CTE `proposed_effective_date` CASE as the two change sites; confirm `eligibility_waiting_days` and the `voluntary_enrollment_base_rates_by_age_*` vars are the reusable config (no new vars introduced).

**Checkpoint**: Edit sites identified; no model output changed yet.

---

## Phase 3: User Story 1 - Eligible new hires are part of the hire-year voluntary enrollment population (Priority: P1) 🎯 MVP

**Goal**: Current-year eligible new hires are evaluated for voluntary enrollment at the configured
demographic rate in their hire year; selected ones get a `voluntary_enrollment` event dated on their
eligibility date.

**Independent Test**: Run one start-year simulation with voluntary enrollment enabled and
auto-enrollment disabled; confirm a non-zero, sub-100% share of eligible new hires receive a
`voluntary_enrollment` event dated within their hire year (matching configured demographic rates).

### Tests for User Story 1 (write first — must FAIL on current code)

- [X] T003 [P] [US1] Create `dbt/tests/assert_new_hire_voluntary_enrollment_hire_year.sql` (tag `data_quality`): fail (return rows) for any current-year new hire (`EXTRACT(YEAR FROM employee_hire_date) = simulation_year`) who has a `voluntary_enrollment` event whose `simulation_year` is later than the hire year, OR whose hire-year cohort has zero hire-year voluntary enrollments while later-year enrollments exist. Encodes Contract 2 / VR-1 / VR-4.
- [X] T004 [P] [US1] Create `dbt/tests/assert_new_hire_voluntary_enroll_effective_date.sql` (tag `data_quality`): for hire-year `voluntary_enrollment` events of current-year new hires, assert `effective_date = employee_hire_date + eligibility_waiting_days`. Encodes Contract 1 / VR-2.
- [X] T005 [US1] Run `dbt build --select int_voluntary_enrollment_decision int_enrollment_events fct_yearly_events --vars "simulation_year: 2025" --threads 1` then `dbt test --select assert_new_hire_voluntary_enrollment_hire_year assert_new_hire_voluntary_enroll_effective_date --threads 1`; confirm both tests FAIL against current behavior and record the failure in `specs/096-newhire-voluntary-enroll/baseline-prefix.txt`.

### Implementation for User Story 1

- [X] T006 [US1] In `dbt/models/intermediate/int_voluntary_enrollment_decision.sql`, widen the candidate population: add current-year new hires into `active_workforce` via `UNION`, supplying `employee_id`, `employee_ssn`, `employee_hire_date`, `current_age`, `current_tenure = 0`, `level_id`, `employee_compensation`, `employment_status = 'active'`. De-duplicate against employees already sourced from `int_employee_compensation_by_year` (prefer the compensation-model row when present). **IMPLEMENTATION NOTE**: sourced from `int_hiring_events` (NOT `int_new_hire_compensation_staging` as the plan assumed) — the staging model only emits rows in the start year, whereas `int_hiring_events` is the canonical current-year new-hire source for ALL simulation years and is exactly the pattern already used by `int_enrollment_events.new_hires_current_year`. `int_hiring_events` runs in EVENT_GENERATION before enrollment, so no circular dependency.
- [X] T007 [US1] In the same model, gate new-hire candidates on eligibility within the year: include only rows where `(employee_hire_date + INTERVAL eligibility_waiting_days DAY)` falls on or before the end of the current simulation year (FR-006/FR-007); ensure the existing `current_enrollment_status`/`eligible_employees` not-enrolled & never-opted-out filters still apply to the new rows.
- [X] T008 [US1] In the `enrollment_decisions` CTE, change `proposed_effective_date` for current-year new hires to the eligibility date `CAST(employee_hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY AS TIMESTAMP)` (replacing the `hire_date + auto_enrollment_window_days` branch for the new-hire case), keeping the standard annual date for continuing employees.
- [X] T009 [US1] Run `dbt build --select int_voluntary_enrollment_decision int_enrollment_events fct_yearly_events --vars "simulation_year: 2025" --threads 1`; verify hire-year `voluntary_enrollment` events now exist for a non-zero, sub-100% share of eligible new hires (quickstart query), then rerun T003/T004 tests — both must now PASS.

**Checkpoint**: US1 independently testable — new hires enroll in their hire year at the configured rate. MVP delivered.

---

## Phase 4: User Story 2 - Hire-year voluntary enrollment appears in the hire-year snapshot (Priority: P1)

**Goal**: Hire-year new-hire enrollees show participating, with their deferral rate and employer
match, in the hire-year `fct_workforce_snapshot`.

**Independent Test**: For new hires who enrolled in their hire year, the hire-year snapshot shows
participating status, the enrollment deferral rate, and (non-zero match formula) employer match > 0.

### Tests for User Story 2 (write first)

- [X] T010 [P] [US2] Create `dbt/tests/assert_new_hire_hire_year_snapshot_participating.sql` (tag `data_quality`): fail for any current-year new hire with a hire-year `voluntary_enrollment` event whose hire-year snapshot row is `not_participating`, has zero `current_deferral_rate`, or (under a non-zero match formula) zero `employer_match_amount`. Encodes Contract 3 / VR-5.
- [X] T011 [US2] Run `dbt build --select fct_workforce_snapshot --vars "simulation_year: 2025" --threads 1` then `dbt test --select assert_new_hire_hire_year_snapshot_participating --threads 1`; confirm it FAILS on current behavior.

### Implementation for User Story 2

- [X] T012 [US2] Verify the feature-095 propagation path (`int_enrollment_state_accumulator` → `fct_workforce_snapshot`) consumes the now-present hire-year new-hire enrollment events with no additional change; if hire-year enrollees are still missing from snapshot participation, trace the accumulator join for a tenure/hire-year filter that excludes them and remove that exclusion in `dbt/models/intermediate/int_enrollment_state_accumulator.sql`.
- [X] T013 [US2] Run `dbt build --select int_enrollment_state_accumulator fct_workforce_snapshot --vars "simulation_year: 2025" --threads 1`; rerun T010 — must PASS. Spot-check with the quickstart snapshot join query that hire-year enrollees show participation + deferral rate + match.

**Checkpoint**: US1 + US2 deliver hire-year participation visible in the record of record.

---

## Phase 5: User Story 3 - Hire-year enrollment persists across years without duplication (Priority: P2)

**Goal**: A hire-year enrollee stays participating in later years with no second/delayed enrollment
event.

**Independent Test**: Multi-year run where a new hire enrolls in hire year Y with no later change
events — participating with the same deferral rate every later year, and exactly one enrollment event.

### Tests for User Story 3 (write first)

- [X] T014 [P] [US3] Create `dbt/tests/assert_new_hire_single_enrollment_event.sql` (tag `data_quality`): fail for any new hire with more than one `voluntary_enrollment` event across all simulation years (guards the `prior_year_enrollments` dedup; Contract 2 / VR-1 / SC-005).
- [X] T015 [US3] Run a multi-year build (`planalign simulate 2025-2027`) then `dbt test --select assert_new_hire_single_enrollment_event assert_voluntary_enrollment_persists --threads 1`; confirm starting state and that no Y+1 duplicate is created.

### Implementation for User Story 3

- [X] T016 [US3] Confirm the existing `prior_year_enrollments` guard and `voluntary > proactive > yoy > auto` dedup in `dbt/models/intermediate/int_enrollment_events.sql` correctly suppress a second enrollment for a hire-year enrollee in Y+1; only adjust if T014 fails (no change expected). Re-verify against the feature-095 `assert_voluntary_enrollment_persists.sql`.
- [X] T017 [US3] Run multi-year `planalign simulate 2025-2027 --verbose`; rerun T014 + persistence tests — must PASS; confirm exactly one enrollment event per hire-year enrollee and unchanged deferral rate in subsequent years.

**Checkpoint**: All three stories complete; multi-year correctness verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T018 [P] Run the full enrollment data-quality suite `dbt test --select tag:data_quality --threads 1`; confirm the feature-095 reconciliation tests (`assert_voluntary_enrollment_snapshot`, `assert_voluntary_enrollee_match_nonzero`, `assert_participation_deferral_consistency`) still pass with hire-year enrollees included (FR-009/FR-011, SC-008).
- [X] T019 [P] Add `tests/test_new_hire_voluntary_enrollment.py` (pytest, `fast`/`integration` markers): assert hire-year enrollment share is non-zero and < 100% of eligible new hires, and that two identical seeded runs produce the identical set of hire-year enrollees (FR-010, SC-001, SC-007).
- [X] T020 Run the regression gates `pytest -m "fast and events"` and `dbt build --threads 1 --fail-fast`; capture post-fix validation output to `specs/096-newhire-voluntary-enroll/baseline-postfix.txt` and confirm no other model regressed.
- [X] T021 [P] Apply `black` to any new Python (`tests/test_new_hire_voluntary_enrollment.py`) and confirm new dbt models follow the project SQL style (2-space indent, uppercase keywords, `{{ ref() }}` only).

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002)** → user stories.
- **US1 (T003–T009)** is the core fix and MUST complete before US2 and US3 (snapshot participation and
  persistence depend on hire-year events existing).
- **US2 (T010–T013)** depends on US1.
- **US3 (T014–T017)** depends on US1 (and benefits from US2 for snapshot checks).
- **Polish (T018–T021)** after all stories.

### Story completion order

```
Setup → Foundational → US1 (MVP) → US2 → US3 → Polish
```

## Parallel Execution Examples

- Within US1, test authoring is parallel: `T003` and `T004` ([P], different files).
- Across stories, the test-authoring tasks `T003`, `T004`, `T010`, `T014` are independent files and may
  be drafted together up front (TDD), though each story's run/verify steps follow its implementation.
- Polish `T018`, `T019`, `T021` are parallel ([P], different files/targets).

## Implementation Strategy

- **MVP = User Story 1** (T001–T009): new hires enroll in their hire year at the configured rate. This
  alone resolves the reported defect's core (events generated in the correct year).
- **Incremental**: add US2 (snapshot visibility) then US3 (multi-year persistence + dedup guard), each
  independently testable, before polishing with the full regression suite and pytest determinism check.

## Task Summary

- Total tasks: 21
- Per story: US1 = 7 (T003–T009), US2 = 4 (T010–T013), US3 = 4 (T014–T017)
- Setup/Foundational: 2 (T001–T002); Polish: 4 (T018–T021)
- Parallel opportunities: T003/T004, T010, T014 (test authoring); T018/T019/T021 (polish)
- New regression tests: `assert_new_hire_voluntary_enrollment_hire_year.sql`,
  `assert_new_hire_voluntary_enroll_effective_date.sql`,
  `assert_new_hire_hire_year_snapshot_participating.sql`,
  `assert_new_hire_single_enrollment_event.sql`, plus `tests/test_new_hire_voluntary_enrollment.py`
</content>
