# Tasks: Tenure-Graded Multi-Tier Employer Match Formula

**Input**: Design documents from `/specs/099-tenure-graded-match/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/config-schema.md, quickstart.md

**Tests**: Included — Constitution Principle III (Test-First Development) mandates tests written before implementation for all significant features. Python/Pydantic and dbt tests are included; no frontend test task is included because the Studio app (`planalign_studio/`) has no test runner configured (no `vitest`/`jest` in `package.json`) — UI verification instead uses the manual `quickstart.md` steps.

**Organization**: Tasks are grouped by user story (US1/US2/US3 from spec.md) to enable independent implementation and testing of each story.

## Path Conventions

This is the existing Fidelity PlanAlign Engine monorepo (no new projects). Paths used below:
- `planalign_orchestrator/config/` — Pydantic config models
- `dbt/macros/`, `dbt/models/intermediate/events/`, `dbt/tests/data_quality/` — dbt layer
- `planalign_studio/components/config/` — React/TypeScript Studio UI
- `planalign_api/routers/` — FastAPI workspace routes
- `tests/` — Python pytest suite

---

## Phase 1: Setup

**Purpose**: Scaffold the new files this feature introduces (per plan.md's Constitution Principle II mitigation: new dedicated files instead of growing already-large existing files).

- [X] T001 [P] Create `planalign_orchestrator/config/tenure_graded_match.py` with module docstring referencing this feature and the data-model.md entities it will hold
- [X] T002 [P] Create `dbt/macros/get_tenure_graded_match_tiers.sql` with the macro signature `{% macro get_tenure_graded_match_tiers(tenure_graded_bands) %}` and a docstring comment describing the contract from `contracts/config-schema.md` (band_min_years/band_max_years/employee_min/employee_max/match_rate output columns)
- [X] T003 [P] Create `planalign_studio/components/config/TenureGradedMatchEditor.tsx` with an empty functional component shell (props placeholder for bands list + onChange handler)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core config model, validation, and mode registration that every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `'tenure_graded'` to the `_VALID_MATCH_STATUSES` tuple in `planalign_orchestrator/config/workforce.py`, keeping `'tenure_based'` recognized for reading legacy saved configs (per `contracts/config-schema.md` migration-window note)
- [X] T005 Implement `TenureBandMatchTier` Pydantic model in `planalign_orchestrator/config/tenure_graded_match.py` with `employee_min`, `employee_max`, `match_rate` fields and bounds per `data-model.md` (`employee_min >= 0`, `employee_max > employee_min` and `<= 1`, `match_rate` in `[0, 2.0]`)
- [X] T006 Implement `TenureGradedMatchBand` Pydantic model in `planalign_orchestrator/config/tenure_graded_match.py` with `min_years`, `max_years` (Optional), `tiers: List[TenureBandMatchTier]` fields, plus a `model_validator(mode="after")` that requires `tiers` non-empty and calls `validate_tier_contiguity()` (imported from `workforce.py`) with `min_key="employee_min"`, `max_key="employee_max"`, `label="tenure-graded tier"`
- [X] T007 Add `tenure_graded_bands: List[TenureGradedMatchBand] = Field(default_factory=list)` to `EmployerMatchSettings` in `planalign_orchestrator/config/workforce.py`, and extend its existing `validate_match_mode()` model_validator to require a non-empty list and call `validate_tier_contiguity()` with `min_key="min_years"`, `max_key="max_years"`, `label="tenure-graded band"` when `employer_match_status == 'tenure_graded'` (depends on T004, T006)
- [X] T008 Implement a backward-compatibility migration helper `migrate_legacy_tenure_based_config(employer_match_status: str, tenure_match_tiers: list) -> tuple[str, list]` in `planalign_orchestrator/config/tenure_graded_match.py` that converts a legacy `employer_match_status='tenure_based'` + single-tier `tenure_match_tiers` config into `('tenure_graded', [TenureGradedMatchBand(...)])` per the one-tier mapping documented in `contracts/config-schema.md`'s Backward-compatibility contract (depends on T005, T006)

**Checkpoint**: Foundation ready — config models exist, validate correctly, and legacy configs can be migrated. User story implementation can now begin.

---

## Phase 3: User Story 1 - Configure a tenure-graded, multi-tier match formula (Priority: P1) 🎯 MVP

**Goal**: An analyst can configure tenure bands (e.g., under 10 years / 10+ years), each with its own multi-tier deferral schedule, and the system calculates the correct match amount per employee per simulation year.

**Independent Test**: Configure two tenure bands via `config/simulation_config.yaml` + dbt vars, run `planalign simulate 2025`, and confirm `fct_employer_match_events` match amounts equal the expected formula result for sample employees (per `quickstart.md`).

### Tests for User Story 1 ⚠️

> Write these tests FIRST; confirm they FAIL before implementing T013-T015.

- [X] T009 [P] [US1] Unit tests for `TenureBandMatchTier`/`TenureGradedMatchBand` validation (valid single-tier band, valid multi-tier band, tier list not starting at 0, tier gap, tier overlap, empty tiers list rejected) in `tests/test_match_modes.py`
- [X] T010 [P] [US1] Unit tests for `EmployerMatchSettings.tenure_graded_bands` cross-band validation (valid 2-band contiguous config matching the spec's example, band gap rejected, band overlap rejected, bands not starting at 0 rejected, exactly one unbounded top band allowed) in `tests/test_match_modes.py`
- [X] T011 [P] [US1] Unit tests for `migrate_legacy_tenure_based_config()` confirming a legacy single-tier config (`min_years`, `max_years`, `match_rate`, `max_deferral_pct`) round-trips into the correct one-tier `TenureGradedMatchBand` per the contract mapping in `tests/test_match_modes.py`
- [X] T012 [P] [US1] Unit test for `_export_employer_match_vars()` emitting `tenure_graded_bands` as a dbt var in decimal form (0.50 not 50) for the spec's two-band example, in `tests/test_match_modes.py`

### Implementation for User Story 1

- [X] T013 [US1] Implement `get_tenure_graded_match_tiers()` macro body in `dbt/macros/get_tenure_graded_match_tiers.sql`: flatten the nested `tenure_graded_bands` var into a `SELECT ... UNION ALL` row set with columns `band_min_years, band_max_years, employee_min, employee_max, match_rate` (one row per tier across all bands), with `band_max_years` rendered as `NULL` when a band's `max_years` is `None` (depends on T006, T007)
- [X] T014 [US1] Add a `{% elif employer_match_status == 'tenure_graded' %}` branch in `dbt/models/intermediate/events/int_employee_match_calculations.sql` that: (a) cross-joins `employee_contributions` against `{{ get_tenure_graded_match_tiers(tenure_graded_bands) }} AS tier`, (b) filters `WHERE ec.years_of_service >= tier.band_min_years AND (tier.band_max_years IS NULL OR ec.years_of_service < tier.band_max_years)`, (c) computes `match_amount` via the cumulative `SUM(CASE WHEN ec.deferral_rate > tier.employee_min THEN LEAST(...) * tier.match_rate * LEAST(ec.eligible_compensation, lim.irs_401a17_limit) ELSE 0 END)` pattern (mirroring the existing `tiered_match` CTE), and (d) tags rows `'tenure_graded' AS formula_type`, feeding the shared `all_matches`/`final_match` CTEs (depends on T013)
- [X] T015 [US1] Update `_export_employer_match_vars()` in `planalign_orchestrator/config/export.py` to export `tenure_graded_bands` (decimal form, per `contracts/config-schema.md`) when `employer_match_status == 'tenure_graded'`, invoking `migrate_legacy_tenure_based_config()` when only a legacy `tenure_based`/`tenure_match_tiers` config is present so dbt always receives the new shape (depends on T008, T012)
- [X] T016 [US1] Add `dbt/tests/data_quality/test_tenure_graded_match_amount_nonnegative.sql` singular dbt test asserting `fct_employer_match_events` rows with `formula_type = 'tenure_graded'` have `match_amount >= 0` and `match_amount <= eligible_compensation * <max band rate>` as a sanity bound (depends on T014)
- [X] T017 [US1] Manually run the `quickstart.md` "Via config + dbt directly" scenario end-to-end and confirm the three spot-check match amounts (5%, 6%, capped-at-5%) match exactly

**Checkpoint**: User Story 1 is fully functional and independently testable — the core capability gap from the spec is closed.

---

## Phase 4: User Story 2 - Review and validate the configured match schedule before running a simulation (Priority: P2)

**Goal**: An analyst can see a clear summary of configured tenure bands/tiers (with computed max match % per band) and gets warned about gaps/overlaps before saving, with a hard block if an invalid config ever reaches a simulation run.

**Independent Test**: Configure a tenure-graded match design (valid and then deliberately gapped), confirm the Studio summary view displays bands/tiers/max-match-% correctly, confirm the save-time warning appears for the gapped config, and confirm `planalign simulate` fails fast with a clear validation error before any dbt run starts.

### Tests for User Story 2 ⚠️

- [X] T018 [P] [US2] Unit test confirming `EmployerMatchSettings` raises `ValueError` (not a silent pass-through) for a band-level gap and for a band-level overlap when `employer_match_status == 'tenure_graded'`, in `tests/test_match_modes.py` (exercises the run-time hard-block path of FR-008) — satisfied by `TestEmployerMatchSettingsTenureGraded.test_band_gap_rejected`/`test_band_overlap_rejected` already written in T010
- [X] T019 [P] [US2] dbt singular test `dbt/tests/data_quality/test_tenure_graded_tier_no_gaps_overlaps.sql` that reconstructs the band list and each band's tier list from the rendered `tenure_graded_bands` var and fails (returns >0 rows) if any band-level or tier-level gap/overlap is detected, mirroring `dbt/tests/data_quality/test_tenure_band_no_gaps.sql`'s `LEAD()`-window pattern — this is the last line of defense for configs that bypass the Pydantic loader (e.g., raw `dbt --vars`). Verified: PASS on valid 2-band config, FAILS correctly on a deliberately gapped config

### Implementation for User Story 2

- [X] T020 [US2] Implement the tier/band editor body of `planalign_studio/components/config/TenureGradedMatchEditor.tsx`: per-band add/remove tier rows, add/remove band rows, and a computed "max effective match %" readout per band (`SUM(tier.match_rate * (tier.employee_max - tier.employee_min))` per `data-model.md`'s Derived/Computed Values)
- [X] T021 [US2] Wire the existing `validateMatchTiers()` gap/overlap warning function (already used elsewhere in `planalign_studio/components/config/DCPlanSection.tsx`, exported for reuse) into `TenureGradedMatchEditor.tsx` for both the band-level list and each band's tier-level list, rendering a non-blocking inline warning (save-time half of FR-008)
- [X] T022 [US2] In `planalign_studio/components/config/DCPlanSection.tsx`, add `dcMatchMode === 'tenure_graded'` as a selectable match mode option and render `<TenureGradedMatchEditor />` when selected (depends on T020, T021) — verified via `npx tsc --noEmit` with zero errors
- [X] T023 [US2] In `planalign_api/routers/workspaces.py`, add `tenure_graded_bands: []` to the default employer_match config payload (parallels the existing `tenure_match_tiers: []` default), so new workspaces start with an empty, valid default
- [X] T024 [US2] Manually run the `quickstart.md` "Negative-path verification (gap/overlap)" scenario and confirm both the dbt-level warning (T019, save/raw-vars time) and the Pydantic hard failure (run-time, before any dbt subprocess starts) occur as specified — both verified directly

**Checkpoint**: User Stories 1 AND 2 both work independently — analysts can configure, review, and get protected against misconfiguration.

---

## Phase 5: User Story 3 - Model more than two tenure bands (Priority: P3)

**Goal**: An analyst can define three or more tenure bands, each with an independent multi-tier schedule, with no system-imposed cap.

**Independent Test**: Configure three tenure bands (e.g., 0-5, 5-10, 10+) with distinct multi-tier schedules, run a simulation, and confirm each band's employees are matched per their own schedule.

### Tests for User Story 3 ⚠️

- [X] T025 [P] [US3] Unit test in `tests/test_match_modes.py` configuring a 4-band `EmployerMatchSettings.tenure_graded_bands` list (varying tier counts per band, e.g., one band with 1 tier, another with 3 tiers) and confirming validation passes and `_export_employer_match_vars()` exports all bands correctly
- [X] T026 [P] [US3] dbt-level test: extend the fixture/seed data used by the `int_employee_match_calculations.sql` test setup (or add a small standalone DuckDB query in a test script) with three employees at 3, 7, and 15 years of tenure against a 3-band `tenure_graded_bands` config, asserting each is matched against its own band's schedule and not a neighboring band's — verified via synthetic SQL (3/7/15yr → 1.25%/3.5%/5% match as expected)

### Implementation for User Story 3

- [X] T027 [US3] Verify (and adjust if needed) that `get_tenure_graded_match_tiers()` (T013) and the `int_employee_match_calculations.sql` branch (T014) impose no hard-coded assumption of exactly 2 bands — confirm the Jinja `{% for band in tenure_graded_bands %}{% for tier in band['tiers'] %}` loop pattern scales to N bands with no code changes required — verified by running the actual dbt model with a real 3-band (1-tier/2-tier/1-tier) config end-to-end with zero code changes
- [X] T028 [US3] Extend `TenureGradedMatchEditor.tsx`'s "add band" control (built in T020) to have no UI-imposed maximum band count, confirming the existing add/remove pattern already generalizes (per clarification: no fixed limit) — confirmed by inspection: `addBand()` has no length check/cap

**Checkpoint**: All user stories independently functional — 2-band example (US1), reviewable/safe configuration (US2), and N-band generalization (US3) all work.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Clean up the superseded legacy mode now that migration (T008) makes it safe to retire, and finalize documentation.

- [X] T029 Remove the now-dead `{% elif employer_match_status == 'tenure_based' %}` branch from `dbt/models/intermediate/events/int_employee_match_calculations.sql` (safe because `_export_employer_match_vars()` (T015) now always emits `tenure_graded_bands`/`'tenure_graded'` via the migration helper, per FR-003a's supersession requirement). Also removed from the eligibility-mode list and the `formula_id` identifier block; verified all 4 remaining modes (`deferral_based`, `graded_by_service`, `tenure_graded`, `points_based`) still compile.
- [X] T030 Remove the legacy single-tier tenure-based editor block from `planalign_studio/components/config/DCPlanSection.tsx` (the one rendering `formData.dcTenureMatchTiers`), now superseded by `TenureGradedMatchEditor.tsx`. Also removed the `tenure_based` option from the mode `<select>`. Verified via `npx tsc --noEmit` with zero errors.
- [X] T031 [P] **Scope adjustment**: kept (rather than removed) the `TenureMatchTier` class and `tenure_match_tiers` field in `planalign_orchestrator/config/workforce.py` — `migrate_legacy_tenure_based_config()` (T008) actively depends on Pydantic parsing this field from old saved configs; removing it would silently break backward-compatible migration for any existing saved scenario. Both are now marked `DEPRECATED (Feature 099)` in their docstrings/field descriptions, with no remaining active (non-migration) code path reading them — the dbt branch (T029) and UI editor (T030) that used to read them are both gone.
- [X] T032 [P] Updated `CLAUDE.md`'s Project Status / Completed Epics section with a one-line entry for Feature 099. (No prior `tenure_based`-specific documentation existed in either CLAUDE.md to update — the legacy mode was never surfaced there.)
- [X] T033 Ran `pytest -m fast` (1371 passed, 3 pre-existing unrelated failures in `test_dbt_runner.py`/`test_excel_exporter.py` — confirmed via `git diff --name-only main` that neither those test files nor their source modules were touched by this feature) and `dbt build` for the match-calculation model chain; the 2 schema-test failures encountered there trace to stale dev-database state (`int_employer_eligibility` only populated for simulation_year 2027, not 2025, from a prior session) rather than this feature's code — confirmed by re-running our own `test_tenure_graded_match_amount_nonnegative` and `test_tenure_graded_tier_no_gaps_overlaps` tests directly, both PASS.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately, all tasks parallelizable
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion — delivers the MVP
- **User Story 2 (Phase 4)**: Depends on Foundational; depends on US1's T014/T015 existing (the UI summary and run-time hard block need a working calculation + export path to validate against) — but is independently testable once US1 is done
- **User Story 3 (Phase 5)**: Depends on Foundational; depends on US1's T013/T014 (verifies the N-band generalization of the same machinery) and US2's T020 (extends the same editor)
- **Polish (Phase 6)**: Depends on US1 + US2 (T008/T015 migration path) being complete; should follow US3 to avoid disrupting in-flight band-count testing

### Within Each User Story

- Tests (T009-T012, T018-T019, T025-T026) MUST be written and FAIL before their corresponding implementation tasks
- Foundational models (T005-T008) before any dbt or export work (T013-T015)
- Macro (T013) before SQL model branch (T014)
- Export (T015) before manual end-to-end validation (T017)

### Parallel Opportunities

- T001, T002, T003 (Setup) — all different files, fully parallel
- T009, T010, T011, T012 (US1 tests) — all in the same test file but independent test classes; can be authored in parallel by different people, though they'll merge into one file
- T018, T019 (US2 tests) — different files, parallel
- T025, T026 (US3 tests) — different files, parallel
- T031, T032 (Polish) — different files, parallel

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together (write first, confirm failing):
Task: "Unit tests for TenureBandMatchTier/TenureGradedMatchBand validation in tests/test_match_modes.py"
Task: "Unit tests for EmployerMatchSettings.tenure_graded_bands cross-band validation in tests/test_match_modes.py"
Task: "Unit tests for migrate_legacy_tenure_based_config() in tests/test_match_modes.py"
Task: "Unit test for _export_employer_match_vars() tenure_graded_bands export in tests/test_match_modes.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks everything)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run `quickstart.md`'s direct-config scenario; confirm match amounts are exactly correct
5. This alone closes the spec's core capability gap (SC-001, SC-002) and is demo-able via raw config + CLI even before any UI work

### Incremental Delivery

1. Setup + Foundational → config models exist and validate
2. Add User Story 1 → correct match calculation via config/dbt → **MVP**
3. Add User Story 2 → Studio UI + save/run-time validation safety net (SC-003)
4. Add User Story 3 → confirm/extend N-band generalization (already mostly free from the US1 design)
5. Polish → retire the superseded `tenure_based` mode cleanly

### Format Validation

All 33 tasks above follow `- [ ] T0XX [P?] [Story?] Description with file path`. Setup/Foundational/Polish tasks correctly omit the `[Story]` label; all Phase 3-5 tasks correctly carry `[US1]`, `[US2]`, or `[US3]`.
