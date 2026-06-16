# Tasks: Tenure Match Tier Bug Fixes

**Input**: Design documents from `/specs/098-tenure-match-tier-bug/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: No test tasks explicitly requested in spec. Verification steps use existing test suite + manual DuckDB queries.

**Organization**: 4 targeted edits across 3 files. No new files. No schema changes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1 or US2)

---

## Phase 1: Setup

**Purpose**: Confirm branch, environment, and exact line locations before editing.

- [x] T001 Verify active branch is `098-tenure-match-tier-bug` (`git branch --show-current`)
- [x] T002 [P] Confirm `export.py` line 35-36 contains the existing `start_year` export in `planalign_orchestrator/config/export.py`
- [x] T003 [P] Confirm `int_workforce_snapshot_optimized.sql` line 13 reads `var('simulation_start_year', 2025)` in `dbt/models/intermediate/int_workforce_snapshot_optimized.sql`
- [x] T004 [P] Confirm `int_workforce_pre_enrollment.sql` line 41 reads `var('simulation_start_year', 2025)` in `dbt/models/intermediate/int_workforce_pre_enrollment.sql`
- [x] T005 [P] Confirm `simulate.py` lines 218 and 228 contain `t.get('max_years','∞')` and line 238 contains `t.get('max_points','∞')` in `planalign_cli/commands/simulate.py`

**Checkpoint**: All exact file locations confirmed before any edits.

---

## Phase 2: Foundational (Blocking Prerequisite)

**Purpose**: Export the `simulation_start_year` alias from the Python config exporter so both dbt models receive the correct value. This unblocks US1 model fixes.

**⚠️ CRITICAL**: US1 model fixes (T007, T008) depend on this being in place for end-to-end verification.

- [x] T006 Add `dbt_vars["simulation_start_year"] = int(cfg.simulation.start_year)` immediately after the `dbt_vars["start_year"]` line in `planalign_orchestrator/config/export.py` (after line 36)

**Checkpoint**: `export.py` now exports both `start_year` and `simulation_start_year` with identical values. Run `pytest -m fast -x` to confirm no regressions.

---

## Phase 3: User Story 1 — Correct Tier Assignment in First Simulation Year (P1) 🎯 MVP

**Goal**: Ensure `int_workforce_snapshot_optimized` takes the Year-1 baseline path when `simulation_year == start_year`, so match calculations receive correct tenure for every employee.

**Independent Test**: After completing T007–T008, run a simulation starting at any year (e.g., 2026) with tenure-based tiers (0–5: 6%, 5–10: 8%, 10+: 10%) and verify in DuckDB:
```sql
SELECT applied_years_of_service, COUNT(*) n
FROM int_employee_match_calculations
GROUP BY 1 ORDER BY 1;
-- Expected: multiple distinct tenure values (NOT all 0)
```

### Implementation for User Story 1

- [x] T007 [P] [US1] Change `var('simulation_start_year', 2025)` to `var('start_year', 2025)` on line 13 of `dbt/models/intermediate/int_workforce_snapshot_optimized.sql`
- [x] T008 [P] [US1] Change `var('simulation_start_year', 2025)` to `var('start_year', 2025)` on line 41 of `dbt/models/intermediate/int_workforce_pre_enrollment.sql`

**Checkpoint**: Both dbt models now use the canonical `start_year` var. With T006 (foundational) in place, the var arrives correctly for every simulation year. Year-1 snapshot reads from `int_baseline_workforce` as intended.

---

## Phase 4: User Story 2 — Infinity Symbol Display in Config Summary (P2)

**Goal**: Config Summary displays `∞` for open-ended tier upper bounds instead of `None`.

**Independent Test**: Run `planalign simulate <years>` with a tenure-based scenario whose final tier has no upper bound. Confirm terminal output shows `10–∞ yrs`, not `10–None yrs`.

### Implementation for User Story 2

- [x] T009 [US2] Replace `t.get('max_years','∞')` with `t.get('max_years') or '∞'` on line 218 (tenure-based tiers) in `planalign_cli/commands/simulate.py`
- [x] T010 [US2] Replace `t.get('max_years','∞')` with `t.get('max_years') or '∞'` on line 228 (graded-by-service tiers) in `planalign_cli/commands/simulate.py`
- [x] T011 [US2] Replace `t.get('max_points','∞')` with `t.get('max_points') or '∞'` on line 238 (points-based tiers) in `planalign_cli/commands/simulate.py`

**Checkpoint**: Config Summary panel renders `∞` for all open-ended tier upper bounds across tenure-based, graded-by-service, and points-based modes.

---

## Phase 5: Polish & Verification

**Purpose**: End-to-end simulation run confirming both bugs are resolved simultaneously.

- [x] T012 Run existing fast test suite: `pytest -m fast -x` — all tests must pass
- [x] T013 Run full existing test suite: `pytest tests/test_analytics_service.py -x` — all tests must pass
- [ ] T014 Execute a 2-year simulation with tenure-based match (start year NOT 2025) and verify:
  - Config Summary shows `∞` for open-ended tier (Bug 2 fix)
  - DuckDB query shows varied `applied_years_of_service` in Year 1 (Bug 1 fix)
  - Year 1 `match_percentage_of_comp` distribution includes values above 0.06 for employees with 5+ years tenure

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — confirm lines before editing
- **Foundational (Phase 2 / T006)**: Depends on Setup — BLOCKS US1 end-to-end verification
- **US1 (Phase 3 / T007–T008)**: T007 and T008 can start immediately (code edits); full verification requires T006
- **US2 (Phase 4 / T009–T011)**: Fully independent — no dependency on Phase 2 or US1
- **Polish (Phase 5)**: Requires all prior phases complete

### User Story Dependencies

- **US1 (P1)**: Independent of US2. Can start after Setup.
- **US2 (P2)**: Independent of US1. Can start after Setup (even in parallel with US1).

### Within Each User Story

- US1: T006 (foundational) → T007 and T008 [parallel] → verify
- US2: T009 → T010 → T011 (all in same file, sequential to avoid conflicts)

### Parallel Opportunities

- All Phase 1 confirmation tasks (T002–T005) run in parallel
- T007 and T008 are different files — run in parallel
- US1 (Phase 3) and US2 (Phase 4) are different files — run in parallel after Setup

---

## Parallel Example: All 4 Code Edits Together

After completing T001–T005 (Setup) and T006 (Foundational):

```bash
# Run in parallel (different files):
Task T007: "Change var name on line 13 of dbt/models/intermediate/int_workforce_snapshot_optimized.sql"
Task T008: "Change var name on line 41 of dbt/models/intermediate/int_workforce_pre_enrollment.sql"
Task T009: "Fix max_years display on line 218 of planalign_cli/commands/simulate.py"
Task T010: "Fix max_years display on line 228 of planalign_cli/commands/simulate.py"
# T011 depends on T010 finishing (same file) — run sequentially after T010
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T005)
2. Complete Phase 2: Foundational (T006) — adds `simulation_start_year` alias to export.py
3. Complete Phase 3: US1 (T007–T008) — fix both dbt models
4. **STOP and VALIDATE**: Run DuckDB query verifying Year-1 varied tenure values
5. If validated, proceed to Phase 4 (Bug 2 is a cosmetic fix, can be done separately)

### Incremental Delivery

1. T001–T005 (Setup) → confirmed line locations
2. T006 (Foundational) → `export.py` exports both var names
3. T007–T008 (US1) → `int_workforce_snapshot_optimized` and `int_workforce_pre_enrollment` fixed
4. T009–T011 (US2) → `simulate.py` displays `∞` correctly
5. T012–T014 (Polish) → verified end-to-end

Total: **14 tasks, ~20 min of implementation**

---

## Notes

- [P] tasks = different files, no shared state conflicts
- All edits are 1-line changes; no new functions, classes, or files
- No dbt model rebuilds needed during implementation — only at verification time
- `simulate.py` edits T009–T011 are in the same file; edit sequentially to avoid conflicts
- Commit after T006 (foundational) and after T008 (US1 complete) and after T011 (US2 complete)
