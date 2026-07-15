# Tasks: Multi-Year Invariant Suite + Determinism Test

**Input**: Design documents from `/specs/113-invariants-determinism/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/invariant-catalog.md, contracts/ci-interface.md, quickstart.md

**Tests**: This feature's deliverable *is* a test suite; there are no separate test-writing tasks. The red-step equivalent is the seeded-defect validation tasks (T017–T019, T026), per research.md R7 and Constitution III.

**Organization**: Grouped by user story. US1 = invariant suite gating merges (MVP), US2 = determinism double-run, US3 = local developer loop ergonomics.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3 per spec.md

## Phase 1: Setup

**Purpose**: Package scaffolding and pytest wiring shared by all stories

- [X] T001 Register the `multi_year_invariants` pytest marker in `pyproject.toml` (markers section, alongside existing `fast`/`integration` markers)
- [X] T002 [P] Create `tests/invariants/__init__.py` package scaffold with a module docstring pointing at `specs/113-invariants-determinism/contracts/invariant-catalog.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The reference census, fixed config, and single-simulation fixture that every story consumes

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Write `scripts/generate_invariant_census.py`: deterministic generator (fixed numpy seed, no CSPRNG) producing ~150 employees satisfying every data-model.md coverage rule (all age/tenure bands ≥5, all job levels ≥3, ≥30 enrolled-at-census, ≥30 never-enrolled, ≥5 hires each side of the AE cutoff, ≥1 pre-simulation termination, ≥2 `auto_escalation_opt_out=true`, a few part-time rows); columns must match the `stg_census_data.sql` schema scaffold (see data-model.md table)
- [X] T004 Run the generator and commit the output as `tests/fixtures/invariant_census.csv`; spot-check it loads via `duckdb -c "SELECT COUNT(*) FROM read_csv_auto('tests/fixtures/invariant_census.csv')"`
- [X] T005 [P] Create `tests/fixtures/invariant_config.yaml` per research.md R3: years 2025–2027, pinned `random_seed`, auto-enrollment ON with a hire-date cutoff splitting the census, auto-escalation ON with a cap that binds by 2027, multi-tier match, positive `target_growth_rate`; verify it loads cleanly through `load_simulation_config`
- [X] T006 Implement `tests/fixtures/invariant_simulation.py`: (a) session-scoped fixture converting the CSV to parquet under `tmp_path_factory` and injecting `census_parquet_path`; (b) session-scoped `invariant_run_db` fixture that sets `DATABASE_PATH` to a tmp file and executes `create_orchestrator(config).execute_multi_year_simulation(2025, 2027)` exactly once; (c) on simulation failure, record the orchestrator exception so dependent tests **skip with the error context** (FR-014), never fail as invariant violations; (d) on any test failure in the session, copy the DB(s) to `var/test-artifacts/113/` (FR-012/FR-013)
- [X] T007 Add a census coverage self-test in `tests/fixtures/invariant_simulation.py` (or `tests/integration/test_multi_year_invariants.py::test_census_coverage`) that re-asserts every T003 coverage rule against the checked-in CSV, so future census edits can't silently defang the invariants (FR-001)

**Checkpoint**: `pytest -m multi_year_invariants` (with only the coverage self-test present) runs one full 3-year simulation into an isolated tmp DB and passes

---

## Phase 3: User Story 1 — Cross-Year Regression Caught Before Merge (Priority: P1) 🎯 MVP

**Goal**: Named invariants evaluated against the built DB, failing with row-level diagnostics, blocking PRs in CI

**Independent Test**: Revert the #418 fix on a scratch branch → suite fails naming `enrollment-census-persistence`; revert → passes (spec acceptance 1.1–1.5)

- [X] T008 [P] [US1] Implement the `Invariant` dataclass and `CATALOG` registry in `tests/invariants/catalog.py` per data-model.md (name, description, guarded_issue, violation_sql, sample_limit=20); names must match contracts/invariant-catalog.md exactly (append-only contract)
- [X] T009 [P] [US1] Write invariants 1–3 in `tests/invariants/queries.py`: `event-uniqueness` (duplicate `event_id` across all years), `enrollment-no-duplicate` (two enrollments without intervening opt-out), `enrollment-census-persistence` (census-enrolled employee later non-enrolled with no explaining event — #418 guard); each query returns violating rows led by `employee_id`, `simulation_year`
- [X] T010 [P] [US1] Write invariants 4–5 in `tests/invariants/queries.py`: `continuity-headcount` (ending actives Y ≠ starting actives Y+1 — #419 guard) and `continuity-no-zombie` (active after termination without rehire)
- [X] T011 [P] [US1] Write invariants 6–7 in `tests/invariants/queries.py`: `snapshot-explained-by-events` (snapshot enrollment/deferral disagrees with event replay + census baseline) and `snapshot-no-foreign-rows` (rows outside the run's years/scenario/plan ids — #419 guard)
- [X] T012 [P] [US1] Write invariant 8 in `tests/invariants/queries.py`: `growth-exactness` — read the E077 solver's expected headcount rule (see `planalign_orchestrator` growth solver and Feature 105 notes) and assert per-year ending headcount matches it exactly under its documented rounding rule (FR-007)
- [X] T013 [P] [US1] Write invariants 9–11 in `tests/invariants/queries.py`: `deferral-explained-changes`, `deferral-cap-respected`, `deferral-optout-not-escalated` (FR-008), reading `fct_workforce_snapshot`/accumulators vs `fct_yearly_events`
- [X] T014 [US1] Implement `tests/integration/test_multi_year_invariants.py`: parametrize over `CATALOG` (`ids=lambda i: i.name`), execute each `violation_sql` read-only against `invariant_run_db`, and on violation render invariant name, description, guarded issue, violation count, and ≤`sample_limit` rows (FR-011); mark all tests `integration` + `multi_year_invariants` (depends on T008–T013)
- [X] T015 [US1] Verify the full invariant pass is green locally: `pytest -m multi_year_invariants -v` from a clean checkout; fix any invariant query that false-positives against correct current behavior (distinguish spec bug vs product bug before changing either — if a real product defect surfaces, file it and decide with the user whether it blocks)
- [X] T016 [US1] Add the `multi-year-invariants` job to `.github/workflows/ci.yml` per contracts/ci-interface.md: same setup steps as existing jobs (checkout, Python 3.11, uv + cache), run `pytest -m multi_year_invariants -v`, `actions/upload-artifact` of `var/test-artifacts/113/` with `if: failure()` and ≥7-day retention, job `timeout-minutes: 20`; then add it to the repo's required status checks (FR-012)
- [X] T017 [US1] Seeded-defect validation A (SC-001): on a scratch branch, `git revert 7f42aa24` (#418 fix), run the suite, confirm `enrollment-census-persistence` fails with a diagnostic sufficient per SC-005; capture the output for the PR description; delete the branch
- [X] T018 [US1] Seeded-defect validation B (SC-001): on a scratch branch, `git revert cf5e57e5` (#419 fix), run the suite, confirm a continuity/stale-state invariant (`continuity-headcount` or `snapshot-no-foreign-rows`) fails; capture output; delete the branch
- [X] T019 [US1] If either seeded defect passes undetected, strengthen the corresponding `violation_sql` in `tests/invariants/queries.py` and re-run T017/T018 until both fail as required (this task is the loop guard; skip if T017–T018 fail correctly on first try)

**Checkpoint**: Invariant suite green on `main`-equivalent code, red on both reverted fixes, and wired as a blocking CI check — MVP complete

---

## Phase 4: User Story 2 — Reproducibility Is Enforced, Not Just Promised (Priority: P2)

**Goal**: Same config+seed twice ⇒ identical `fct_yearly_events` and `fct_workforce_snapshot` modulo the documented exempt list

**Independent Test**: Inject an unseeded random draw into one event model on a scratch branch → determinism test fails naming the table with differing-row samples (spec acceptance 2.1–2.4)

- [X] T020 [P] [US2] Implement `tests/invariants/comparison.py`: `ExemptField` records (initial list per contracts: `fct_yearly_events.created_at` with justification; snapshot build-timestamp column — confirm its exact name from `dbt/models/marts/fct_workforce_snapshot.sql` and update the contract file if it differs; `run_metadata` whole-table exclusion) and a `compare_tables(db_a, db_b, table, exempt)` function using read-only `ATTACH` + row-count equality + symmetric `EXCEPT` over the non-exempt projection, returning `(count_a, count_b, diff_count, sample_rows≤20)` ordered by (simulation_year, employee_id, event_sequence/event_type) per research.md R5
- [X] T021 [US2] Extend `tests/fixtures/invariant_simulation.py` with a second session-scoped fixture `invariant_run_db_b`: identical config + seed + census parquet, separate `DATABASE_PATH` tmp file, second `execute_multi_year_simulation(2025, 2027)`; reuse the FR-014 skip-on-simulation-failure and failure-artifact behavior from T006
- [X] T022 [US2] Implement `tests/integration/test_determinism.py`: one test per compared table (`fct_yearly_events`, `fct_workforce_snapshot`) calling `compare_tables`; failure message includes table name, both counts, diff count, and the sample rows (FR-009, FR-011); marked `integration` + `multi_year_invariants` so the existing CI job picks them up with no workflow change
- [X] T023 [US2] Run the double-run comparison locally. If differences appear in non-exempt fields: diagnose each as either (a) a product nondeterminism bug — fix it in the responsible model/module as part of this feature (likely suspects: unordered aggregation, wall-clock leakage into payloads, unseeded randomness), or (b) a legitimate run-bookkeeping field — add it to the exempt list in `tests/invariants/comparison.py` **and** the table in `specs/113-invariants-determinism/contracts/invariant-catalog.md` with justification in the same commit (FR-010). `event_id` may NOT be exempted without explicit user sign-off
- [X] T024 [US2] Document the final exempt-field list with justifications in `tests/invariants/comparison.py` module docstring and confirm contracts/invariant-catalog.md matches (acceptance 2.4)
- [X] T025 [US2] Confirm suite runtime with both simulations stays within budget: <10 min locally (`pytest -m multi_year_invariants --durations=10`), <15 min in the CI job (SC-002); if over budget, shrink census toward 100 employees (re-running T004/T007 coverage rules) before any other optimization
- [ ] T026 [US2] Seeded-nondeterminism validation (SC-001 analog, research R7c): on a scratch branch, make one event model draw unseeded randomness (e.g., replace a seeded hash input with `random()` in one `int_*_events` model), run the determinism tests, confirm failure names the affected table with row samples; capture output; delete the branch

**Checkpoint**: Determinism enforced in the same CI job; exempt list documented and minimal

---

## Phase 5: User Story 3 — Fast Local Feedback for the Development Loop (Priority: P3)

**Goal**: One documented command, clean isolation, tidy cleanup

**Independent Test**: On a clean checkout, `pytest -m multi_year_invariants -v` passes in <10 min and `dbt/simulation.duckdb` is byte-identical before/after (spec acceptance 3.1–3.2)

- [X] T027 [P] [US3] Add a guard test in `tests/integration/test_multi_year_invariants.py` asserting the suite never touched the shared dev DB: record `dbt/simulation.duckdb` mtime+size (or hash) in a session fixture before the simulations and compare after (SC-004); if the file is absent, the guard passes trivially
- [X] T028 [P] [US3] Verify cleanup behavior: tmp DBs are removed by pytest tmp retention on pass and copied to `var/test-artifacts/113/` only on failure; ensure `var/test-artifacts/` is covered by the existing `var/` git-ignore (FR-013)
- [ ] T029 [US3] Documentation: add a "Multi-Year Invariant Suite" subsection to `tests/TEST_INFRASTRUCTURE.md` (command, marker, fixture locations, how to add an invariant, exempt-field policy — condensed from `specs/113-invariants-determinism/quickstart.md`) and a one-line pointer in `tests/README.md`

**Checkpoint**: All three stories complete and independently verified

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T030 [P] Retire superseded prior art: review `tests/conservation_employee_state_by_year.sql` and `tests/test_deterministic_behavior.sql`; delete each only if its checks are fully subsumed by the new catalog (map check-by-check in the PR description), otherwise port the gap into `tests/invariants/queries.py` first
- [ ] T031 [P] Run `ruff` and the fast suite (`pytest -m fast`) to confirm no regressions from marker/pyproject changes; confirm the fast suite runtime is untouched (Constitution: fast suite <10s)
- [ ] T032 Walk `specs/113-invariants-determinism/quickstart.md` end-to-end verbatim on a clean checkout and fix any drift between the doc and reality
- [ ] T033 Open PR: description includes the T017/T018/T026 seeded-defect outputs (SC-001/SC-005 evidence), the final exempt-field table, and local + CI runtimes (SC-002); PR closes #435 and #436

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: none — start immediately; T001 and T002 are parallel
- **Phase 2 (Foundational)**: T003 → T004 → (T006, T007); T005 parallel with T003/T004; T006 needs T004+T005 — **blocks all stories**
- **Phase 3 (US1)**: T008–T013 all parallel after Phase 2; T014 after T008–T013; T015 after T014; T016 after T015; T017/T018 after T016 (need the runnable suite; parallel with each other); T019 conditional
- **Phase 4 (US2)**: T020 parallel with all of Phase 3; T021 needs T006; T022 needs T020+T021; T023→T024→T025 sequential after T022; T026 after T022
- **Phase 5 (US3)**: T027/T028 parallel, need T006 (T027 is strongest after both sims exist, i.e., after T021); T029 after Phases 3–4 stabilize the interfaces it documents
- **Phase 6 (Polish)**: after all stories; T030/T031 parallel; T032 then T033 last

### User Story Dependencies

- **US1**: independent (MVP) — needs only Phase 2
- **US2**: independent of US1's invariants but shares Phase 2 fixtures and reuses US1's CI job (T016); it can be developed in parallel and land second
- **US3**: needs Phase 2; its guard tests are most meaningful once US1/US2 tests exist

### Parallel Opportunities

- Largest fan-out: **T008–T013** (six independent query/catalog files-sections) plus **T020** — seven parallel work items immediately after Phase 2
- T005 alongside T003/T004 during Phase 2
- T017 ∥ T018 (separate scratch branches)
- T027 ∥ T028 ∥ T029-prep

## Implementation Strategy

**MVP first**: Phases 1–3 alone deliver the merge-blocking invariant suite (US1) with proven #418/#419 detection — stop, validate, and optionally land that PR before continuing. Phase 4 rides the same fixtures and CI job. Phase 5–6 are small finishing passes. Single-developer sequential path: T001→T007 (~foundation), then invariants in catalog order, then determinism, then polish. Biggest schedule risk is T023 (a real nondeterminism bug in the product would expand scope); surface it to the user immediately rather than silently fixing something large.

## Task Summary

- **Total**: 33 tasks — Setup 2, Foundational 5, US1 12, US2 7, US3 3, Polish 4
- **MVP scope**: Phases 1–3 (T001–T019)
- **Format check**: all tasks have checkbox + ID; [P] on parallelizable tasks; [US#] labels on story-phase tasks only; every task names concrete file paths or commands
