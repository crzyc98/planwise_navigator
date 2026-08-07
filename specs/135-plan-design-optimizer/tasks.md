---

description: "Task list for Plan-Design Optimizer (135-plan-design-optimizer)"
---

# Tasks: Plan-Design Optimizer

**Input**: Design documents from `/specs/135-plan-design-optimizer/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/spec-schema.md, contracts/cli-contract.md, quickstart.md

**Tests**: Included. The constitution (`III. Test-First Development`) mandates tests written before implementation, and plan.md's Project Structure already enumerates the specific test files this feature requires.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P1/P2/P3) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- File paths are exact and relative to the repo root

## Path Conventions

Single project, new sibling library package `planalign_optimizer/` (mirrors `planalign_fit/`, `planalign_ensemble/`) plus one CLI command module in `planalign_cli/commands/`, per plan.md's Project Structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the new package and CLI entry point so Foundational and per-story work has somewhere to land.

- [X] T001 Create the `planalign_optimizer/` package directory with an empty `planalign_optimizer/__init__.py`
- [X] T002 [P] Create `planalign_cli/commands/optimize.py` with a Typer command stub (`planalign optimize <spec_path>`, no behavior yet) and register it in `planalign_cli/main.py`'s command group, matching how `planalign_cli/commands/fit.py`/`backtest.py` are registered
- [X] T003 [P] Create empty test modules with pytest markers configured — `tests/test_optimizer_spec_io.py`, `tests/test_optimizer_design_space.py`, `tests/test_optimizer_evaluate.py`, `tests/test_optimizer_search.py`, `tests/test_optimizer_pareto.py`, `tests/test_optimizer_export.py`, `tests/test_optimizer_metrics.py` (all `-m fast`), and `tests/test_optimizer_end_to_end.py` (`-m integration`)

**Checkpoint**: Package and CLI skeleton exist; nothing runs yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The Pydantic spec/result models, the lever registry, the metric vocabulary, and spec validation — every user story evaluates candidates through these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Define the design-space and objective/constraint input models (`LeverSpec`, `DesignSpaceSpec`, `ObjectiveTerm`, `ConstraintSpec`, `ObjectiveConstraintSpec`) with field validators (exactly one of `choices`/`bounds` per `kind`, `bounds.min < bounds.max`, no duplicate lever names, 1-2 objectives, `percentile` in 1-99) in `planalign_optimizer/models.py`, per data-model.md
- [X] T005 Define the result models (`ConstraintResult`, `Candidate`, `OptimizerRun`) in `planalign_optimizer/models.py`, per data-model.md (depends on T004 — same file)
- [X] T006 [P] Build the v1 lever registry — a mapping from lever name strings (e.g. `employer_match.tier_1_rate`, `auto_enrollment.default_deferral_rate`, `vesting_schedule`) to the `SimulationConfig` field path each one overlays, covering match formula tiers/caps, AE default rate + scope, auto-escalation params, eligibility rules, and vesting-schedule choice (per research.md §5) — in `planalign_optimizer/design_space.py`
- [X] T007 [P] Build the supported metric vocabulary constant — re-export `planalign_ensemble.models.CANONICAL_METRICS` plus `irs_compliance_pass` — in `planalign_optimizer/metrics.py`
- [X] T008 Implement `load_spec()`/`validate_spec()` in `planalign_optimizer/spec_io.py`: parse the YAML spec (contracts/spec-schema.md), validate every lever name against the T006 registry and every metric name against the T007 vocabulary, enforce the ~6-8 lever ceiling and the 1-2 objective limit, and raise a specific, actionable error naming the exact bad lever/metric/lever-count on any failure (FR-003, FR-004) (depends on T004, T006, T007)
- [X] T009 [P] Implement baseline config loading and fingerprinting (hash of the resolved baseline `SimulationConfig`) in `planalign_optimizer/baseline.py`, for stale-baseline detection on re-run (Edge Cases; `OptimizerRun.baseline_config_fingerprint`) (depends on T004)

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - State objectives and get a ranked frontier (Priority: P1) 🎯 MVP

**Goal**: A user authors a design-space + objective/constraint spec, runs `planalign optimize` with a run budget, and gets back a ranked candidate table (plus a Pareto frontier for two-objective specs), every candidate re-runnable from its stored config.

**Independent Test**: Author a two-lever spec (match tier rate, AE default rate), one objective, one constraint; run with `--max-runs 20`; confirm a non-empty ranked candidate table where every "feasible" candidate independently satisfies its constraint.

### Tests for User Story 1

> Write these tests FIRST; confirm they FAIL before implementing the corresponding module.

- [X] T010 [P] [US1] Unit tests for spec validation — valid 2-lever spec passes; unresolvable lever name, metric name, and >8 levers each fail with the specific bad value named — in `tests/test_optimizer_spec_io.py`
- [X] T011 [P] [US1] Unit tests for the grid-seeding + local-refinement sampler — samples stay within declared discrete choices / continuous bounds, and 0-lever / 1-lever design spaces degenerate to a valid trivial candidate set (Edge Cases) — in `tests/test_optimizer_design_space.py`
- [X] T012 [P] [US1] Unit tests for config-delta resolution — overlaying declared levers on a deep-copied baseline changes only the declared `to_dbt_vars` keys — in `tests/test_optimizer_evaluate.py`
- [X] T013 [P] [US1] Unit tests for the search loop's ranking behavior (feasible candidates ranked by objective value) using a mocked `ScenarioRunPool` worker, in `tests/test_optimizer_search.py`
- [X] T014 [P] [US1] Unit tests for Pareto-efficient subset computation on a small fixed candidate set (known dominated vs. frontier points) in `tests/test_optimizer_pareto.py`
- [X] T015 [P] [US1] Integration test: a small 2-lever, 1-objective, 1-constraint end-to-end run against an isolated `DATABASE_PATH`, asserting a non-empty ranked table and independently re-checking each "feasible" candidate's constraint — in `tests/test_optimizer_end_to_end.py` (marked `integration`)

### Implementation for User Story 1

- [X] T016 [US1] Implement the grid-seeding + coordinate-descent local-refinement sampler, bounded by the requested candidate count, in `planalign_optimizer/design_space.py` (depends on T006, T011)
- [X] T017 [US1] Implement config-delta resolution — overlay declared `LeverSpec` values onto a deep copy of the baseline `SimulationConfig`, diff `to_dbt_vars(baseline)` vs. `to_dbt_vars(candidate)` for the reported delta — in `planalign_optimizer/evaluate.py` (depends on T006, T009, T012)
- [X] T018 [US1] Implement point-estimate metric extraction from one candidate's `fct_workforce_snapshot`, reusing `planalign_ensemble.extract`'s query logic for `CANONICAL_METRICS`, in `planalign_optimizer/metrics.py` (depends on T007)
- [X] T019 [US1] Implement candidate evaluation — build a `ScenarioJob` from the resolved config, submit to `ScenarioRunPool`, and classify the result as `feasible`/`infeasible`/`non_evaluable` against the spec's constraints — in `planalign_optimizer/evaluate.py` (depends on T017, T018)
- [X] T020 [US1] Implement the bounded search loop — submit sampled candidates through `ScenarioRunPool` via `resolve_worker_count`, collect `Candidate` results, rank feasible candidates by objective value — in `planalign_optimizer/search.py` (depends on T016, T019)
- [X] T021 [US1] Implement Pareto-efficient subset computation for two-objective specs in `planalign_optimizer/pareto.py` (depends on T020, T014)
- [X] T022 [US1] Wire the `planalign optimize` CLI command — parse `<spec.yaml>` and flags, call `spec_io.load_spec` → `search` → `pareto`, print a console summary and ranked candidate table — in `planalign_cli/commands/optimize.py` (depends on T002, T008, T020, T021)

**Checkpoint**: User Story 1 is fully functional and independently testable — a spec in, a ranked candidate table out.

---

## Phase 4: User Story 2 - Guardrails against runaway or misleading search (Priority: P1)

**Goal**: The search never exceeds its budget, always reports a result, names unsatisfiable constraints instead of faking a recommendation, is reproducible under a seed, and never touches an undeclared lever.

**Independent Test**: Run a spec with `--max-runs 5` and an unreachable constraint; confirm the run stops at exactly 5 evaluated candidates, reports zero feasible candidates, and names the never-satisfied constraint.

### Tests for User Story 2

- [X] T023 [P] [US2] Unit tests for run-budget accounting — a run never evaluates more than N distinct candidates; duplicate reuse (FR-012) does not consume budget; failed candidates (FR-016) do consume budget — in `tests/test_optimizer_search.py`
- [X] T024 [P] [US2] Unit tests for search determinism — the same spec + search seed reproduces the same sequence of evaluated candidates and the same ranked output across repeated runs (SC-003) — in `tests/test_optimizer_search.py`
- [X] T025 [P] [US2] Unit tests for the undeclared-lever pinning guarantee — every candidate's effective config matches baseline on every field not listed in `DesignSpaceSpec.levers` — in `tests/test_optimizer_evaluate.py`
- [X] T026 [P] [US2] Unit tests for infeasible-spec reporting — an unreachable constraint yields zero feasible candidates and names the binding constraint(s), never a false recommendation (SC-006) — in `tests/test_optimizer_search.py`
- [X] T027 [P] [US2] Unit tests for exact-match-only candidate dedup — two candidates with identical declared-lever values reuse the prior result and don't consume additional budget; near-but-not-exact continuous values do NOT dedup — in `tests/test_optimizer_design_space.py`
- [X] T028 [P] [US2] Unit tests for failed-candidate handling — a crashed/timed-out/no-output scenario run is recorded as `"failed"` (distinct from `"infeasible"`), is never retried, and still consumes one unit of run budget — in `tests/test_optimizer_evaluate.py`

### Implementation for User Story 2

- [X] T029 [US2] Enforce the mandatory `--max-runs` flag (no default; the command exits non-zero naming the missing flag if omitted) in `planalign_cli/commands/optimize.py` (depends on T022)
- [X] T030 [US2] Implement a dedicated, deterministic search-path RNG (independent of per-candidate simulation seeds, per research.md §7) driving which candidates the sampler and refinement step choose, in `planalign_optimizer/search.py` (depends on T020, T024)
- [X] T031 [US2] Implement hard run-budget enforcement in the search loop — stop submitting new (non-duplicate) candidates once `max_runs` non-duplicate evaluations have occurred, regardless of convergence — in `planalign_optimizer/search.py` (depends on T020, T023)
- [X] T032 [US2] Implement best-found-so-far / zero-feasible reporting — when the budget exhausts, report the best feasible candidate found, or, if none, that zero candidates satisfied all constraints and which constraint(s) were never met (FR-011, SC-006) — in `planalign_optimizer/search.py` (depends on T031, T026)
- [X] T033 [US2] Implement exact-match candidate identity/dedup keyed on declared-lever effective values (no rounding or tolerance) in `planalign_optimizer/design_space.py` (depends on T016, T027) [FR-012]
- [X] T034 [US2] Implement structural undeclared-lever pinning — candidate construction only ever mutates a deep copy of baseline on the declared lever fields, never anything else — in `planalign_optimizer/evaluate.py` (depends on T017, T025) [FR-001]
- [X] T035 [US2] Implement failed-candidate classification — a `ScenarioJob`/`JobResult` failure (crash, timeout, no usable output) is recorded as `Candidate.status == "failed"`, never retried, and always counted against budget — in `planalign_optimizer/evaluate.py` (depends on T019, T028) [FR-016]

**Checkpoint**: User Stories 1 AND 2 both work — a bounded, deterministic, honestly-reported search.

---

## Phase 5: User Story 3 - Export and drill down for client presentation (Priority: P2)

**Goal**: A completed run's full candidate table (and frontier) exports to a file usable outside the terminal, and every candidate's underlying scenario data stays queryable afterward without re-running anything.

**Independent Test**: Run a completed optimizer job, export its results, confirm the export contains every evaluated candidate's config delta/objective/constraint status, and confirm at least one candidate's `.duckdb` is independently queryable.

### Tests for User Story 3

- [X] T036 [P] [US3] Unit tests for export completeness — the exported candidate table contains every evaluated candidate (feasible, infeasible, non-evaluable, failed) with no omissions, and includes a Pareto sheet only for two-objective runs — in `tests/test_optimizer_export.py`

### Implementation for User Story 3

- [X] T037 [US3] Implement the candidate ledger writer (`candidates.csv`) and the per-candidate retained-`.duckdb` directory layout (`<output>/candidates/candidate-NNNN/scenario.duckdb`) in `planalign_optimizer/export.py` (depends on T020)
- [X] T038 [US3] Implement the Excel/JSON export (candidate table + Pareto sheet when applicable), reusing `planalign_orchestrator.excel_exporter` conventions, in `planalign_optimizer/export.py` (depends on T037, T021, T036)
- [X] T039 [US3] Implement human-readable `report.md` generation (ranking, frontier, binding-constraint summary) in `planalign_optimizer/report.py` (depends on T037)
- [X] T040 [US3] Wire `--output` directory handling into the CLI command — write the resolved `spec.yaml` copy, `candidates.csv`, `report.md`, and `optimizer_results.xlsx` per the cli-contract.md output layout — in `planalign_cli/commands/optimize.py` (depends on T022, T038, T039)

**Checkpoint**: Optimizer output is exportable and drill-down-capable — usable in an actual client conversation.

---

## Phase 6: User Story 4 - Evaluate candidates against distributional risk (Priority: P3)

**Goal**: When ensemble data exists and the user explicitly names a percentile for a constraint, that constraint is checked against the metric's percentile value instead of a point estimate; otherwise point-estimate stays the default, with the evaluation mode always labeled.

**Independent Test**: Run the optimizer twice on the same spec — once with constraints at point-estimate, once with an explicit conservative percentile — and confirm the percentile run marks no more candidates feasible than the point-estimate run.

### Tests for User Story 4

- [X] T041 [P] [US4] Unit tests for percentile-based constraint evaluation — activates only when `ConstraintSpec.percentile` is explicitly set; falls back to point-estimate (clearly labeled) when no ensemble data is available for that metric; never auto-selects a percentile — in `tests/test_optimizer_metrics.py`

### Implementation for User Story 4

- [X] T042 [US4] Implement percentile-based constraint evaluation — read `fct_metric_distributions` from a pre-existing ensemble aggregate database for the constraint's metric/year, per the query pattern in `docs/guides/seed_ensembles.md` — in `planalign_optimizer/metrics.py` (depends on T018, T041)
- [X] T043 [US4] Wire evaluation-mode selection (point-estimate vs. percentile, explicit-only) and mode labeling into candidate constraint classification in `planalign_optimizer/evaluate.py` (depends on T019, T042) [FR-015]
- [X] T044 [US4] Implement `irs_compliance_pass` metric evaluation from the `dq_compliance_monitoring` mart in `planalign_optimizer/metrics.py` (depends on T007) [FR-004]

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Rounding out the CLI contract and closing the remaining edge cases.

- [X] T045 [P] Implement `--dry-run` — validate the spec and print the planned initial candidate set without evaluating anything or consuming budget — in `planalign_cli/commands/optimize.py`
- [X] T046 [P] Wire `--parallel N` through to `resolve_worker_count`, matching `planalign batch --parallel` semantics, in `planalign_cli/commands/optimize.py`
- [X] T047 [P] Implement stale-baseline detection — compare a re-run's resolved baseline fingerprint against `OptimizerRun.baseline_config_fingerprint` and surface a clear warning on mismatch (Edge Cases) — in `planalign_optimizer/baseline.py`
- [X] T048 [P] Write `docs/guides/plan_design_optimizer.md`, mirroring `docs/guides/seed_ensembles.md`'s structure (run, spec shape, budget/guardrails, percentile evaluation, export, cost notes)
- [X] T049 Run the quickstart.md walkthrough end-to-end against an isolated database and confirm every step's expected output

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational only. This is the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational; layers guardrail enforcement onto the search/evaluate code User Story 1 builds — implement after US1 for a working codebase, though its tests can be written in parallel with US1's.
- **User Story 3 (Phase 5)**: Depends on Foundational + a working search loop (US1's `search.py`/`pareto.py`) to have something to export.
- **User Story 4 (Phase 6)**: Depends on Foundational + US1's `evaluate.py`/`metrics.py`; independent of US2/US3.
- **Polish (Phase 7)**: Depends on whichever stories are in scope for the release being finalized.

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories — the MVP.
- **US2 (P1)**: Builds on US1's search/evaluate code paths (adds enforcement, not new capability); independently testable via its own acceptance scenarios once wired in.
- **US3 (P2)**: Builds on US1's search output; independent of US2.
- **US4 (P3)**: Builds on US1's evaluate/metrics code; independent of US2/US3.

### Within Each User Story

- Tests are written and confirmed failing before implementation.
- Models/registries (Foundational) before sampling/evaluation logic.
- Sampling + evaluation before the search loop.
- Search loop before Pareto ranking, export, and percentile evaluation (all consume its output).
- Story complete before moving to the next priority.

### Parallel Opportunities

- Setup: T002 and T003 in parallel (different files); T001 first (creates the directory T002 may reference).
- Foundational: T006, T007, T009 in parallel once T004/T005 land (different files; T004→T005 is same-file, sequential).
- All Phase 3 (US1) test tasks T010-T015 in parallel (different files).
- All Phase 4 (US2) test tasks T023-T028 in parallel (different files, some sharing `tests/test_optimizer_search.py` — see note below).
- Phase 7 polish tasks T045-T048 in parallel (different files).
- Different user stories' implementation phases may be staffed in parallel by different developers once Foundational is done, though US2/US3/US4 each read code US1 produces, so in a single-developer flow, sequential P1→P1→P2→P3 is simplest.

**Note on `tests/test_optimizer_search.py`**: T013 (US1), T023/T024/T026 (US2) all add tests to this one file. Treat them as parallel-safe only across different developers/worktrees adding distinct test functions; in a single sequential flow, run them in the listed order to avoid merge conflicts within one file.

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together (different files):
Task: "Unit tests for spec validation in tests/test_optimizer_spec_io.py"
Task: "Unit tests for the sampler in tests/test_optimizer_design_space.py"
Task: "Unit tests for config-delta resolution in tests/test_optimizer_evaluate.py"
Task: "Unit tests for search ranking in tests/test_optimizer_search.py"
Task: "Unit tests for Pareto subset computation in tests/test_optimizer_pareto.py"
Task: "Integration test for a 2-lever end-to-end run in tests/test_optimizer_end_to_end.py"
```

## Parallel Example: Foundational

```bash
# Launch after T004/T005 (models.py) land:
Task: "Build the v1 lever registry in planalign_optimizer/design_space.py"
Task: "Build the supported metric vocabulary in planalign_optimizer/metrics.py"
Task: "Implement baseline fingerprinting in planalign_optimizer/baseline.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational — **CRITICAL**, blocks all stories.
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: run the quickstart.md steps 1-5 against an isolated `--database`; confirm a ranked candidate table appears and reproduces under the same seed.
5. Demo: `planalign optimize <spec.yaml> --max-runs 20` producing a ranked, re-runnable candidate table.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. Add US1 → validate independently → MVP demo (ranked frontier from a spec).
3. Add US2 → validate independently → trustworthy, bounded, reproducible search.
4. Add US3 → validate independently → exportable, client-presentable output.
5. Add US4 → validate independently → distributional-risk-aware constraint evaluation.
6. Polish → full CLI contract (`--dry-run`, `--parallel`, stale-baseline warning, docs).

### Parallel Team Strategy

With multiple developers, after Foundational:
- Developer A: US1 (core search).
- Developer B: starts US2's test suite against US1's evolving interfaces, then wires enforcement once US1's `search.py`/`evaluate.py` stabilize.
- Developer C: US3 (export) once US1's `search.py` output shape is stable.
- Developer D: US4 (percentile evaluation) once US1's `metrics.py`/`evaluate.py` land.

---

## Notes

- `[P]` tasks touch different files with no unmet dependencies.
- `[US#]` maps every user-story-phase task to its spec.md story for traceability.
- Tests are written first per task, and must fail before the corresponding implementation task lands (constitution III).
- Commit after each task or logical group.
- Stop at any phase checkpoint to validate that story independently before continuing.
- Every validation run uses an isolated `--database`/`DATABASE_PATH` — never `dbt/simulation.duckdb` — per the project's isolated-DB rule.
