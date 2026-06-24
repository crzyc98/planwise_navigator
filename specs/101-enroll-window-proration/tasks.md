---
description: "Task list for Same-Year Enroll → Opt-Out Window Proration"
---

# Tasks: Prorate Contributions & Match for Same-Year Enroll → Opt-Out Window

**Input**: Design documents from `/specs/101-enroll-window-proration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — Constitution Principle III (Test-First) is mandatory for this repo. The dbt guard + schema tests precede the crediting implementation.

**Organization**: Tasks grouped by user story (US1 → US3, priority order). US1 is the foundation; US2/US3 build on it.

## Path Conventions

dbt-only change. Models in `dbt/models/intermediate/events/`, schema in `dbt/models/intermediate/schema.yml`, singular test in `dbt/tests/`. Validate via isolated `DATABASE_PATH` DBs and `planalign simulate`, never the shared `dbt/simulation.duckdb`. See `quickstart.md`.

---

## Phase 1: Setup

**Purpose**: Validation scaffolding.

- [X] T001 [P] Create an isolated validation scenario (`scenarios/enroll_optout.yaml` or a `/tmp/run101/cfg.yaml`) that produces voluntary enrollments **and** same-year opt-outs (voluntary enrollment enabled, non-zero opt-out rates), per `quickstart.md` step 1.
- [X] T002 [P] Build it once into an isolated DB (`DATABASE_PATH=/tmp/run101/iso.duckdb planalign simulate 2025-2027 …`) and run the `quickstart.md` step 2 query to confirm at least one same-year enroll→opt-out employee exists (otherwise tune the config).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The data-quality guard, created at non-blocking `warn` severity, so it can be authored before the fix and flipped to enforcing in US3.

⚠️ Create before US1 implementation so the failing invariant is visible.

- [X] T003 Create `dbt/tests/assert_same_year_enroll_optout_window.sql` per `data-model.md`: for same-year enroll→opt-out employee-years, assert year-end `participation_status='not_participating'` AND `current_deferral_rate=0` AND `annual_contribution_amount > 0`. Register at severity `warn` in `dbt/models/intermediate/schema.yml` (or test config) so it does not block until US3.

**Checkpoint**: Guard runs and (pre-fix) reports the contribution-zero violations as warnings.

---

## Phase 3: User Story 1 — Active-window contributions (Priority: P1) 🎯 MVP

**Goal**: Credit same-year enroll→opt-out employees a non-zero employee contribution proportional to their active-enrollment window, using the enrollment-event deferral rate; year-end status unchanged.

**Independent Test**: In the isolated DB, a chosen enroll→opt-out employee has `annual_contribution_amount > 0` and proportional to the enrolled fraction, while their year-end snapshot shows not-participating / rate 0 (`quickstart.md` steps 3–4).

### Tests (write/observe first)

- [X] T004 [US1] Confirm the guard (T003) currently **fails/warns** for the enroll→opt-out employee in the isolated DB (contribution == 0 pre-fix) — this is the red state US1 must turn green.

### Implementation (`dbt/models/intermediate/events/int_employee_contributions.sql`)

- [X] T005 [US1] Add an `enroll_optout_windows` CTE reading `fct_yearly_events` for `simulation_year`: per employee, capture the enrollment event `effective_date` (window start), the opt-out `enrollment_change` event `effective_date` (window end), and parse the enrollment-window deferral rate via `REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1)/100.0` (fallback 0.06), matching `int_deferral_rate_state_accumulator`. Flag `is_same_year_enroll_optout` (both events present AND year-end not enrolled).
- [X] T006 [US1] Compute `active_enrollment_days` = `GREATEST(0, DATEDIFF('day', window_start, window_end) + 1)` intersected with the existing employment window (year-start/hire → termination/year-end); guard degenerate/out-of-order windows to 0 (FR-007).
- [X] T007 [US1] Set `effective_annual_deferral_rate` = the window deferral rate for `is_same_year_enroll_optout` rows (else unchanged), and compute `total_contribution_base_compensation` = `prorated_annual_compensation × (active_enrollment_days / employed_days)` for those rows (else `= prorated_annual_compensation`). **Leave `prorated_annual_compensation` unchanged** (research R4).
- [X] T008 [US1] Recompute `annual_contribution_amount` from `total_contribution_base_compensation × effective_annual_deferral_rate`, preserving the existing IRS 402(g) `LEAST(..., limit)` capping. Add audit columns `active_enrollment_days` and `contribution_window_category` (`'enroll_optout_window' | 'full_year' | 'partial_year'`).

### Validation

- [X] T009 [US1] Rebuild the isolated DB and run `quickstart.md` step 3: confirm `annual_contribution_amount > 0`, `total_contribution_base_compensation < prorated_annual_compensation` (and comp itself unchanged), and SC-002 proportionality (within tolerance of enrolled-days/employed-days × full-window).
- [X] T010 [US1] Run `quickstart.md` step 4: year-end snapshot still `not_participating` / rate 0 (FR-005/SC-003). Run step 7: degenerate windows yield `0`, never negative (FR-007).

**Checkpoint**: US1 independently shippable — the $0 defect is fixed; match still derives from the old base (US2 makes it consistent).

---

## Phase 4: User Story 2 — Employer match follows the active window (Priority: P1)

**Goal**: Employer match for enroll→opt-out employees reflects the active-window contributions and the configured match formula.

**Independent Test**: For the same employee, employer match is `> 0` and consistent with the windowed contribution; non-opt-out employees show no match change (`quickstart.md` step 3, match line).

### Implementation (`dbt/models/intermediate/events/int_employee_match_calculations.sql`)

- [X] T011 [US2] Change the `eligible_compensation` source from `ec.prorated_annual_compensation` to `ec.total_contribution_base_compensation` (deferral_rate already carries the window rate from US1). No change for non-opt-out employees (the two columns are equal there). Verify all match modes still compile (deferral_based, graded_by_service, tenure_based, tenure_graded, points_based).

### Validation

- [X] T012 [US2] In the isolated DB, confirm `employer_match_amount > 0` for the enroll→opt-out employee and consistent with `annual_contribution_amount` + the active formula (SC-004). With a no-match config, match is 0 without error (acceptance #2).
- [X] T013 [P] [US2] Confirm a non-opt-out enrollee's match is identical to a pre-change baseline (no regression, SC-005).

**Checkpoint**: Contributions and match are internally consistent for the active window.

---

## Phase 5: User Story 3 — Reconciliation guard enforcing (Priority: P2)

**Goal**: The guard moves from advisory to enforcing so the fix can't silently regress.

**Independent Test**: Guard passes at `error` severity on a representative multi-year isolated run; temporarily reverting the crediting fails the build.

- [X] T014 [US3] Flip `assert_same_year_enroll_optout_window` to severity `error` in `dbt/models/intermediate/schema.yml` (or test config).
- [X] T015 [US3] Run `dbt test --select assert_same_year_enroll_optout_window` against the isolated DB across years; confirm it passes. Temporarily revert T008's crediting locally and confirm the build fails, then restore (SC-006).

**Checkpoint**: Behavior protected permanently.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T016 [P] Document the new/changed columns (`total_contribution_base_compensation` semantics, `active_enrollment_days`, `contribution_window_category`) in `dbt/models/intermediate/schema.yml` with bounds tests: `total_contribution_base_compensation` ≤ `prorated_annual_compensation` and ≥ 0; `annual_contribution_amount` ≥ 0 (contract invariants 1–2).
- [X] T017 [P] Backward-compatibility regression: confirm aggregate contributions/match for a scenario with **no** same-year opt-outs are byte-identical to a pre-change baseline build (FR-006/SC-005).
- [ ] T018 [P] Reproducibility: same scenario + seed twice → identical contribution/match outputs (FR-009 determinism).
- [X] T019 Multi-year check (FR-009): an enroll→opt-out cycle in year N is credited for N's window without affecting other years' contributions for that employee.
- [X] T020 Run `cd dbt && dbt build --threads 1 --fail-fast` against the isolated DB to confirm the full pipeline (incl. the enforcing guard and downstream comp/match/snapshot models) is green before PR.

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: T001–T002, both [P]. Needed to validate everything.
- **Foundational (Phase 2)**: T003 guard at `warn` — author before US1.
- **US1 (Phase 3)**: depends on Setup + T003. T005→T006→T007→T008 are sequential (same file, building CTE→columns); T009/T010 validate. **MVP.**
- **US2 (Phase 4)**: depends on US1 (reads `total_contribution_base_compensation`). T011 then T012; T013 [P].
- **US3 (Phase 5)**: depends on US1+US2 (guard must pass green). T014→T015.
- **Polish (Phase 6)**: after the stories it validates; T016/T017/T018 [P].

### Story independence

- US1 is the foundation (fixes the defect with default match still on the old base).
- US2 is a one-line source change that makes match consistent; independently testable via the match line.
- US3 is a severity flip + regression proof.

## Parallel Execution Examples

- **Phase 1**: T001 ∥ T002 (after T001 produces the config).
- **US2**: T011 (impl) then T012; T013 [P] alongside T012.
- **Polish**: T016 ∥ T017 ∥ T018.

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + US1 (T001–T010)**: eliminates the $0 contribution defect for same-year enroll→opt-out employees; independently shippable.
- **Increment 2 = US2 (T011–T013)**: make employer match consistent with the windowed contribution.
- **Increment 3 = US3 (T014–T015)**: enforce the guard.
- **Finalize = Phase 6**: schema docs/tests, regression/reproducibility/multi-year, full build.
