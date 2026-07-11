# Tasks: Clear Stale Prior-Run State on Scenario Re-Run

**Input**: Design documents from `/specs/108-clear-stale-rerun-state/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the spec mandates regression coverage (FR-009) and the constitution mandates test-first development. Every implementation task is preceded by failing tests.

**Organization**: Tasks are grouped by user story. US1 (purge stale prior-run state) is the MVP; US2 (safe-by-default semantics and configuration precedence) hardens the same mechanism; US3 (participation label lineage) is independent of both.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story the task belongs to (US1, US2, US3)

## Path Conventions

Single-project simulation pipeline at repository root: `planalign_orchestrator/` (Python orchestrator), `dbt/` (models + data tests), `tests/` (pytest). All dbt commands run from `dbt/` with `--threads 1`. All validation uses isolated databases — never `dbt/simulation.duckdb`.

---

## Phase 1: Setup

**Purpose**: Confirm a green baseline so purge-behavior regressions are attributable to this feature.

- [x] T001 Verify baseline: run `pytest -m fast` and `pytest -m integration tests/integration/` green on branch `108-clear-stale-rerun-state`, and inventory existing assertions about omitted-`setup` no-op behavior in tests/unit/orchestrator/test_cleanup_scoping.py and tests/unit/orchestrator/test_pipeline.py that T005 will need to update

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None required — the feature reuses the existing `StateManager._year_scope`/`_delete_year_rows` infrastructure, the per-year cleanup call sites in `pipeline_orchestrator.py:557-558`, and the existing `esa` join in `fct_workforce_snapshot.sql:805`. No new modules, schema, or fixtures are prerequisites.

*(No tasks.)*

---

## Phase 3: User Story 1 — Re-Run Reflects Only Current Configuration (P1) 🎯 MVP

**Goal**: A re-run into an existing scenario database purges every yearly state row for each simulated year before rebuilding it — including rows whose keys the current run never regenerates (the `int_deferral_rate_state_accumulator` delete+insert gap) — so no prior-run row survives or propagates forward.

**Independent Test**: Seed an isolated DuckDB with prior-run-shaped rows (old `created_at`, keys a new run will not regenerate), drive the orchestrator's per-year cleanup with a Studio-shaped config (no `setup` block), and verify zero pre-run rows survive for any simulated year while other-scenario and other-year rows are untouched.

### Tests for User Story 1 (write first, confirm failing)

- [x] T002 [P] [US1] Add failing unit tests in tests/unit/orchestrator/test_cleanup_scoping.py: (a) `maybe_clear_year_data` purges year rows when `config.setup` is absent/None, (b) purges when `setup` dict exists but `clear_tables` key is absent, (c) deletes a stale `int_deferral_rate_state_accumulator` row whose `(employee_id, simulation_year)` key the new run does not regenerate, (d) preserves rows for other simulation years and other scenario_id/plan_design_id values, (e) no-ops without error on a fresh database with no matching tables
- [x] T003 [P] [US1] Add failing integration test tests/integration/test_stale_rerun_purge.py: seed an isolated DuckDB with the issue #419 contamination shape (multi-year `int_deferral_rate_state_accumulator` + `fct_workforce_snapshot` rows with old `created_at`, including never-enrolled employees carrying `rate_source='carried_forward'`, `is_enrolled_flag=true` at 0.03), invoke the per-year cleanup path for each simulated year in order, and assert zero surviving pre-run rows per year (SC-001 shape) and that year N's purge occurs before year N could feed year N+1 (forward-propagation guard, spec US1 scenario 3)

### Implementation for User Story 1

- [x] T004 [US1] Implement default-on year purge in planalign_orchestrator/pipeline/state_manager.py `maybe_clear_year_data` per contracts/default-year-purge.md: treat absent/non-dict `setup` and absent `clear_tables` key as purge-enabled with default patterns `['int_', 'fct_']`; keep explicit falsy `clear_tables` as a no-op opt-out (log at DEBUG); keep `clear_mode: 'all'` deferring to `maybe_full_reset` unchanged; update the method docstring to document the new default and the opt-out
- [x] T005 [US1] Update any existing tests that assert the old omitted-`setup` no-op behavior (per T001 inventory, e.g. in tests/unit/orchestrator/test_cleanup_scoping.py and tests/unit/orchestrator/test_pipeline.py) to the new default-on contract, then run `pytest -m fast tests/unit/orchestrator/ -v` and `pytest -m integration tests/integration/test_stale_rerun_purge.py -v` until green

**Checkpoint**: US1 is a shippable MVP — Studio re-runs (no `setup` block) now purge each simulated year before rebuild; the issue #419 contamination mechanism is closed.

---

## Phase 4: User Story 2 — Re-Runs Without Explicit Cleanup Settings Are Safe (P2)

**Goal**: The default-on purge coexists correctly with every explicit configuration (opt-out, full reset), the full fast suite reflects the new default, and out-of-range stale years are surfaced with a warning instead of silent leakage.

**Independent Test**: With configs covering each row of the contract table (absent setup, explicit `clear_tables: false`, `clear_mode: 'all'`), verify purge/no-purge/full-reset behavior respectively; re-run a shorter year range over a longer prior run and verify a warning names the stale later years without deleting them.

### Tests for User Story 2 (write first, confirm failing)

- [x] T006 [P] [US2] Add failing unit tests in tests/unit/orchestrator/test_cleanup_scoping.py: (a) explicit `clear_tables: false` performs no deletions, (b) `clear_tables: true, clear_mode: 'all'` still skips year-level purging in `maybe_clear_year_data` while `maybe_full_reset` continues to require the explicit pair (never fires by default), (c) explicit `clear_table_patterns` are honored under the default-on path
- [x] T007 [P] [US2] Add failing unit test in tests/unit/orchestrator/test_pipeline.py: after a simulated 2026-2030 "prior run" leaves rows, starting a 2026-2028 run logs a WARNING naming stale years > end_year for the current scenario and deletes nothing outside the simulated range; no warning fires on a clean database; rows with simulation_year < start_year are never inspected or deleted

### Implementation for User Story 2

- [x] T008 [US2] Implement the run-start stale-range warning in planalign_orchestrator/pipeline_orchestrator.py `execute_multi_year_simulation` (after the `maybe_full_reset` call at ~line 290): scenario-scoped existence check for `simulation_year > end_year` rows in the critical fact tables, WARNING recommending `setup.clear_tables: true, clear_mode: 'all'`, tolerant of missing tables per contracts/default-year-purge.md
- [x] T009 [US2] Document the new default, the explicit opt-out, and re-run guidance in docs/guides/error_troubleshooting.md (stale-state symptom → purge default → full-reset recommendation), and run `pytest -m fast -v` full suite green

**Checkpoint**: All configuration paths behave per the contract table; the shorter-re-run edge case warns; full fast suite green under the new default.

---

## Phase 5: User Story 3 — Participation Labels Reflect True Enrollment Lineage (P3)

**Goal**: `'participating - census enrollment'` is asserted only when the enrollment state accumulator shows `enrollment_source = 'baseline'`; unexplained participation surfaces as `'participating - unknown source'` instead of masquerading as census enrollment.

**Independent Test**: In an isolated DB, construct snapshot inputs where an employee has `current_deferral_rate > 0` but no baseline-source enrollment state, build `fct_workforce_snapshot`, and verify the row is labeled `'participating - unknown source'`; a genuine baseline-enrolled employee keeps `'participating - census enrollment'`.

### Tests for User Story 3 (write first, confirm failing)

- [x] T010 [P] [US3] Add failing dbt data test dbt/tests/test_participation_label_lineage.sql per contracts/participation-label-lineage.md: select rows from `fct_workforce_snapshot` where `participation_status_detail = 'participating - census enrollment'` and the matching `int_enrollment_state_accumulator` row is absent or has `enrollment_source <> 'baseline'` (test passes when zero rows)

### Implementation for User Story 3

- [x] T011 [US3] Tighten the participating-branch CASE in dbt/models/marts/fct_workforce_snapshot.sql (~lines 707-715): census label requires `esa.enrollment_method IS NULL AND esa.enrollment_source = 'baseline'`; remaining NULL-method cases fall to new label `'participating - unknown source'`; auto/voluntary/other branches and the not-participating branch unchanged
- [x] T012 [P] [US3] Grep Studio/analytics consumers of `participation_status_detail` string literals (planalign_studio/, planalign_api/, dbt/models/marts/) and extend any exact-string enumeration/bucketing to display `'participating - unknown source'`; record findings (or "none") in specs/108-clear-stale-rerun-state/research.md under R5
- [x] T013 [US3] From dbt/: `dbt compile --select fct_workforce_snapshot --threads 1`, then build an isolated validation DB per quickstart.md §4 prerequisites and run `dbt test --select test_participation_label_lineage --threads 1` green (use `DATABASE_PATH` to target the isolated DB, never dbt/simulation.duckdb)

**Checkpoint**: Label lineage enforced by a dbt invariant; anomalous participation is diagnosable instead of disguised.

---

## Phase 6: Polish & End-to-End Validation

**Purpose**: Prove the literal issue #419 recipe end-to-end and reconcile spec criteria.

- [x] T014 Execute quickstart.md §4 in an isolated database: full `planalign simulate 2026-2030` with AE on, re-run same DB with AE off, and assert SC-001 (zero deferral-state rows predate run 2), SC-002 (zero participating rows without enrollment-state support), SC-003 (zero census labels without baseline lineage), and SC-004 (repeat run 2 with identical config+seed produces identical participation counts); record results in specs/108-clear-stale-rerun-state/quickstart.md
- [x] T015 Run the full suites (`pytest -m fast`, `pytest -m integration`) green, reconcile FR-001..FR-010 and SC-001..SC-005 against the implementation, and note any limitation (e.g., out-of-range years warn rather than delete) in specs/108-clear-stale-rerun-state/spec.md Assumptions

---

## Dependencies

```
Phase 1 (T001)
   │
   ▼
Phase 3 / US1 (MVP): T002, T003 [P] ──► T004 ──► T005
   │
   ▼
Phase 4 / US2: T006, T007 [P] ──► T008 ──► T009      (depends on US1's default-on semantics)

Phase 5 / US3: T010 [P] ──► T011 ──► T013            (independent of US1/US2; can start after T001)
                T012 [P] (parallel with T011)
   │
   ▼
Phase 6: T014 (needs US1+US2+US3 merged into branch) ──► T015
```

- **US1 → US2**: US2's precedence/opt-out tests exercise the default-on code written in T004.
- **US3 is independent**: dbt-only change; can proceed in parallel with US1/US2 after T001.
- **T014/T015** require all three stories complete.

## Parallel Execution Examples

- **US1**: T002 and T003 in parallel (different test files), then T004 alone (single source file), then T005.
- **US2**: T006 and T007 in parallel (different test files), then T008, then T009.
- **US3 alongside US1/US2**: T010 + T012 in parallel with any US1/US2 task (dbt/tests, planalign_studio grep vs. orchestrator files); T011 in parallel with orchestrator implementation tasks (different files).

## Implementation Strategy

**MVP first**: Ship US1 alone if needed — the T004 default-on purge closes the contamination mechanism for every Studio re-run with zero config/API changes. US2 adds configuration-precedence hardening and the stale-range warning; US3 adds the diagnostic label. Each checkpoint leaves the branch releasable: fast suite green, no schema migrations, behavior change confined to the documented default.
