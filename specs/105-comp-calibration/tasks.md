---
description: "Task list for Fast Compensation Calibration Mode"
---

# Tasks: Fast Compensation Calibration Mode

**Input**: Design documents from `/specs/105-comp-calibration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED — Constitution Principle III (Test-First) and plan.md mandate fast unit tests for the workflow variant + guard, and an integration test asserting comp-column exactness vs. a full sim.

**Organization**: Tasks grouped by user story. US1 (CLI calibrate) is the MVP; US2 (interactive) and US3 (Studio) build on the shared foundation.

## Path Conventions

Existing web/CLI/orchestrator layout (no new top-level projects): `planalign_orchestrator/`, `planalign_cli/`, `planalign_api/`, `planalign_studio/`, `tests/` at repo root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Branch + scaffolding for new modules

- [X] T001 Confirm working on branch `105-comp-calibration` and create empty module stubs: `planalign_orchestrator/calibration_runner.py`, `planalign_cli/commands/calibrate.py`, `planalign_api/routers/calibration.py`, `planalign_studio/components/CalibrationPanel.tsx`
- [X] T002 [P] Create empty test modules `tests/test_calibration_workflow.py`, `tests/test_calibration_runner.py`, `tests/test_calibration_exactness.py` with `pytest` markers (`fast` for first two, `integration` for the third)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The comp-only build engine that ALL user stories depend on — the workflow variant, the parameter/result models, the prerequisite guard, and the runner.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

> Test-first: write the `[TEST]` tasks (T004, T006) and confirm they FAIL before implementing the behavior they cover.

- [X] T003 Define `CalibrationParameterSet`, `CalibrationRun`, and `PerYearCompensationResult` Pydantic v2 models per data-model.md in `planalign_orchestrator/calibration_runner.py` (reuse `CompensationSettings` fields; `target_growth_pct` for delta only; first-year `yoy_growth_pct`/`growth_delta_pct` nullable)
- [X] T004 [P] [TEST] Fast unit test in `tests/test_calibration_workflow.py` (write first, must fail): assert `build_calibration_year_workflow` includes the comp models + the two marts + `fct_compensation_growth` and EXCLUDES every DC model listed in research.md; assert Year 1 vs Year 2+ foundation differences
- [X] T005 [P] Add `WorkflowBuilder.build_calibration_year_workflow(year, start_year)` in `planalign_orchestrator/pipeline/workflow.py` returning the comp-only stage list from research.md Decision 3 (explicit INCLUDE list: foundation + hazard + comp events + `fct_yearly_events` + `int_workforce_snapshot_optimized` + `fct_workforce_snapshot` + `fct_compensation_growth`; DC models dropped). Ensure `fct_compensation_growth` is explicitly built (it is absent from the standard STATE_ACCUMULATION list)
- [X] T006 [P] [TEST] Fast unit test in `tests/test_calibration_runner.py` (write first, must fail): year-range parsing/validation (end≥start), first-year nulls, isolated-DB default selection, and guard raises on a DB missing DC tables (mock/fixture DB)
- [X] T007 Implement prerequisite guard `verify_dc_prerequisites(database_path)` in `planalign_orchestrator/calibration_runner.py` that checks the DC tables `ref()`d by `fct_workforce_snapshot`/`fct_yearly_events` exist; raise a `ConfigurationError` (from `planalign_orchestrator/exceptions.py`) with an actionable message + correlation id when any are missing
- [X] T008 Implement isolated-DB resolution in `planalign_orchestrator/calibration_runner.py` mirroring `scenario_batch_runner._run_isolated_scenario` — when no `--database` given, target a timestamped `<calibration>.duckdb` and set `DATABASE_PATH`; never touch `dbt/simulation.duckdb`
- [X] T009 Implement `CalibrationRunner.run(calibration_run)` in `planalign_orchestrator/calibration_runner.py`: validate range → guard → per-year `DbtRunner.execute_command(["run","--select",<models>], dbt_vars=to_dbt_vars(...))` → assemble `PerYearCompensationResult[]` by reading `fct_compensation_growth` (methodology A) + `fct_workforce_snapshot` (headcount, new-hire/existing comp gap) (depends on T003, T007, T008)

**Checkpoint**: The comp-only engine builds and assembles results; foundation ready.

---

## Phase 3: User Story 1 - Tune comp policy from the CLI (Priority: P1) 🎯 MVP

**Goal**: `planalign calibrate <start>-<end>` returns a per-year table (avg comp, YoY growth vs target, headcount, new-hire gap), runs against an isolated DB by default, materially faster than the full sim, with exact comp metrics.

**Independent Test**: Run `planalign calibrate 2025-2029 --database /tmp/cal/iso.duckdb` against a fully-built DB; confirm the per-year table renders and comp columns match a full sim exactly (quickstart.md steps 2–3).

### Tests for User Story 1 ⚠️

- [X] T010 [P] [US1] [TEST] Integration test `test_calibration_comp_columns_exact` in `tests/test_calibration_exactness.py`: runs `CalibrationRunner` against a pre-built isolated baseline DB (`CALIBRATION_BASELINE_DB`), asserts **per-employee** prorated comp matches the full sim bit-for-bit (SC-002); `test_shared_dev_db_untouched` asserts the shared `dbt/simulation.duckdb` is untouched (SC-004). **PASSING** against a 2-year baseline (0 mismatches, avg diff ~1e-10).
- [X] T011 [P] [US1] [TEST] Integration test `test_calibration_tracks_non_default_config`: exactness under a non-default edge config (COLA 4.5% / merit 5.0%). **PASSING** — 6967/6967 active, 0 mismatches, avg $93,667.57 matches the full sim (≠ default $92,153.87, proving the config flows through).

> ✅ **EXACTNESS RESOLVED (SC-002/FR-003).** The earlier divergence was **not** incremental contamination — it was a parameter-mapping bug: `--target-growth` was overriding `simulation.target_growth_rate` (the *workforce* growth target that sizes E077 hiring), changing headcount. `target_growth_pct` is the *compensation*-growth target and is now used **only** for the per-year delta column. With that fixed, the per-year incremental rebuild is bit-for-bit exact vs. a full sim under both default and edge configs. No clean-slate/full-refresh needed.

### Implementation for User Story 1

- [X] T012 [US1] Implemented `run_calibration()` in `planalign_cli/commands/calibrate.py` (positional `<year-range>`, `--config`/`--database`/`--target-growth`/`--cola`/`--merit`/`--threads`, parse via `parse_years`/`validate_year_range`, builds `CalibrationRun`, invokes `CalibrationRunner`)
- [X] T013 [US1] Per-year Rich table (Year, Avg Comp, YoY Growth, Target, Δ vs Target, Headcount, NH Gap) with `—` for first-year growth/delta
- [X] T014 [US1] Exit codes mapped (0/2/3/1) and guard's actionable message surfaced
- [X] T015 [US1] Registered `calibrate` command in `planalign_cli/main.py`

**Checkpoint**: ✅ US1 fully functional — CLI calibrate **runs, is fast (~16s/yr vs. the full sim), isolated by default, fail-fast, and exact vs. a full simulation under both default and edge configs**. **MVP shippable.**

---

## Phase 4: User Story 2 - Iterate interactively without restarting (Priority: P2)

**Goal**: An `--interactive` loop lets the analyst change params between iterations and re-run with a minimal rebuild, without restarting the command.

**Independent Test**: Start `planalign calibrate 2025-2029 --interactive`, change COLA, confirm refreshed per-year results reflect only that change and remain exact (spec US2 scenarios).

### Tests for User Story 2 ⚠️

- [X] T016 [P] [US2] [TEST] Fast unit tests in `tests/test_calibration_runner.py`: a re-tune updating `cola_rate`/`merit_budget` overrides only those fields, leaves unset params at the config default, and (critically) does NOT touch `simulation.target_growth_rate`. **PASSING.**

### Implementation for User Story 2

- [X] T017 [US2] Added `--interactive` flag + cumulative re-tune loop in `planalign_cli/commands/calibrate.py` (`_interactive_loop`/`_prompt_params`): after each render, prompts for COLA/merit (blank keeps current, layered onto prior params, re-validated), re-runs the comp subgraph for the range, re-renders; exits on `q`. Implemented via `rerun_with_params` (rebuild) rather than `update_compensation_parameters`, which is cleaner and keeps the build exact. **Verified end-to-end**: COLA 2%→8% moved avg comp $92,154→$94,474 with headcount unchanged at 6,967.
- [X] T018 [US2] Added `CalibrationRunner.rerun_with_params(params)` fast-path in `planalign_orchestrator/calibration_runner.py` — applies new params and rebuilds the comp subgraph for the existing range/DB (no re-guard, no isolated-DB re-init).

**Checkpoint**: ✅ US1 + US2 work independently; interactive tuning delivers the fast tune-and-read loop.

---

## Phase 5: User Story 3 - Calibrate visually from Studio sliders (Priority: P3)

**Goal**: A Studio panel with target-growth/COLA/merit/new-hire-mix sliders triggers a calibration run and shows per-year avg-comp + growth-vs-target charts matching the CLI.

**Independent Test**: Open the Studio Calibration panel, move a slider, confirm a run triggers and charts update with values equal to the CLI for the same params (spec US3 scenarios, SC-006).

### Tests for User Story 3 ⚠️

- [X] T019 [P] [US3] [TEST] API tests in `tests/test_calibration_api.py` (4): valid request returns per-year results matching the runner; missing-DC guard → 409; bad year range → 422; negative COLA → 422 (per contracts/api-calibration.md). **PASSING.**

### Implementation for User Story 3

- [X] T020 [P] [US3] Implemented `POST /api/calibration/run` in `planalign_api/routers/calibration.py` with Pydantic request/response models, delegating to `CalibrationRunner` (sync `def` endpoint → offloaded to a worker thread); guard→409, validation→422, unexpected→500.
- [X] T021 [US3] Included the calibration router in `planalign_api/main.py` (`/api`, tag "Calibration"); verified `/api/calibration/run` is registered in the live app.
- [X] T022 [P] [US3] Built `CalibrationPanel.tsx` in `planalign_studio/components/`: four sliders (target growth, COLA, merit, new-hire senior mix), year range + optional DB inputs, `runCalibration` client (added to `services/api.ts`), per-year avg-comp line chart + YoY-growth bar chart with a target reference line, and a results table (Tailwind utilities, recharts; no CDN).
- [X] T023 [US3] Wired `CalibrationPanel` into Studio nav: route `/calibrate` in `App.tsx` + a "Calibration" `NavItem` in `Layout.tsx`. `tsc --noEmit` 0 errors; `vite build` succeeds.
- [X] T024 [US3] CLI↔Studio value parity (FR-013/SC-006): both surfaces delegate to the **same** `CalibrationRunner.run_calibration()` with identical params, and the API test asserts the endpoint returns the runner's results verbatim — so rendered values equal the CLI by construction. (Live slider-drive is quickstart.md step 6.)

**Checkpoint**: ✅ All three stories independently functional; CLI/Studio parity holds by construction (shared runner).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T025 [P] Documented `calibrate` in `CLAUDE.md` Quick Start + a dedicated "Fast Compensation Calibration (Feature 105)" section (invariants, the target-growth vs. workforce-growth distinction, isolated-DB verification flow).
- [X] T026 [P] `calibrate` appears in `planalign --help` (verified) with its own `--help`.
- [X] T027 Quickstart verified against isolated DBs: speedup (SC-001, ~2yr calibrate in ~22-32s vs. a multi-minute full build), exactness (SC-002, per-employee match), guard fail-fast exit code 3 (SC-005), shared dev DB unchanged (SC-004).
- [X] T028 [P] Full fast suite **1484 passed** (no regressions); all 3 integration exactness tests pass (default + edge config + shared-DB-untouched).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Stories (Phase 3–5)**: All depend on Foundational. US1 is MVP; US2 and US3 depend only on the foundation (US2 also uses the CLI from US1; US3 is independent of US1/US2).
- **Polish (Phase 6)**: After desired stories complete.

### User Story Dependencies

- **US1 (P1)**: After Phase 2. No dependency on other stories.
- **US2 (P2)**: After Phase 2 + US1 CLI command (extends `calibrate.py`).
- **US3 (P3)**: After Phase 2. Independent of US1/US2 (separate API/UI surface over the same runner).

### Within Each Story

- Tests written first and FAIL before implementation.
- Models → runner/services → CLI/endpoint → wiring.

### Parallel Opportunities

- T002 ∥ T001 scaffolding.
- Phase 2: T004 (workflow test) ∥ T006 (runner test) — distinct test files; T005 (workflow.py) is a separate file from the `calibration_runner.py` work (T007/T008/T009), which is sequential within that one file.
- US1: T010 ∥ T011 (tests).
- US3: T020 ∥ T022 (API vs frontend) once contracts fixed.
- Polish: T025 ∥ T026 ∥ T028.

---

## Parallel Example: User Story 1

```bash
# Tests first (both in the exactness module, distinct test functions):
Task: "Integration exactness test (default config) in tests/test_calibration_exactness.py"
Task: "Integration exactness test (edge config) in tests/test_calibration_exactness.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL) → 3. Phase 3 US1 → 4. **STOP & VALIDATE** exactness + speedup against an isolated DB → 5. Demo.

### Incremental Delivery

1. Setup + Foundational → engine ready.
2. US1 → CLI MVP (fast, exact, isolated, fail-fast).
3. US2 → interactive re-tune (the headline 15-min loop).
4. US3 → Studio sliders + charts.

---

## Notes

- [P] = different files / independent; [TEST] = test task (write first, must fail).
- Comp-column exactness (SC-002) is the make-or-break gate — keep T010/T011 green before merging.
- No new dbt models under Design 1; if a future snapshot change makes a DC column influence comp, escalate to Design 2 (lean snapshot) per research.md Decision 2.
- Keep `CalibrationRunner` within the ~600-line / 6–8 public-method constitution guidance; split a helper module if it grows.
