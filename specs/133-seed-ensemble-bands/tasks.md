---

description: "Task list for 133-seed-ensemble-bands"
---

# Tasks: Seed Ensembles — Distribution Bands, Exceedance Risk, and Variance Attribution

**Input**: Design documents from `/specs/133-seed-ensemble-bands/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included. Constitution Principle III (Test-First Development) mandates tests before implementation for all significant features; fast unit tests must stay under the 10s suite budget.

**Organization**: Grouped by user story. Each story is independently implementable, testable, and deliverable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US4, mapping to spec.md user stories
- All paths are repository-relative from `/Users/nicholasamaral/Developer/fidelity_planalign`

**Phase ordering note**: US3 (attribution) and US4 (export) are both P3. US4 runs first because US3 depends on the dbt seed refactor — the feature's single largest risk — and plan.md sequences the risky work last so it can never block delivery of the other three stories.

---

## Phase 1: Setup

**Purpose**: Package scaffolding

- [X] T001 Create `planalign_ensemble/` package with `__init__.py` exporting the public surface named in `specs/133-seed-ensemble-bands/contracts/cli.md` (stub signatures only)
- [X] T002 Register `planalign_ensemble` in the packages list in `pyproject.toml`
- [X] T003 [P] Confirm `var/` is git-ignored so `var/ensembles/` artifacts never enter version control, in `.gitignore`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Entities, seed planning, and metric extraction — required by every user story

**⚠️ CRITICAL**: No user story work can begin until this phase completes

- [X] T004 [P] Write failing tests for ensemble entities (duplicate-seed rejection naming the repeats, `attribution_seed_count <= seed_count`, `seed_count >= 1`, `min_seeds >= 1`) in `tests/test_ensemble_models.py`
- [X] T005 Implement Pydantic v2 entities — `EnsembleSpec`, `Threshold`, `SeedPlan`, `SeedRunOutcome`, `MetricDistribution`, `RiskStatement`, `AttributionShare`, `Subsystem` enum — per `data-model.md`, in `planalign_ensemble/models.py`
- [X] T006 [P] Write failing tests for seed planning (deterministic derivation from base seed + N, identical list on repeat, explicit list honored, duplicates rejected, run-count arithmetic) in `tests/test_ensemble_planner.py`
- [X] T007 Implement `plan_ensemble()` — seed derivation, duplicate rejection, ensemble/per-seed path layout under `var/ensembles/<timestamp>-<scenario>/`, total run count and disk estimate for the FR-021 disclosure — in `planalign_ensemble/planner.py`
- [X] T008 [P] Write failing tests for metric extraction, including absent-metric detection returning NULL rather than 0 (FR-016), in `tests/test_ensemble_extract.py`
- [X] T009 Implement per-seed metric extraction for the six headline metrics, reusing the aggregate expressions in `planalign_orchestrator/excel_exporter.py::_calculate_summary_metrics` and mapping `total_employer_plan_cost` to `SUM(total_employer_contributions)` per FR-009a, using short-lived read-only connections, in `planalign_ensemble/extract.py`

**Checkpoint**: Entities, planning, and extraction ready — user stories can begin

---

## Phase 3: User Story 1 — Headline numbers become bands (Priority: P1) 🎯 MVP

**Goal**: `--seeds N` runs N isolated seed runs through the existing pool and writes `fct_metric_distributions` with P10/P25/P50/P75/P90, mean, stddev, and seed count.

**Independent Test**: Run an N-seed ensemble against a small census in isolated databases; confirm one row per (scenario, metric, year), percentiles bracketing per-seed values, and a repeat run producing bit-identical aggregates.

### Tests for User Story 1

- [X] T010 [P] [US1] Write failing tests for percentile computation against hand-computed NumPy linear-interpolation expectations, and for bit-stability across repeated aggregation of the same seed-ordered inputs (SC-002, SC-003), in `tests/test_ensemble_aggregate.py`
- [X] T011 [P] [US1] Write failing tests for the sufficiency gate — N=1 and below-minimum samples yield NULL percentiles with `is_sufficient=False`, NULL distinguishable from 0.0 (FR-013/013a/013b) — in `tests/test_ensemble_aggregate.py`
- [X] T012 [P] [US1] Write failing integration test running a small multi-seed ensemble end-to-end into `tmp_path` databases, asserting no write to any per-seed database after its run (FR-011a) and no touch of `dbt/simulation.duckdb`, in `tests/test_ensemble_end_to_end.py`

### Implementation for User Story 1

- [X] T013 [US1] Implement `aggregate_ensemble()` — NumPy linear percentiles over seed-ordered values, sample stddev, sufficiency gate writing NULL percentiles below `min_seeds` — in `planalign_ensemble/aggregate.py`
- [X] T014 [US1] Implement the `fct_metric_distributions` and `fct_metric_seed_values` table DDL and writes into the ensemble database, with the grain and invariants in `data-model.md`, in `planalign_ensemble/aggregate.py`
- [X] T015 [P] [US1] Implement ensemble provenance — `ensemble_id`, `ensemble_seed_list`, `ensemble_seed_count`, `ensemble_role`, `ensemble_member_paths` columns added via the additive `_evolve_provenance_schema` pattern used in `planalign_orchestrator/run_metadata.py` — in `planalign_ensemble/provenance.py`
- [X] T016 [US1] Implement the module-level seed worker function (pickle-crossable per the `ScenarioRunPool` constraint) building a `ConstructionSpec` per seed, following the `planalign_backtest/simulate.py::run_seed` pattern, in `planalign_ensemble/runner.py`
- [X] T017 [US1] Implement `run_ensemble()` — build one `ScenarioJob` per seed with config and seed fully resolved before submission (FR-004), submit to `ScenarioRunPool`, size workers via `resolve_worker_count`, collect `SeedRunOutcome` per seed including failures with reasons — in `planalign_ensemble/runner.py`
- [X] T018 [US1] Implement the `--discard-seed-dbs` post-aggregation cleanup, retaining the ensemble database and warning that reuse is forfeited (FR-028), in `planalign_ensemble/runner.py`
- [X] T019 [P] [US1] Implement the Rich distribution table and the insufficient-sample rendering shown in `contracts/cli.md`, always printing the seed count (FR-026), in `planalign_ensemble/report.py`
- [X] T020 [US1] Implement the pre-execution plan disclosure (seed list, worker budget, run count, disk estimate, output path) and live progress on pool events (FR-006, FR-021), in `planalign_ensemble/report.py`
- [X] T021 [US1] Add `--seeds`, `--seed-list`, `--min-seeds`, `--discard-seed-dbs` to **both** the `run` subcommand and the hidden `default` command in `planalign_cli/commands/simulate.py` — extract a shared option set rather than duplicating a third time (research.md D8)
- [X] T022 [US1] Wire the ensemble exit codes (0/1/2/3/130) from `contracts/cli.md`, ensuring a below-minimum sample exits 0 and an interrupt writes no aggregate (SC-010), in `planalign_cli/commands/simulate.py`
- [X] T023 [P] [US1] Add the batch-equivalent `--seeds` option with identical semantics per scenario (FR-001) in `planalign_cli/commands/batch.py`

**Checkpoint**: User Story 1 fully functional — bands ship. This is the MVP.

---

## Phase 4: User Story 2 — Probability of blowing the budget (Priority: P2)

**Goal**: Configured thresholds produce per-year exceedance probabilities with seed counts.

**Independent Test**: Set a threshold below every observed value and another above every observed value; confirm 100% and 0% exactly, with intermediate thresholds matching a hand count.

### Tests for User Story 2

- [X] T024 [P] [US2] Write failing tests for exceedance boundaries — below-min threshold yields exactly 1.0, above-max exactly 0.0, intermediate matches a direct count (SC-004) — in `tests/test_ensemble_risk.py`
- [X] T025 [P] [US2] Write failing tests for a threshold naming an unavailable metric reporting not-evaluable with the metric named, and for insufficient-sample metrics being excluded rather than contributing (FR-016, FR-013c), in `tests/test_ensemble_risk.py`

### Implementation for User Story 2

- [X] T026 [P] [US2] Add the Pydantic v2 ensemble threshold configuration block with validation at load (Principle V) in `planalign_orchestrator/config/`
- [X] T027 [US2] Implement `evaluate_thresholds()` computing per-year exceedance over successful seeds, excluding insufficient-sample metrics, in `planalign_ensemble/risk.py`
- [X] T028 [US2] Implement the risk-statement report section including the not-evaluable line, and the empty-section behavior when no thresholds are configured, in `planalign_ensemble/report.py`
- [X] T029 [US2] Add the repeatable `--threshold metric:value` option with parse validation to both command definitions in `planalign_cli/commands/simulate.py`

**Checkpoint**: User Stories 1 and 2 both work independently

---

## Phase 5: User Story 4 — Bands travel to the client deliverable (Priority: P3)

**Goal**: Workbook export carries the distribution sheet.

**Independent Test**: Run a batch with ensembles enabled, export, confirm distribution rows match stored values and that a non-ensemble export is unchanged.

### Tests for User Story 4

- [X] T030 [P] [US4] Write failing tests asserting the distribution sheet matches stored values, withheld percentiles render as empty cells rather than 0, and a non-ensemble export gains no sheet (FR-025, FR-013a), in `tests/test_ensemble_export.py`

### Implementation for User Story 4

- [X] T031 [US4] Implement the `Metric_Distributions` sheet following the existing `_write_*_sheets` and `_format_worksheet` conventions, added only when an ensemble aggregate exists, in `planalign_orchestrator/excel_exporter.py`

**Checkpoint**: Bands are deliverable outside the terminal

---

## Phase 6: User Story 3 — What actually drives the spread (Priority: P3)

**Goal**: Ranked OFAT variance attribution for termination, hiring, and promotion, with enrollment and merit reported as not stochastic.

**Independent Test**: On a purpose-built scenario, confirm a deliberately dominant subsystem ranks first and an effectively deterministic one ranks at/near zero; confirm an unfrozen attribution ensemble reproduces a plain ensemble exactly at the same seeds.

**⚠️ Stage 6a is a hard gate.** The seed refactor ships as a pure refactor with no behavioral consumer. The T033 byte-identical test and the T038 fingerprint-stability check MUST both pass before any attribution logic is written.

### Stage 6a: Seed refactor (byte-identical, no attribution logic)

- [X] T032 [US3] Create the `subsystem_seed(subsystem)` macro resolving to `var('random_seed_' ~ subsystem, var('random_seed', 42))` in `dbt/macros/utils/subsystem_seed.sql`
- [X] T033 [P] [US3] Write the byte-identical gate test building an isolated database before and after the refactor at the same seed and config, comparing `fct_yearly_events` and `fct_workforce_snapshot` exactly, in `tests/test_subsystem_seed_identity.py`
- [X] T034 [US3] Convert the 3 termination seed call sites in `dbt/models/intermediate/events/int_termination_events.sql` (selection hash L89; `generate_termination_date` seed argument L101, L110) to `subsystem_seed('termination')`
- [X] T035 [P] [US3] Convert the 4 termination seed call sites to `subsystem_seed('termination')` in `dbt/models/intermediate/events/int_new_hire_termination_events.sql`
- [X] T036 [P] [US3] Convert the 2 hiring seed call sites to `subsystem_seed('hiring')` in `dbt/models/intermediate/events/int_hiring_events.sql`
- [X] T037 [P] [US3] Convert the 1 promotion seed call site to `subsystem_seed('promotion')` in `dbt/models/intermediate/events/int_promotion_events.sql`
- [X] T038 [US3] Emit `random_seed_<subsystem>` vars **only when a freeze is requested**, so default runs keep an unchanged var set and `config_fingerprint`, in `planalign_orchestrator/config/export.py`
- [X] T039 [US3] Write tests proving freeze effectiveness and containment — pinning `random_seed_termination` holds terminations identical across seeds while hiring and promotion vary exactly as in an unfrozen pair (FR-022) — in `tests/test_subsystem_seed_identity.py`

**Gate**: T033 and T038's fingerprint-stability check must pass before proceeding. Do not start Stage 6b otherwise.

### Stage 6b: Attribution

- [X] T040 [P] [US3] Write failing tests for the paired-difference variance share, for the FR-019b reuse guard rejecting a seed match under a differing `config_fingerprint`, and for reuse producing shares identical to a fresh baseline (SC-011, SC-012), in `tests/test_ensemble_attribution.py`
- [X] T041 [P] [US3] Write failing tests asserting enrollment and merit report `stochastic_status='not_stochastic'` with `variance_share=None` and never 0.0 (research.md D1), in `tests/test_ensemble_attribution.py`
- [X] T042 [US3] Implement baseline resolution — attribution seeds validated as a subset of the headline seed list, headline runs reused when seed **and** `compute_config_fingerprint` both match, fresh baseline runs executed otherwise, reuse/execute counts recorded (FR-019a/b/c) — in `planalign_ensemble/attribution.py`
- [X] T043 [US3] Implement `attribute_variance()` — per-subsystem frozen ensembles, seed-paired variance reduction per metric and year, ranked output, non-stochastic subsystems reported structurally — in `planalign_ensemble/attribution.py`
- [X] T044 [US3] Implement the attribution report table including the method/limits statement, seed counts, reuse counts, and the not-stochastic lines shown in `contracts/cli.md` (FR-020), in `planalign_ensemble/report.py`
- [X] T045 [US3] Add `--attribution` and `--attribution-seeds` to both command definitions, with the run-count disclosure stating the multiplier before execution (FR-021), in `planalign_cli/commands/simulate.py`
- [X] T046 [US3] Add the `Variance_Attribution` sheet including `stochastic_status` and reuse counts in `planalign_orchestrator/excel_exporter.py`
- [X] T047 [P] [US3] Write the integration test for attribution ranking on a purpose-built scenario with one dominant and one effectively deterministic subsystem (SC-006, SC-007) in `tests/test_ensemble_end_to_end.py`

**Checkpoint**: All four user stories independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T048 [P] Write the ensembles guide covering bands, thresholds, attribution, cost, and the enrollment/merit non-stochasticity finding, in `docs/guides/seed_ensembles.md`
- [X] T049 [P] Add the seed-ensembles section to `CLAUDE.md` following the existing feature-section conventions
- [X] T050 Run the full `quickstart.md` validation end-to-end against isolated databases and correct any drift between documented and actual output
- [X] T051 [P] Update `CHANGELOG.md` and bump the version in `_version.py` and `pyproject.toml` per `docs/VERSIONING_GUIDE.md`
- [ ] T052 Verify the fast suite still completes under the 10s budget (Constitution Principle III) via `pytest -m fast`
- [X] T053 Confirm no task introduced a write to `dbt/simulation.duckdb` — grep the feature diff for the shared database path and for `dbt build`/`dbt run` invocations without an explicit target

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational; consumes US1's aggregate in practice but is testable against fixture distributions
- **US4 (Phase 5)**: depends on US1 (needs an aggregate to export)
- **US3 (Phase 6)**: depends on Foundational; Stage 6b depends on the Stage 6a gate
- **Polish (Phase 7)**: depends on all desired stories

### Critical path

```
Setup → Foundational → US1 (MVP) → US2 → US4
                            └─────→ US3 Stage 6a (gate) → US3 Stage 6b
```

### Within User Story 3

T032 → T034–T037 (call-site conversions, parallel across files) → T033 gate → T038/T039 → T040–T047.
The gate is not advisory: attribution measured on an unverified refactor produces numbers nobody can defend.

### Parallel Opportunities

- T004, T006, T008 — foundational tests, different files
- T010, T011, T012 — US1 tests, independent
- T015, T019, T023 — provenance, report, batch CLI: different files
- T035, T036, T037 — three separate dbt models, no shared lines
- T040, T041 — attribution tests
- T048, T049, T051 — documentation

---

## Parallel Example: User Story 1

```bash
# Tests first, in parallel:
Task: "Percentile + bit-stability tests in tests/test_ensemble_aggregate.py"
Task: "Sufficiency gate tests in tests/test_ensemble_aggregate.py"
Task: "End-to-end isolation test in tests/test_ensemble_end_to_end.py"

# Then implementation across independent files:
Task: "Provenance columns in planalign_ensemble/provenance.py"
Task: "Rich distribution table in planalign_ensemble/report.py"
Task: "Batch --seeds option in planalign_cli/commands/batch.py"
```

---

## Implementation Strategy

### MVP First

1. Phase 1 Setup → Phase 2 Foundational → Phase 3 US1
2. **STOP and VALIDATE**: run a 25-seed ensemble; verify bit-identical repeat aggregates and that the worker budget holds on a work laptop
3. Bands alone change what can be claimed in front of a client — ship here if needed

### Incremental Delivery

1. Foundational → US1 (bands, MVP)
2. US2 (exceedance risk) — thin derivation, high client value
3. US4 (export) — mechanical, makes bands portable
4. US3 (attribution) — gated seed refactor first, then attribution

### Risk Note

US3 is the only story touching production dbt models. It is sequenced last precisely so the other three ship regardless of how the refactor goes. Enrollment seeding is **not** in scope for any task here — it changes results for every existing scenario and belongs in its own change with its own before/after evidence (research.md D1).

---

## Notes

- `[P]` = different files, no dependencies on incomplete tasks
- Every behavioral validation uses isolated databases; the shared `dbt/simulation.duckdb` is never built into (CLAUDE.md §8)
- Tests must fail before implementation (Constitution Principle III)
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
