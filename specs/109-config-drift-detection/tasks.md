# Tasks: Config Drift Detection

**Input**: Design documents from `/specs/109-config-drift-detection/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/run-metadata.md, quickstart.md

**Tests**: INCLUDED — the project constitution (Principle III) mandates test-first development; each story writes failing tests before implementation.

**Organization**: Tasks are grouped by user story. US1 (warn on drift) is the MVP; US2 (seed-distinct messaging) and US3 (auditable history) layer on the same module.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Single project at repository root: `planalign_orchestrator/`, `tests/` (per plan.md Structure Decision).

---

## Phase 1: Setup

**Purpose**: Module skeleton matching the contract, so tests have a target to import against.

- [X] T001 Create `planalign_orchestrator/run_metadata.py` skeleton per `contracts/run-metadata.md`: `RUN_METADATA_TABLE` constant, `DriftStatus` enum, frozen `DriftCheckResult` dataclass, and stub signatures for `compute_config_fingerprint()` and `check_and_record_run()` (raising `NotImplementedError`), full type hints, module docstring referencing spec 109

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The deterministic fingerprint and the `run_metadata` table DDL — every story depends on both.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Write failing unit tests for `compute_config_fingerprint()` in `tests/test_run_metadata.py` (marker: fast): identical configs → identical hash across two loads; changing a result-affecting value (e.g. `simulation.target_growth_rate`) → different hash; changing `simulation.random_seed` → **same** hash (seed excluded, D1); changing non-result-affecting `setup.clear_tables` → same hash; Decimal/date values serialize deterministically; use `tests/fixtures/config.py` minimal configs
- [X] T003 Implement `compute_config_fingerprint()` in `planalign_orchestrator/run_metadata.py`: SHA-256 hex of `json.dumps(vars, sort_keys=True, default=str)` where `vars = to_dbt_vars(config)` with `"random_seed"` popped; make T002 pass
- [X] T004 Write failing unit tests for table lifecycle in `tests/test_run_metadata.py` (marker: fast): lazy `CREATE TABLE IF NOT EXISTS` on first stamp against an in-memory DuckDB (`tests/fixtures/database.py`); schema columns match `contracts/run-metadata.md` §2; second stamp appends (2 rows, both retained); table name matches neither `int_` nor `fct_` prefix (survives `maybe_full_reset` patterns)
- [X] T005 Implement table DDL + append + latest-row read helpers (private functions) in `planalign_orchestrator/run_metadata.py` using the `db_manager` `_run(conn)` callback style from `pipeline/state_manager.py`; make T004 pass

**Checkpoint**: Fingerprint is deterministic and the table can be created/appended/read — user story implementation can begin.

---

## Phase 3: User Story 1 - Warn When Re-Running Against a Database Built with a Different Configuration (Priority: P1) 🎯 MVP

**Goal**: Every run stamps its provenance and loudly warns (non-blocking) when the target DB was last written under a different config/seed, across all writer entry points.

**Independent Test**: Fresh isolated DB → run → info note; unchanged re-run → silent; change one config value → re-run → prominent warning naming the mismatch, run still completes (quickstart.md steps 1–3).

### Tests for User Story 1 (write first, ensure they FAIL)

- [X] T006 [P] [US1] Write failing unit tests for the `check_and_record_run()` state machine in `tests/test_run_metadata.py` (marker: fast): NO_HISTORY on empty/missing table (info, not warning — FR-006); MATCH is silent (SC-003); DRIFT on fingerprint change sets `config_changed`; UNKNOWN on injected `duckdb.Error` (never raises — FR-005); exactly one row appended per call (FR-008); `full_reset=True` sets `suppressed_by_full_reset` and downgrades log level; `run_type="calibration"` downgrades log level; DRIFT warning text includes prior run timestamp and both FR-010 remedies; use `caplog` for message assertions
- [X] T007 [P] [US1] Write failing integration test in `tests/test_run_metadata_integration.py` (marker: integration): against an isolated `DATABASE_PATH` DB with mock dbt runner fixtures (`tests/fixtures/mock_dbt.py`), run `PipelineOrchestrator.execute_multi_year_simulation` twice — second run with a changed config emits the drift warning before year execution begins and completes successfully; `dry_run=True` stamps **no** record

### Implementation for User Story 1

- [X] T008 [US1] Implement `check_and_record_run()` in `planalign_orchestrator/run_metadata.py`: read latest row → compare fingerprint+seed → emit log message per `contracts/run-metadata.md` §3 (warning for DRIFT; info for NO_HISTORY/UNKNOWN/downgraded cases) → append record; wrap all DB work in `try/except duckdb.Error` returning `DriftCheckResult(status=UNKNOWN, ...)`; make T006 pass
- [X] T009 [US1] Wire into `PipelineOrchestrator.execute_multi_year_simulation` in `planalign_orchestrator/pipeline_orchestrator.py` (~line 291, inside `ExecutionMutex`, after `maybe_full_reset()`/`warn_if_stale_years_beyond()`): skip when `dry_run`; pass `full_reset=` derived from `setup.clear_tables` + `clear_mode == 'all'` (same keys `maybe_full_reset` reads); `run_type="simulate"`; make T007 pass
- [X] T010 [US1] Wire into `CalibrationRunner.run_calibration` in `planalign_orchestrator/calibration_runner.py` before the per-year builds, with `run_type="calibration"` and the calibration-tailored info message (comp levers diverge and DC tables go stale by design — research D3); add a fast unit test in `tests/test_run_metadata.py` asserting CalibrationRunner invokes the check with `run_type="calibration"`

**Checkpoint**: MVP complete — quickstart.md steps 1–3 demonstrable end-to-end on an isolated DB.

---

## Phase 4: User Story 2 - Seed Changes Are Called Out Distinctly (Priority: P2)

**Goal**: A seed change against an existing DB is named explicitly in the warning, with old and new values; combined config+seed drift reports both.

**Independent Test**: Build isolated DB with seed A, re-run with seed B (config otherwise identical) → warning says the random seed changed and shows A → B.

### Tests for User Story 2 (write first, ensure they FAIL)

- [X] T011 [US2] Write failing unit tests in `tests/test_run_metadata.py` (marker: fast): seed-only change → DRIFT with `seed_changed=True`, `config_changed=False`, warning text contains both seed values and does NOT claim config changed; seed+config change → both flags set and warning reports both; `prior_seed`/`current_seed` populated on the result

### Implementation for User Story 2

- [X] T012 [US2] Extend the DRIFT message composition in `planalign_orchestrator/run_metadata.py` to branch on `{config only | seed only | both}` with prior→current seed values and 12-char fingerprint short-hashes per `contracts/run-metadata.md` §3; make T011 pass

**Checkpoint**: Seed drift is distinctly actionable; US1 behavior unchanged (re-run T006/T007).

---

## Phase 5: User Story 3 - Run History Is Auditable After the Fact (Priority: P3)

**Goal**: Each database is self-describing — full append-only run history queryable from the DB alone (SC-005), surviving full resets.

**Independent Test**: Two runs with different configs into one isolated DB, then `duckdb <db> "SELECT ... FROM run_metadata ORDER BY run_timestamp DESC"` shows two rows with distinct fingerprints, seeds recorded, timestamps ordered.

### Tests for User Story 3 (write first, ensure they FAIL)

- [X] T013 [P] [US3] Write failing integration test in `tests/test_run_metadata_integration.py` (marker: integration): after two differing runs, `run_metadata` holds two rows with distinct `config_fingerprint`, correct `start_year`/`end_year`/`run_type`/`random_seed`, monotonic timestamps; a run with `setup.clear_tables: true` + `clear_mode: all` wipes `fct_`/`int_` tables but `run_metadata` rows survive and the new row has `full_reset=TRUE`

### Implementation for User Story 3

- [X] T014 [US3] Close any gaps T013 exposes (audit columns `scenario_id`, `plan_design_id`, `planalign_version` populated from config/`planalign_orchestrator/_version.py`) in `planalign_orchestrator/run_metadata.py`; make T013 pass
- [X] T015 [P] [US3] Document the audit surface: add the canonical provenance query and drift-warning explanation to `docs/` (or the troubleshooting guide `docs/guides/error_troubleshooting.md` if that is the established home) and a brief note in `CLAUDE.md` §11 Troubleshooting pointing to `run_metadata`

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T016 Validate quickstart.md end-to-end on a real isolated DB (`/tmp/run109/iso.duckdb`, per the isolated-DB rule — never `dbt/simulation.duckdb`): steps 1–3 produce info → silent → warning; audit query returns expected rows; confirm startup overhead is imperceptible (SC-006)
- [X] T017 [P] Run `pytest -m fast` and confirm the suite still completes <10s (constitution) and new fast tests are auto-marked; run full new-test files with coverage on `planalign_orchestrator/run_metadata.py` (target ≥90%)
- [X] T018 [P] Update `CHANGELOG.md` under the next version with the config-drift-detection entry (table schema, non-blocking semantics, entry points covered)
  - **Adapted**: CHANGELOG.md states it is generated at release time from conventional commits, not hand-curated per PR; the entry will be drafted from this feature's `feat:` commit at the next release. No manual edit made.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none
- **Foundational (Phase 2)**: T001 → (T002 → T003), (T004 → T005); T002/T004 are [P]-eligible with each other but shown sequenced because they share `tests/test_run_metadata.py`
- **US1 (Phase 3)**: needs Phase 2; T006 ∥ T007 (different files) → T008 → T009 → T010
- **US2 (Phase 4)**: needs T008 (message composition exists); independent of T009/T010
- **US3 (Phase 5)**: needs T008/T009 (records written by real runs); T013 → T014; T015 anytime after T008
- **Polish (Phase 6)**: needs all desired stories

### User Story Dependencies

- **US1 (P1)**: only Foundational — the MVP
- **US2 (P2)**: builds on US1's message path; independently testable via seed-only change
- **US3 (P3)**: exercises records US1 writes; independently testable via the audit query

### Parallel Opportunities

- T006 ∥ T007 (unit vs. integration test files)
- T013 ∥ T015 (test file vs. docs)
- T017 ∥ T018 (verification vs. changelog)
- After Phase 2, US2's T011 could proceed in parallel with US1's wiring tasks (T009/T010) since it only depends on T008 — but same-file edits to `run_metadata.py` (T008/T012) must serialize

## Parallel Example: User Story 1

```bash
# Write both failing test layers together:
Task: "T006 unit tests for check_and_record_run state machine in tests/test_run_metadata.py"
Task: "T007 integration test for drift warning via PipelineOrchestrator in tests/test_run_metadata_integration.py"
```

## Implementation Strategy

**MVP first**: Phases 1–3 (T001–T010) deliver the entire headline value — silent contamination becomes loud. Stop, run quickstart steps 1–3, demo. US2 (T011–T012) is a small messaging refinement; US3 (T013–T015) is verification + docs on top of records US1 already writes. Every phase leaves the suite green and the feature shippable.

**Format validation**: ✅ all 18 tasks use `- [ ] Txxx [P?] [Story?] description + explicit file path`; story labels only in Phases 3–5.
