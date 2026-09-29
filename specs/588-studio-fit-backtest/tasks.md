---
description: "Task list for #588 — Studio workflows for parameter fit and backtest"
---

# Tasks: Studio Workflows for Parameter Fit and Backtest

**Input**: Design documents from `/specs/588-studio-fit-backtest/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, contracts/progress-protocol.md

**Tests**: Required. Issue #588 lists test coverage as acceptance criteria, and Constitution III mandates test-first. Test tasks precede implementation in each phase.

**Organization**: Tasks are grouped by user story (spec.md: US1 P1 fit, US2 P2 backtest, US3 P2 apply, US4 P3 persistence/retention).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1–US4

---

## Phase 1: Setup

- [x] T001 Create package skeleton `planalign_api/services/param_fit/__init__.py` and an empty `planalign_studio/components/paramFit/` folder
- [x] T002 [P] Add `param_fit_max_jobs_per_workspace: int = Field(default=20, gt=0)` to `planalign_api/config.py`

---

## Phase 2: Foundational (engine additions + job plumbing; blocks all stories)

### Tests first

- [x] T003 [P] Add tests to `tests/test_parameter_fitting.py`:
  - `build_diagnostics` groups every fitted value and flags thin cells
  - `write_pack(..., diagnostics=...)` writes `diagnostics.json`
  - the pack fingerprint and `load_pack` round-trip are identical with and without it
- [x] T004 [P] Create `tests/test_fit_progress.py`:
  - `emit` is silent unless `PLANALIGN_FIT_PROGRESS=1`
  - it emits `PLANALIGN_FIT_PROGRESS|{"v":1,...}` lines
  - `parse_progress_line` round-trips and ignores non-sentinel lines
- [x] T005 [P] Add a test to `tests/test_parameter_fitting.py` (apply section) that `apply_pack(..., seeds_root=custom)` copies seeds from `custom`, not `dbt_root/seeds`
- [x] T006 [P] Create `tests/api/test_param_fit_jobs.py` with fast JobStore unit tests:
  - atomic create, read and update of `job.json`
  - list newest-first
  - a non-terminal job not owned by the current process reads back as failed/`interrupted`

### Implementation

- [x] T007 [P] Implement `planalign_fit/diagnostics.py::build_diagnostics(run: FitRun) -> dict`, per research R6: groups, thin flag, unfittable, warnings, promotion classification, counts
- [x] T008 [P] Implement `planalign_fit/progress.py`: `SENTINEL`, `ENV_FLAG`, `emit(event, **fields)`, `parse_progress_line(line)`
- [x] T009 Extend `write_pack` in `planalign_fit/pack.py` with an optional `diagnostics` argument that writes `diagnostics.json` (not part of the fingerprint); export `build_diagnostics` from `planalign_fit/__init__.py`
- [x] T010 Add `seeds_root: Optional[Path] = None` to `apply_pack`/`_build_overlay_project` in `planalign_fit/apply.py`. Default: `dbt_root/seeds`.
- [x] T011 Emit progress stages (`loading_history`, `fitting`) in `planalign_fit/runner.py::fit_parameter_pack`
- [x] T012 Update `planalign_backtest/runner.py`:
  - expose the fit run on `BacktestRun` (`fit_run` field)
  - pass `seeds_root=options.fit_options.seeds_dir` to `apply_pack`
  - emit the `stage`, `seed_started` and `seed_completed` events
- [x] T013 Update `planalign_cli/commands/fit.py`: pass `diagnostics=build_diagnostics(run)` to `write_pack`; emit `writing_pack` and `completed`
- [x] T014 Update `planalign_cli/commands/backtest.py`:
  - write `fit_report.md` and `diagnostics.json` via `write_pack(run.pack, …, report=render_fit_report(run.fit_run), diagnostics=build_diagnostics(run.fit_run))`
  - emit `simulation_failed` (seed, year, message) before exit 4
  - emit `scoring`, `writing_pack` and `completed` (with verdict)
- [x] T015 [P] Create the API models in `planalign_api/models/param_fit.py`: SnapshotInfo, SplitPreview, SplitError, HistorySet, FitOptionsModel, ThresholdPair, ThresholdsModel, ParamFitRequest, JobInputs, JobProgress, JobError, ParamFitJob, ParamFitJobSummary, ParamFitResult, StaleReason, ApplyPreview, ApplyRequest (bounds per data-model.md)
- [x] T016 Implement `planalign_api/services/param_fit/jobs.py` `JobStore`:
  - paths
  - atomic write
  - get/list
  - `claim` (register as owned by this process)
  - interrupted reconciliation
  - `prune_finished(max_jobs)`
  - `has_active_backtest(ws)`
- [x] T017 Create `planalign_api/routers/param_fits.py` with dependencies (`get_storage`, `get_param_fit_service`) and register it in `planalign_api/main.py` under `/api/workspaces` with `protected_dependencies`

**Checkpoint**: The engine emits diagnostics and progress, and job records persist.

---

## Phase 3: User Story 1 — Fit parameters from census history (P1) 🎯 MVP

**Goal**: Upload history, preview it, launch a fit, and view the results.
**Independent test**: Upload 3 synthetic snapshots, run a fit against a scenario, and check the result summary, diagnostics, provenance and report.

### Tests first

- [x] T018 [P] [US1] Create `tests/api/test_param_fit_history.py`:
  - uploading 3 synthetic CSVs returns 201, with years, rows, sha256, digest, as-of dates, and splits (holdout 1 ok, holdout 2 → error)
  - a gap, a duplicate year, or 1 file returns 422 with the fitter's message and nothing is persisted
  - a bad extension returns 400
  - list and get work; get re-hashes
  - delete returns 204, and 409 while a job uses the set
  - an unknown workspace returns 404
- [x] T019 [P] [US1] Add fit-job tests to `tests/api/test_param_fit_jobs.py`, using an injectable command factory that runs a stub Python script emitting progress lines and writing a fixture pack:
  - POST returns 202 quickly with status queued
  - polling reaches completed; the result has the summary, diagnostics (with thin flags), provenance and `stale == []`
  - GET `reports/fit` returns markdown
  - exit codes 2, 3 and 4 map to `invalid_input`/422, `invalid_history`/422 and `output_conflict`/409
  - any other exit code maps to `unexpected`/500 with a sanitized message
  - 422 for an unknown scenario, an invalid split, or invalid options
- [x] T020 [P] [US1] Add a real-CLI fit test (fast; the synthetic fit takes seconds) in `tests/api/test_param_fit_jobs.py` that runs the actual `planalign_cli.main fit` subprocess against a workspace scenario and asserts `diagnostics.json` and the manifest are present and the fingerprint is verified

### Implementation

- [x] T021 [US1] Implement `planalign_api/services/param_fit/history.py`:
  - `save_upload(ws, files)`: sanitized names, a temp directory, `load_snapshots` validation, then an atomic rename
  - `list`, `get` (re-hash plus split previews via `plan_split` for holdout 1 and 2), `delete`
- [x] T022 [US1] Implement `planalign_api/services/param_fit/runner.py`:
  - `build_fit_command` and `build_backtest_command`
  - `prepare_inputs`: the merged base config and seeds via `write_seeds`, into `inputs/`
  - `launch(job, command)`: a thread plus `Popen` in a new session, streaming stdout, applying progress, keeping a `job.log` tail
  - exit-code mapping per research R9
  - a process registry for cancellation
- [x] T023 [US1] Implement `planalign_api/services/param_fit/results.py`:
  - `load_result(job_dir, job, storage)` reads `pack/manifest.json`, `diagnostics.json` and `backtest/scorecard.json`
  - computes stale reasons (`history_changed`, `pack_modified`, `base_scenario_changed`)
  - builds the summary label for the promotion basis
- [x] T024 [US1] Implement `ParamFitService` in `planalign_api/services/param_fit/__init__.py`, tying history, jobs, runner and results together (start, get, list, report)
- [x] T025 [US1] Add the history and job routes to `planalign_api/routers/param_fits.py`:
  - POST/GET/GET/DELETE `fit-history`
  - POST/GET/GET `param-fits`
  - GET `reports/{kind}`

**Checkpoint**: A fit is launchable and inspectable over the API.

---

## Phase 4: User Story 2 — Backtest against held-out years (P2)

**Goal**: Fit and backtest with progress, cancel, and a scorecard.
**Independent test**: 4 snapshots, holdout 1, 2 seeds; check the scorecard. Separately, cancel a running job.

### Tests first

- [x] T026 [P] [US2] Add to `tests/api/test_param_fit_jobs.py`:
  - backtest progress (`seed_started` → stage simulating, index/total)
  - a `simulation_failed` event maps to `simulation_failure`/500 with `failed_seed` and `failed_year`
  - the scorecard is parsed into the result with `current == True`
  - a second concurrent backtest in the same workspace returns 409 (a fit is still allowed)
  - cancelling a running stub (sleeping) process ends as cancelled within 10 s, with the `pack/` and `work/` directories removed
  - cancelling a terminal job returns 409
- [x] T027 [P] [US2] Create `tests/api/test_param_fit_backtest_e2e.py` (marked `integration`, not fast): a real fit and backtest through the service on a small synthetic 4-year history (1 seed); it must leave `dbt/simulation.duckdb` untouched

### Implementation

- [x] T028 [US2] Extend the runner and service for backtest mode:
  - the command builder passes holdout, seed list, thresholds and `--workdir <job>/work`
  - the one-backtest-per-workspace guard (409)
  - `work/` is removed after completion (seed DBs are already deleted by the CLI)
- [x] T029 [US2] Implement cancel in `planalign_api/services/param_fit/runner.py`:
  - terminate the process group, then kill after a 5 s grace period
  - mark the job cancelled
  - remove `pack/` and `work/`
- [x] T030 [US2] Add the POST `param-fits/{job_id}/cancel` route and the `scorecard` report kind in `planalign_api/routers/param_fits.py`

**Checkpoint**: Backtests run, report progress, cancel cleanly, and score.

---

## Phase 5: User Story 3 — Apply a pack to a new scenario (P2)

**Goal**: A reviewed and acknowledged apply creates a new scenario whose runs use the pack.
**Independent test**: Apply, then confirm the new scenario exists with provenance and the source is byte-identical. A Studio run of the new scenario gets the pack seeds and the `param_pack` block.

### Tests first

- [x] T031 [P] [US3] Add to `tests/unit/simulation/test_simulation_service.py`: `write_seeds(config, run_dir, pack_seeds_dir)` layers seeds as defaults, then pack, then config-generated (a pack termination seed survives; `promotion_hazard` config wins over pack promotion seeds); `_prepare_simulation` passes the scenario's `param_pack/seeds` when present
- [x] T032 [P] [US3] Create `tests/api/test_param_fit_apply.py` (stub-produced completed job with a real `write_pack` fixture pack):
  - the apply preview returns fingerprints, required acknowledgements (thin_cells, unfittable, no_backtest), a diff and a suggested name
  - apply creates a new scenario:
    - overrides = source overrides ⊕ fragment ⊕ `promotion_hazard` ⊕ `param_pack`
    - the pack is copied
    - provenance is recorded
  - the source `scenario.json`/`overrides.yaml` bytes are unchanged
  - missing acknowledgements → 422 with `missing_acknowledgements`
  - stale cases → 409 naming the stale item:
    - history file edited
    - pack seed edited (`pack_modified`)
    - source config changed (fingerprint mismatch)
  - a name collision → 409 with `suggested_name`
  - apply on a non-completed job → 409
  - a backtest warn/fail verdict requires `backtest_warn`/`backtest_fail`; a scorecard that is not current counts as `no_backtest`

### Implementation

- [x] T033 [US3] Add `pack_seeds_dir` to `write_seeds` in `planalign_api/services/simulation/run_execution.py`, and pass `scenario_path/"param_pack"/"seeds"` from `_prepare_simulation` in `planalign_api/services/simulation/service.py`
- [x] T034 [US3] Implement `planalign_api/services/param_fit/apply.py`:
  - `promotion_hazard_from_pack(seed_files)`
  - `build_overrides(source_overrides, pack)`
  - `required_acknowledgements(result)`
  - `preview(...)` with the diff via `config_diff_service`
  - `apply(...)`: re-verify, check acknowledgements and name, create the scenario, copy the pack into `param_pack/`, roll back on failure
- [x] T035 [US3] Add the GET `apply-preview` and POST `apply` routes in `planalign_api/routers/param_fits.py` (409/422 bodies per contracts/api.md)

**Checkpoint**: A reviewed pack becomes a runnable new scenario.

---

## Phase 6: User Story 4 — Revisit jobs; retention (P3)

**Goal**: Jobs survive restart; old jobs are pruned; leftover scratch is reclaimed.
**Independent test**: Recreate the service (simulated restart); jobs are still listed and applicable; exceeding the cap prunes the oldest finished jobs.

### Tests first

- [x] T036 [P] [US4] Add to `tests/api/test_param_fit_jobs.py`:
  - after constructing a fresh service (new process registry), completed jobs are listed and their results load, and a leftover `running` record reads as failed/`interrupted`
  - with the cap set to 2, finishing a 3rd job prunes the oldest finished job and its directory, and never prunes running jobs
- [x] T037 [P] [US4] Add a test to `tests/cli/` (or wherever the gc tests live) that `planalign gc` reports and deletes `workspaces/*/param_fits/*/work` trees older than the cutoff and leaves `pack/` untouched

### Implementation

- [x] T038 [US4] Call `JobStore.prune_finished(settings.param_fit_max_jobs_per_workspace)` after each job reaches a terminal state, in `planalign_api/services/param_fit/runner.py`
- [x] T039 [US4] Add `find_stale_param_fit_scratch(workspaces_root, max_age)` and wire it into `run_gc` in `planalign_cli/commands/gc.py`

**Checkpoint**: Backend complete. Regenerate the OpenAPI snapshot.

- [x] T040 Regenerate `tests/api/snapshots/openapi_schema.json` per specs/115 quickstart and review the diff; run `tests/api/test_openapi_contract.py` and `tests/api/test_route_auth_coverage.py`

---

## Phase 7: Studio UI (US1–US4 surfaces)

- [x] T041 Regenerate `planalign_studio/services/api.generated.ts` (openapi-typescript from `node_modules/.bin`)
- [x] T042 Add the API client functions and `Schemas[...]` aliases to `planalign_studio/services/api.ts`:
  - uploadFitHistory, listFitHistory, getFitHistory, deleteFitHistory
  - startParamFit, listParamFits, getParamFit, cancelParamFit, getParamFitReport
  - getApplyPreview, applyParamPack
- [x] T043 [P] Write `planalign_studio/components/paramFit/paramFitHelpers.test.ts` first, covering:
  - moved-settings detection
  - thin-cell flagging and diagnostics grouping
  - progress label ("Simulating seed 2 of 3")
  - terminal-state detection
  - the required-acknowledgement labels
  - the pre-run summary rows
  - verdict styling
- [x] T044 [P] Implement `planalign_studio/components/paramFit/paramFitHelpers.ts`
- [x] T045 [P] [US1] Implement `planalign_studio/components/paramFit/HistoryStep.tsx`: multi-file upload, history-set picker, preview table (year, file, rows, sha256 short with full value in a title, as-of), source digest, errors
- [x] T046 [P] [US1] Implement `planalign_studio/components/paramFit/ConfigureStep.tsx`:
  - base scenario, mode, holdout with split preview, seeds
  - Advanced (fit options and thresholds, with moved values highlighted)
  - the pre-run summary and Run button
- [x] T047 [P] [US2] Implement `planalign_studio/components/paramFit/JobProgress.tsx`: stage and seed progress, Cancel with confirmation, and the error display (including failed seed and year)
- [x] T048 [P] [US1] Implement `planalign_studio/components/paramFit/FitResults.tsx`: summary cards, warnings, unfittable list, filterable diagnostics table with thin highlighting, provenance, stale banner, report viewer
- [x] T049 [P] [US2] Implement `planalign_studio/components/paramFit/BacktestScorecard.tsx`: verdict banner, split, and a comparisons table with status colors and moved-threshold markers
- [x] T050 [P] [US3] Implement `planalign_studio/components/paramFit/ApplyPackModal.tsx`: source scenario picker, diff list, acknowledgement checkboxes, name field with the suggested name on 409, stale errors, and a success link to the new scenario's config
- [x] T051 [P] [US4] Implement `planalign_studio/components/paramFit/JobList.tsx`: the workspace's jobs with status, mode, verdict, created time and a select action
- [x] T052 Implement the `planalign_studio/components/paramFit/ParamFitPage.tsx` shell: history, configure, active job progress, results, job list; polls every 1.5 s while any job is non-terminal
- [x] T053 Add the route `fit` in `planalign_studio/App.tsx` and a "Fit & Backtest" nav item in `planalign_studio/components/Layout.tsx`

---

## Phase 8: Polish & Cross-Cutting

- [x] T054 Run the Python checks:
  - `pytest -m fast tests/test_parameter_fitting.py tests/test_fit_progress.py tests/api/ tests/unit/simulation -q`
  - the existing backtest/fit CLI tests (`tests/test_backtest_*.py`)
- [x] T055 Run the Studio checks: typecheck, lint (`--max-warnings 0`), vitest
- [x] T056 Run the slow end-to-end test `tests/api/test_param_fit_backtest_e2e.py` in an isolated temp workspace root
- [x] T057 [P] Update `docs/guides/parameter_fitting.md` and `docs/guides/backtesting.md` with a "From Studio" section; add a CHANGELOG entry
- [ ] T058 Independent review (Codex/Opus) of the full diff; address findings

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → US1 (Phase 3) → US2 (Phase 4) and US3 (Phase 5), in either order → US4 (Phase 6) → OpenAPI (T040) → UI (Phase 7) → Polish.
- US3 needs a completed job, which it gets from US1's store and results. It does not need US2, but it reads the scorecard when one is present.
- The UI depends on the backend contract (T040/T041).

## Parallel Opportunities

- Phase 2 tests T003–T006 are parallel; implementations T007, T008 and T015 are parallel.
- Within US1, tests T018–T020 are parallel.
- UI components T045–T051 are parallel once the helpers (T044) and client (T042) exist.

## Implementation Strategy

- **MVP**: Phases 1–3 (fit only, over the API).
- **Delivery**: three commits on `588-studio-fit-backtest`:
  - (1) backend jobs: Phases 1–4, 6 and T040
  - (2) apply: Phase 5
  - (3) Studio UI: Phase 7, plus polish
