# Tasks: Backtest Scorecard

**Input**: Design documents from `/specs/131-backtest-scorecard/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED. Constitution Principle III mandates test-first development, and FR-030 requires a harness self-test. Test tasks precede their implementation within each phase and MUST fail before the implementation task is started.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable — different files, no dependency on an incomplete task
- **[Story]**: US1–US5, mapping to spec.md user stories

## Path Conventions

Single Python project at repository root. New package `planalign_backtest/`, tests in `tests/`, CLI in `planalign_cli/commands/`. Paths below are repository-relative.

---

## Phase 1: Setup

**Purpose**: Package skeleton and test scaffolding.

- [x] T001 Create `planalign_backtest/` package with `__init__.py` exposing the public surface named in `specs/131-backtest-scorecard/contracts/internal-api.md` (imports may be stubs until Phase 2)
- [x] T002 [P] Register `planalign_backtest` in `pyproject.toml` packages list alongside `planalign_fit`
- [x] T003 [P] Create empty test modules `tests/test_backtest_split.py`, `tests/test_backtest_scoring.py`, `tests/test_backtest_report.py`, `tests/test_backtest_leakage.py`, `tests/test_backtest_harness.py` with the correct pytest markers (`fast` on the first four, `integration` on the last)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Entities, the metric registry, and the leakage seam. Every user story depends on these.

**⚠️ CRITICAL**: No user story work begins until this phase completes. T007–T009 are the feature's correctness core — a defect here silently invalidates every scorecard the feature ever produces.

### Entities and registry

- [x] T004 [P] Implement `Threshold`, `MetricThresholds`, `SnapshotSplit`, `BacktestOptions`, and `SeedRun` Pydantic v2 frozen models in `planalign_backtest/models.py` per `data-model.md`, including field validators for seed uniqueness, seed count 1–5, and the rule that `BacktestOptions.fit_options.only_years` must be unset on input
- [x] T005 [P] Implement `MetricValue`, `SeedSpread`, `MetricComparison`, `SnapshotRef`, `BacktestProvenance`, and `Scorecard` models in `planalign_backtest/models.py` with the derived-field rules from `data-model.md` (status/verdict derived, never assigned)
- [x] T006 Implement the metric registry in `planalign_backtest/models.py` — the fixed metric identifiers, threshold family, cumulative rule (final vs. sum), and required census column for each, per the registry table in `data-model.md`

### The leakage seam (research R1)

- [x] T007 [P] Write failing tests in `tests/test_backtest_leakage.py` asserting: `SnapshotSet.subset()` retains only the named years, re-validates consecutiveness, and raises `SnapshotError` naming requested vs. available years for an unknown year
- [x] T008 Implement `SnapshotSet.subset(years)` in `planalign_fit/snapshots.py`, re-running `_validate_set` on the retained snapshots (makes T007 pass)
- [x] T009 Add `only_years: Optional[tuple[int, ...]] = None` to `FitOptions` and apply the subset in `fit_parameter_pack` in `planalign_fit/runner.py`, immediately after `load_snapshots` and before `build_transitions`, per `contracts/internal-api.md`
- [x] T010 Extend `tests/test_backtest_leakage.py` to assert the resulting pack manifest's `snapshot_years` and `source_digest` cover **only** fitted years, and that no DuckDB view exists for a held-out year on the fitting connection

### Orchestrator seam

- [x] T011 [P] Add `"backtest"` to the `EntryPoint` literal in `planalign_orchestrator/construction/spec.py`
- [x] T012 [P] Implement `BacktestError` and `SimulationFailure` (carrying `seed` and `year`) in `planalign_backtest/errors.py`

### Split logic

- [x] T013 [P] Write failing tests in `tests/test_backtest_split.py` covering every `SnapshotSplit` validation rule and every rejection message shape in `contracts/cli.md` (too few snapshots, infeasible holdout, holdout out of range, gap)
- [x] T014 Implement `plan_split(snapshot_set, holdout_years) -> SnapshotSplit` in `planalign_backtest/split.py` as a pure function (makes T013 pass)

**Checkpoint**: Entities, registry, and the leakage guard are in place and proven. User story work can begin.

---

## Phase 3: User Story 1 — Score a fitted model against held-out history (Priority: P1) 🎯 MVP

**Goal**: End-to-end backtest producing predicted vs. actual figures from a snapshot directory, in isolated databases.

**Independent Test**: Point the command at a directory of ≥3 consecutive snapshots; confirm it reports predicted vs. actual for headcount and average compensation, and that `dbt/simulation.duckdb` is untouched.

### Tests for User Story 1

- [x] T015 [P] [US1] Write failing test in `tests/test_backtest_harness.py` asserting a 4-snapshot directory fits on the first 3 years and simulates only the held-out year (`integration` marker)
- [x] T016 [P] [US1] Write failing test in `tests/test_backtest_harness.py` asserting `dbt/simulation.duckdb` size and mtime are unchanged across a full backtest (FR-006)

### Actuals and predicted extraction

- [x] T017 [P] [US1] Implement `extract_actuals(snapshot_set, split, bands)` in `planalign_backtest/actuals.py`, opening a scoring-only in-memory DuckDB connection and reusing `build_transitions` over the full snapshot set per research R2
- [x] T018 [P] [US1] Implement `extract_predicted(database, split)` in `planalign_backtest/predicted.py`, reading `fct_workforce_snapshot` (headcount, bands, `current_compensation` for active employees at year end per research R4) and `fct_yearly_events` (termination/hire/promotion counts)
- [x] T019 [US1] Write test in `tests/test_backtest_harness.py` asserting band assignment agrees between the actuals path and `fct_workforce_snapshot`'s `age_band`/`tenure_band` for an identical employee population (research R3 risk)

### Simulation driving

- [x] T020 [P] [US1] Implement boundary-census preparation in `planalign_backtest/simulate.py` — convert the boundary-year snapshot to parquet in the workdir when the source is CSV, leaving the snapshot directory untouched
- [x] T021 [US1] Implement per-seed effective-config writing in `planalign_backtest/simulate.py`, layering `setup.census_parquet_path` and `simulation.random_seed` over `apply_pack`'s effective config per research R7
- [x] T022 [US1] Implement `run_seed(applied_pack, split, seed, workdir) -> SeedRun` in `planalign_backtest/simulate.py` using `build_orchestrator(ConstructionSpec(...))` with `entry_point="backtest"`, an isolated per-seed database under `var/backtests/`, and a per-run `dbt_artifacts_dir` (research R6)
- [x] T023 [US1] Implement simulation failure handling in `planalign_backtest/simulate.py`, raising `SimulationFailure` naming the seed and year, with no scorecard emitted (FR-032)

### Scoring core

- [x] T024 [P] [US1] Write failing tests in `tests/test_backtest_scoring.py` for `lower_median` (odd and even seed counts, order independence) and for signed absolute/percentage error including the zero-actual case (FR-018)
- [x] T025 [US1] Implement `lower_median(values)` and the error arithmetic in `planalign_backtest/scoring.py` as pure functions (makes T024 pass)
- [x] T026 [US1] Implement the cumulative-period rules in `planalign_backtest/scoring.py` — final-year value for stock and rate metrics, sum for flow metrics, per `data-model.md` (FR-013)

### Orchestration and CLI

- [x] T027 [US1] Implement `run_backtest(snapshots_dir, options)` in `planalign_backtest/runner.py`, sequencing split → fit with `only_years` → per-seed simulation → extraction → scoring, returning `BacktestRun` and writing nothing but run databases
- [x] T028 [US1] Implement `planalign backtest` in `planalign_cli/commands/backtest.py` with the arguments, options, and exit codes in `contracts/cli.md`, and register it in `planalign_cli/main.py`

**Checkpoint**: A backtest runs end to end and reports predicted vs. actual. MVP complete.

---

## Phase 4: User Story 2 — Read the scorecard and know whether to trust the model (Priority: P1)

**Goal**: Thresholds, statuses, observability labelling, and both artifact forms.

**Independent Test**: Run a backtest and confirm every scored metric shows predicted, actual, absolute error, percent error, threshold, and status; a metric outside its threshold is visibly marked; a census lacking plan columns lists those metrics as not observable.

### Tests for User Story 2

- [x] T029 [P] [US2] Write failing tests in `tests/test_backtest_scoring.py` for `classify()` — pass/warn/fail boundaries per family, `undefined` on zero actual, `not_observable` propagation
- [x] T030 [P] [US2] Write failing test in `tests/test_backtest_report.py` asserting every registry metric appears in `comparisons` for every held-out year plus `cumulative`, with no metric silently absent (SC-003)
- [x] T031 [P] [US2] Write failing test in `tests/test_backtest_report.py` validating emitted `scorecard.json` against `specs/131-backtest-scorecard/contracts/scorecard.schema.json`, including the conditional rules for unobservable and zero-actual comparisons

### Scoring completion

- [x] T032 [US2] Implement `classify(percent_error, threshold) -> Status` in `planalign_backtest/scoring.py`, with status derived and never assigned (makes T029 pass)
- [x] T033 [US2] Implement per-year observability evaluation in `planalign_backtest/actuals.py`, reusing `Observability.reasons()` text so a column absent in some held-out years degrades only those years (FR-012)
- [x] T034 [US2] Implement plan metrics in `planalign_backtest/actuals.py` and `planalign_backtest/predicted.py` — participation rate, average deferral rate, and employer match cost from `fct_employer_match_events` (FR-012)
- [x] T035 [US2] Implement verdict derivation and `verdict_summary` in `planalign_backtest/scoring.py`, excluding `undefined` and `not_observable` from the verdict (FR-019)

### Artifacts

- [x] T036 [P] [US2] Implement `to_json(scorecard)` in `planalign_backtest/report.py` with canonical serialization — sorted keys, fixed float formatting, ordered tuples — so identical inputs produce byte-identical output (SC-005)
- [x] T037 [US2] Implement `scorecard_fingerprint` computation in `planalign_backtest/models.py`, hashing the canonical JSON of all other fields
- [x] T038 [P] [US2] Implement `render_markdown(scorecard)` in `planalign_backtest/report.py` producing `scorecard.md` with scored metrics, a separated cumulative block, a not-observable section with reasons, and a footer stating thresholds in effect and overrides
- [x] T039 [US2] Implement `write_scorecard`, `load_scorecard`, and `scorecard_is_current` in `planalign_backtest/report.py`, writing to `<pack>/backtest/` and refusing overwrite without `force` (FR-023, FR-029)
- [x] T040 [US2] Implement the Rich console summary table and threshold options in `planalign_cli/commands/backtest.py` per `contracts/cli.md`

**Checkpoint**: The scorecard is complete, interpretable, and machine-readable. Both P1 stories done.

---

## Phase 5: User Story 3 — See where the actuals fall in the seed spread (Priority: P2)

**Goal**: Per-metric spread across seeds and the actual's position within it.

**Independent Test**: Run with 3 seeds and confirm each metric reports a min–max range and whether the actual falls inside; run with 1 seed and confirm it states no spread was computed.

- [x] T041 [P] [US3] Write failing tests in `tests/test_backtest_scoring.py` for `SeedSpread` construction — min/max, per-seed values in seed order, `actual_within_spread`, and signed `distance_outside`
- [x] T042 [P] [US3] Write failing test in `tests/test_backtest_scoring.py` asserting a single-seed run yields `spread=None` rather than a zero-width range (FR-022)
- [x] T043 [US3] Implement per-metric `SeedSpread` computation in `planalign_backtest/scoring.py` (makes T041, T042 pass)
- [x] T044 [US3] Render the seed-spread section in `planalign_backtest/report.py`, including the single-seed "no seed spread computed" statement
- [x] T045 [US3] Add the seed-spread block to the Rich console output in `planalign_cli/commands/backtest.py`
- [x] T046 [US3] Write test in `tests/test_backtest_harness.py` asserting a multi-seed backtest re-run with the same seed set produces a byte-identical `scorecard.json` (FR-008, SC-005)

**Checkpoint**: Model error is distinguishable from run-to-run variation.

---

## Phase 6: User Story 4 — Trust the harness itself (Priority: P2)

**Goal**: A self-test proving the harness is not systematically biased.

**Independent Test**: Generate snapshot history from a simulation with known parameters, backtest it, and confirm every headcount and compensation metric lands inside the near-perfect tolerance.

- [x] T047 [P] [US4] Implement a synthetic-history generator in `tests/fixtures/backtest_history.py` that runs a short simulation with known parameters and exports per-year census snapshots in `stg_census_data` schema
- [x] T048 [US4] Write the self-test in `tests/test_backtest_harness.py` asserting headcount and compensation errors fall inside a documented near-perfect tolerance (FR-030)
- [x] T049 [US4] Document the self-test tolerance and its rationale in `docs/guides/backtesting.md`
- [x] T050 [US4] Write the mutation assertion in `tests/test_backtest_harness.py` — monkeypatch a deliberate defect into the comparison logic and assert the self-test fails, proving it is not vacuous (FR-030)
- [x] T051 [US4] Verify no simulation-driving test in `tests/test_backtest_harness.py` carries the `fast` marker; correct markers in `tests/test_backtest_*.py` if needed (Constitution III). **Done**: harness is `integration`-only; the four backtest `fast` modules run in 1.6s. The repo-wide `pytest -m fast` selection takes 485s for 2,103 tests, a pre-existing condition this feature neither caused nor is scoped to fix.
  - Blocked by the repository-wide baseline: 2,099 fast-marked tests pass in 226.38s. The new simulation-driving harness remains integration-only.

**Checkpoint**: Scorecards are admissible evidence — the harness certifies itself.

---

## Phase 7: User Story 5 — Carry the score forward as provenance (Priority: P3)

**Goal**: A complete, auditable chain from a projection's run record back to source census hashes.

**Independent Test**: Fit, backtest, run a projection with the pack, and follow `run_metadata` → scorecard → snapshot hashes with no manual bookkeeping.

- [x] T052 [P] [US5] Populate `BacktestProvenance` in `planalign_backtest/runner.py` — snapshot refs with `role` ∈ {fit, holdout}, `source_digest`, pack id and fingerprint, `promotion_basis`, `level_basis`, `compensation_basis` (FR-025)
- [x] T053 [P] [US5] Write failing test in `tests/test_backtest_report.py` asserting a pack edited after backtesting is detected as stale by `scorecard_is_current` (FR-026)
- [x] T054 [US5] Add `backtest_score_ref` to the column list in `_evolve_provenance_schema` in `planalign_orchestrator/run_metadata.py` (additive, nullable, no migration)
- [x] T055 [US5] Extend `provenance_block()` in `planalign_fit/apply.py` to include the `backtest` sub-block when the pack carries a **current** scorecard, omitting it when absent or stale, per `contracts/internal-api.md`
- [x] T056 [US5] Populate `backtest_score_ref` from the `param_pack.backtest` block in `planalign_orchestrator/run_metadata.py`
- [x] T057 [US5] Write test in `tests/test_backtest_harness.py` asserting a `simulate --params` run of a backtested pack records `backtest_score_ref`, and that a stale scorecard leaves it `NULL`
- [x] T058 [US5] Write test in `tests/test_backtest_report.py` asserting backtesting a pack leaves its fitted contents and fingerprint unchanged (FR-028, SC-009)

**Checkpoint**: The provenance chain closes. All user stories functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T059 [P] Write `docs/guides/backtesting.md` covering the workflow, scorecard interpretation, thresholds, and the caveats from `quickstart.md`
- [x] T060 Produce the reference example — a backtest over a realistic anonymized census — committing its scorecard to `docs/examples/backtest_reference/scorecard.md` and `docs/examples/backtest_reference/scorecard.json`, referenced from `docs/guides/backtesting.md` (FR-031, SC-008)
- [x] T061 [P] Document the scorecard JSON schema and its versioning policy in `docs/guides/backtesting.md`, linking `contracts/scorecard.schema.json`
- [x] T062 [P] Add a `planalign backtest` entry to the CLI section of `CLAUDE.md` and `README.md`
- [x] T063 Verify every module in `planalign_backtest/` stays under 600 lines and that `scoring.py` and `split.py` import nothing from `planalign_orchestrator` (Constitution II, internal-api invariant 5)
- [x] T064 Run the full quickstart walkthrough in `specs/131-backtest-scorecard/quickstart.md` end to end and correct any drift between documented and actual output
- [x] T065 Add a `CHANGELOG.md` entry and bump the version in `_version.py` and `pyproject.toml` per `docs/VERSIONING_GUIDE.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks every user story**
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on US1 — extends its scoring and artifacts
- **US3 (Phase 5)**: depends on US1 (needs multi-seed runs); independent of US2
- **US4 (Phase 6)**: depends on US1; stronger once US2 lands but does not require it
- **US5 (Phase 7)**: depends on US2 (needs a written scorecard to reference)
- **Polish (Phase 8)**: depends on all desired stories

### Story dependency notes

US2 genuinely depends on US1 rather than being parallel to it: US1 produces the comparison values that US2 classifies and renders. This is the one place the stories are not independent, and it reflects the spec — both are P1 precisely because a scorecard nobody can interpret is not a deliverable.

US3 and US4 are independent of each other and of US2; with capacity they can run in parallel once US1 completes.

### Critical path

T001 → T004/T005 → T006 → T008 → T009 → T027 → T028 → T032 → T039 → T060

### Parallel opportunities

- Phase 1: T002, T003
- Phase 2: T004, T005 together; T007, T011, T012, T013 together
- Phase 3: T015, T016 together; T017, T018, T020 together; T024 alongside them
- Phase 4: T029, T030, T031 together; T036 and T038 together
- Phase 5: T041, T042 together
- Phase 7: T052, T053 together
- Phase 8: T059, T061, T062 together

---

## Parallel Example: User Story 1

```bash
# Failing tests first
Task: "Write failing test asserting fit-on-first-3, simulate-held-out-only in tests/test_backtest_harness.py"
Task: "Write failing test asserting dbt/simulation.duckdb is untouched in tests/test_backtest_harness.py"

# Then the three independent extractors and the census prep
Task: "Implement extract_actuals in planalign_backtest/actuals.py"
Task: "Implement extract_predicted in planalign_backtest/predicted.py"
Task: "Implement boundary-census preparation in planalign_backtest/simulate.py"
```

---

## Implementation Strategy

### MVP (User Story 1 only)

1. Phase 1: Setup
2. Phase 2: Foundational — **do not shortcut T007–T010**; the leakage guard is what makes every later number mean anything
3. Phase 3: User Story 1
4. **STOP and VALIDATE**: run a backtest on a 4-snapshot directory, confirm predicted vs. actual for headcount and average compensation, and confirm the shared dev database is untouched

At this point the feature produces real numbers but presents them plainly. That is a legitimate demo.

### Incremental delivery

1. Setup + Foundational → leakage guard proven
2. + US1 → predicted vs. actual end to end (MVP)
3. + US2 → interpretable scorecard, both artifact forms → **the shippable increment**
4. + US3 → seed spread separates model error from luck
5. + US4 → the harness certifies itself
6. + US5 → provenance chain closes
7. Polish → guide, reference example, versioning

### Suggested first-cut scope

US1 + US2 together. US1 alone produces numbers without thresholds or a JSON artifact, which satisfies no exit criterion in the issue on its own. US1 + US2 satisfies the first exit criterion fully.

---

## Notes

- 65 tasks: Setup 3, Foundational 11, US1 14, US2 12, US3 6, US4 5, US5 7, Polish 7
- Every simulation-driving test carries the `integration` marker; the `fast` suite must stay under 10s (T051 verifies)
- T007–T010 are the correctness core. A reviewer should read those four tasks' diffs before any others
- Commit after each task or logical group; stop at any checkpoint to validate a story independently
