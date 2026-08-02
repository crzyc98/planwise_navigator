---
description: "Task list for 132-collapse-dbt-invocations"
---

# Tasks: Collapse Remaining Per-Year Transformation Invocations

**Input**: Design documents from `/specs/132-collapse-dbt-invocations/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Test tasks ARE included. The spec mandates a correctness gate (`FR-006`–`FR-013`) and Constitution III requires test-first. Testing is deliberately split: **schedule-shape tests run in CI** (fast, cheap), while the **60k parity gate runs locally** with committed evidence (clarification Q4).

**Organization**: Grouped by user story. US1 and US2 are sequenced, not parallel — the spec requires Story 2 to follow a *measured and merged* Story 1, because it is where Tier C's failure mode lives.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3

**Status legend**: `[X]` done · `[~]` not attempted — the sequence stopped after Step 1a on corrected economics; see [evidence/decision-log.md](evidence/decision-log.md)

## Path Conventions

Single project at repository root: `planalign_orchestrator/`, `scripts/`, `tests/`, `specs/132-collapse-dbt-invocations/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Produce the fixed measurement subject and the baseline every step is compared against.

- [X] T001 Create the evidence and working directories: `specs/132-collapse-dbt-invocations/evidence/` (committed) and `var/perf_profile/` (git-ignored)
- [X] T002 Generate the 60,040-row reference census once via `python -m scripts.perf_profile.make_large_census --factor 8 --out var/perf_profile/census_60k.parquet`; verify it reports 60,040 rows with unique ids
- [X] T003 [P] Write the Studio-shaped reference configuration to `var/perf_profile/studio_shape.yaml`, pointing at the generated census, with `threads: 1` and years 2025-2029
- [X] T004 Record the census file digest in `specs/132-collapse-dbt-invocations/evidence/reference-workload.md` so every later gate can prove it used the same file (invariant RW-1, research Finding 6)

**Checkpoint**: The reference workload exists and is pinned.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The measurement and correctness machinery every story depends on. Note that although the *recorded step records* are User Story 3 (P3), the **harness that produces them is foundational** — Steps 1a/1b cannot make a keep/revert decision without it.

**⚠️ CRITICAL**: No story work begins until this phase is complete.

- [X] T005 Implement `scripts/parity_gate.py`: enumerate marts via `cd dbt && dbt ls --select marts --resource-type model --output name` (never a hardcoded list), run bidirectional `EXCEPT ALL` per mart between two databases, and emit a Markdown report — per `contracts/parity-gate.md`
- [X] T006 In `scripts/parity_gate.py`, apply the exclusion list — `created_at`, `snapshot_created_at`, `cache_built_at`, and the `run_metadata` / `run_execution_metadata` tables — and **report the exclusions applied** rather than silently dropping columns (invariant PR-4)
- [X] T007 In `scripts/parity_gate.py`, add the coverage assertion: the compared mart set must equal the enumerated mart set, so a silently skipped mart fails rather than passes (invariant PR-2)
- [X] T008 In `scripts/parity_gate.py`, add the `--determinism` third-database comparison so a candidate is also checked against a same-seed re-run (`FR-011`, invariant PR-3)
- [X] T009 [P] Add a schedule reader helper in `tests/fixtures/schedule.py` that reads the finalized command schedule from `run_execution_metadata` and returns per-year, per-stage command records matching the Command Schedule entity in `data-model.md`
- [X] T010 Capture the pre-change baseline: run the five-year 60k simulation into `var/perf_profile/baseline.duckdb`, three times, and record median wall time plus the startup/execution/orchestration split in `specs/132-collapse-dbt-invocations/evidence/step-00-baseline.md`
- [X] T011 Reconcile the captured 103.576s baseline with the 102.720s median across 18 prior 20-command runs; reject the unreproducible 91.5s issue headline and derive 3s/6s bars from observed command-removal cohorts

**Checkpoint**: Gate driver works, baseline is recorded and sanity-checked.

---

## Phase 3: User Story 1 - Analyst waits less for the first simulation year (Priority: P1) 🎯 MVP

**Goal**: Cut the year-1 setup block from 8 commands to 6, recovering ≥3s.

**Independent Test**: Run the five-year 60k simulation before and after; confirm year-1 command count drops, median wall time drops ≥3s, and every mart is row-for-row identical in both directions.

### Tests (write first — these must fail before implementation)

- [X] T012 [P] [US1] Write `tests/test_workflow_schedule.py::test_start_year_command_count` asserting the start year issues fewer than eight commands (`FR-001`, invariant CS-4)
- [X] T013 [P] [US1] Write `tests/test_workflow_schedule.py::test_no_model_built_twice_per_year` asserting no model name appears in more than one command's resolved selection within a year (`FR-002`, invariant CS-1) — this fails today because of the redundant `int_baseline_workforce` build
- [X] T014 [P] [US1] Write `tests/test_workflow_schedule.py::test_full_refresh_set_unchanged` pinning the exact set of models built with a rebuild flag, so any step that changes it fails loudly (`FR-005`, invariant CS-2)
- [X] T015 [P] [US1] Write `tests/test_workflow_schedule.py::test_hazard_cache_vars_preserved` asserting `hazard_params_hash` is present on whichever command builds the hazard caches (invariant CS-5, research Finding 4 risk 1)

### Step 1a — remove the redundant year-1 build

- [X] T016 [US1] In `planalign_orchestrator/pipeline/workflow.py:120-123`, empty the start-year INITIALIZATION model list so `int_baseline_workforce` is built only by FOUNDATION, which already `--full-refresh`es it — a deletion, not a regrouping
- [X] T017 [US1] Add a comment at that site recording *why* this is safe: FOUNDATION full-refreshes the same model moments later (`year_executor.py:407-433`), and `StageValidator.validate_stage` dispatches nothing for INITIALIZATION (`stage_validator.py:57-83`), mirroring how Tier B documented its own merge
- [X] T018 [US1] Run `pytest -m fast tests/test_workflow_schedule.py -v` and confirm T012/T013 now pass
- [X] T019 [US1] Run the parity gate for step 1a into `specs/132-collapse-dbt-invocations/evidence/step-1a-parity.md` (baseline vs candidate vs determinism re-run, 60k, five years)
- [X] T020 [US1] Measure step 1a (median of three) and write `specs/132-collapse-dbt-invocations/evidence/step-1a-record.md` with command count, wall time, three-way split, delta, and the keep/revert decision
- [X] T021 [US1] Apply the decision rule: keep only if parity is clean; revert if parity is dirty. Record either outcome (invariants SR-1, SR-3)

### Step 1b — merge the hazard-cache pair

- [X] T022 [US1] In `planalign_orchestrator/hazard_cache_manager.py:395-432`, replace the `run --select int_effective_parameters --full-refresh` plus `build --select dim_*_hazards hazard_cache_metadata --full-refresh` pair with a single `build --select int_effective_parameters dim_*_hazards hazard_cache_metadata --full-refresh`
- [X] T023 [US1] Ensure the merged command still passes `extra_vars={"hazard_params_hash": current_hash}` — dropping it rebuilds caches against a wrong hash, a silent failure the gate would catch only after a full 60k run (research Finding 4)
- [X] T024 [US1] Confirm `int_effective_parameters`' schema tests pass at 60k, since moving from `run` to `build` newly executes them — the existing comment at `hazard_cache_manager.py:399-400` shows `run` was chosen deliberately to skip them. If they are flaky, revert step 1b
- [X] T025 [US1] Run `pytest -m fast tests/test_workflow_schedule.py -v` and confirm T014/T015 still pass
- [~] T026 [US1] Run the parity gate for step 1b into `specs/132-collapse-dbt-invocations/evidence/step-1b-parity.md`
- [X] T027 [US1] Measure step 1b and write `specs/132-collapse-dbt-invocations/evidence/step-1b-record.md`, with delta measured against the post-1a state
- [X] T028 [US1] Evaluate `SC-001`: if 1a + 1b together deliver ≥3s against the freshly captured baseline, US1 is complete. If short, evaluate optional step 1c below; otherwise retain the provably redundant Step 1a and record the decision on Step 1b

### Optional Step 1c — only if T028 shows a shortfall

- [~] T029 [US1] Union the seed load into a single `build` with `staging.*` (20 → 13 total), accepting that `build` newly runs seed and staging tests; gate and measure exactly as above, writing `specs/132-collapse-dbt-invocations/evidence/step-1c-*.md`

**Checkpoint**: US1 is independently shippable. If US2 is never attempted, the gain here is retained.

---

## Phase 4: User Story 2 - Analyst waits less for every subsequent year (Priority: P2)

**Goal**: Fold the later-year setup command into event generation, 3 commands/year → 2, recovering a further ≥6s if its value justifies the known Tier C correctness risk.

**Independent Test**: If attempted, confirm exactly two commands per year after the start year, ≥6s further reduction against the post-US1 state, and clean all-marts parity at 60k.

**⚠️ Do not begin until US1 is measured, gated, and merged.** This phase touches per-year simulation semantics — the exact place Feature 121's Tier C broke.

### Tests (write first)

- [~] T030 [P] [US2] Write `tests/test_workflow_schedule.py::test_later_year_command_count` asserting exactly two commands per year after the start year (`FR-003`, invariant CS-3)
- [~] T031 [P] [US2] Write `tests/integration/test_stage_attribution.py` asserting that an induced failure inside the merged command still reports a simulation year and a recognizable stage (`FR-015`, `SC-009`)
- [~] T032 [P] [US2] Extend `tests/test_workflow_schedule.py::test_full_refresh_set_unchanged` to cover later years, confirming neither merged side carries a rebuild flag (`_should_full_refresh_foundation` is start-year-only, `year_executor.py:424`)

### Implementation

- [~] T033 [US2] In `planalign_orchestrator/pipeline/workflow.py`, fold the merged later-year INITIALIZATION+FOUNDATION models into the event-generation selection, producing `run --select tag:EVENT_GENERATION <foundation models>` — a tag/model union, since event generation selects by tag (`stage_execution_strategies.py:26-43`) while state accumulation selects by model list (`year_executor.py:308-331`)
- [~] T034 [US2] Retain the FOUNDATION stage with an empty model list so its validation rules and telemetry still run against the built tables (`FR-013`, `FR-014`) — the same pattern Tier B established at `workflow.py:171-173`
- [~] T035 [US2] Confirm the `"Match working runner ordering exactly for determinism"` comment at `workflow.py:191` does not encode a real constraint: the listed models already go into one dbt selection where order comes from the `ref()` DAG, not the list. If any model turns out to depend on orchestrator ordering rather than a declared dependency, abandon this step
- [~] T036 [US2] Run `pytest -m fast tests/test_workflow_schedule.py -v` and `pytest tests/integration/test_stage_attribution.py -v`
- [~] T037 [US2] Run the parity gate for step 2 into `specs/132-collapse-dbt-invocations/evidence/step-2-parity.md`
- [~] T038 [US2] Measure step 2 and write `specs/132-collapse-dbt-invocations/evidence/step-2-record.md`, delta measured against the post-US1 state (invariant SR-2)
- [~] T039 [US2] Apply the decision rule. **A dirty gate means revert, full stop** — do not narrow the mart set or retry at 7.5k to obtain a pass (`FR-012`); 7.5k parity is explicitly not evidence

**Checkpoint**: Both stories complete, or US2 reverted with its record intact — both are successful outcomes under `SC-004`.

---

## Phase 5: User Story 3 - Engineer can tell whether each step was worth it (Priority: P3)

**Goal**: A consolidated, comparable record of every step and its decision.

**Independent Test**: Every step has a record with command count, wall time, three-way split, and an explicit keep/revert/stop decision; a reader can tell why the sequence stopped where it did.

- [X] T040 [P] [US3] Define the step-record format in `specs/132-collapse-dbt-invocations/evidence/README.md`, matching the Step Record entity in `data-model.md`, so the per-step files written during US1/US2 are consistent
- [X] T041 [US3] Write the consolidated decision log at `specs/132-collapse-dbt-invocations/evidence/decision-log.md`: one row per step with delta, bar, parity result, and decision — including reverted and unattempted steps and why
- [X] T042 [US3] Verify `SC-004`: every kept step cleared its bar, and every reverted or abandoned step has a recorded measurement and explicit decision

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T043 [P] Confirm `SC-006` and `SC-007` against the final recorded schedule: 14 or fewer commands and startup under 26s if both steps kept; 18 or fewer and under 35s if US1 only
- [X] T044 [P] Update `docs/perf/` with the new production schedule, superseding the 20-invocation baseline, and state the empirically observed per-command value and honest remaining ceiling
- [X] T045 [P] Update `CLAUDE.md`'s dbt-invocation guidance so the recorded production schedule reflects the new command count rather than the pre-132 figure
- [X] T046 Open a follow-up issue for the dead `data_freshness_check` validation rule (declared at `workflow.py:180` and `:308`, never dispatched by `StageValidator`) — deliberately out of scope here to keep this diff purely about invocation count (research Finding 2)
- [X] T047 Run the full fast suite plus integration tests to confirm no collateral regression: `pytest -m fast` then `pytest -m integration`

---

## Dependencies

```text
Phase 1 (Setup: census, config, baseline pinning)
  └─> Phase 2 (Foundational: parity driver, schedule reader, baseline capture)
        └─> Phase 3 US1 (P1) ── 1a ──> 1b ──> [optional 1c]
              └─> Phase 4 US2 (P2)   [BLOCKED until US1 measured + merged]
                    └─> Phase 5 US3 (P3)
                          └─> Phase 6 Polish
```

**Story independence**: US1 ships without US2. US2 is *sequenced* after US1 rather than merely prioritized — the spec requires a proven, measured Story 1 first. US3 documents whatever US1 and US2 produced.

**Within US1**: step 1a and step 1b touch different files (`workflow.py` vs `hazard_cache_manager.py`) and could in principle be implemented in parallel, but they are deliberately gated and measured **separately** so a dirty parity result attributes to one change. Do not batch them.

## Parallel Execution Opportunities

- **Phase 1**: T003 alongside T002.
- **Phase 2**: T009 alongside T005–T008 (different files).
- **US1 tests**: T012–T015 are all new test functions and can be written together.
- **US2 tests**: T030–T032 together.
- **Phase 6**: T043, T044, T045 together.

**Never parallel**: the parity gate and measurement runs. Each is a multi-minute, memory-heavy simulation; running two concurrently corrupts the timing numbers that every keep/revert decision depends on.

## Implementation Strategy

**MVP = User Story 1** (T001–T028). Targets ≥3s on the lowest-risk changes available — step 1a is a deletion of provably discarded work, not a regrouping, so it cannot trip the reordering failure mode that broke Tier C.

**Incremental delivery**:
1. Phases 1–2 → baseline pinned, gate driver working.
2. Phase 3 → **ship US1**. Independently valuable; retained regardless of what follows.
3. Phase 4 → attempt US2. Expected to be the risky one; reverting it is a documented success, not a failure.
4. Phases 5–6 → record and clean up.

**Stop conditions**: revert on a dirty gate, revert on a delta below the step's bar, and stop the sequence entirely once the remaining ceiling no longer justifies the correctness risk. Historical command-count cohorts put the honest total prize near 10s; SQL and orchestration work are out of scope and unaffected.
