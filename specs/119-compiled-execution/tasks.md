# Tasks: Compiled DAG Execution — #470 Hardening

**Input**: Design documents from `/specs/119-compiled-execution/` (rewritten 2026-07-19 for #470)
**Prerequisites**: plan.md, spec.md, research.md (R1–R14), data-model.md, contracts/{engine-interface,compiled-bundle,parity-report}.md, quickstart.md

**Tests**: INCLUDED and gating — the six #470 regressions are written RED against the checked-in prototype before any hardening code (plan "Ordered Delivery" step 1).

**Prototype baseline (already merged into this branch, kept)**: `optimization.execution_engine` config enum + loader test, factory wiring + runner-type test, `engine/{fallback,compiled_runner,plan_cache,materialize}.py` with 23 green unit tests, and the foundational smoke (`tests/integration/test_engine_fallback_smoke.py`). #470 supersedes several of its mechanisms — the hand selector, shared `dbt/target` reads, ambient `DATABASE_PATH` delegation, catch-all error fallback, and transactionless materialization are deliberately deleted or rebuilt below.

**Organization**: US2 (semantics & isolation, P1) is the machinery and comes first; US1 (faster with identical results, P1) is the proof layer; US3 (visibility, P2) makes evidence auditable. The six acceptance gates run strictly ordered in the final phase; the default flip is unreachable before them.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Create scaffolds: `tests/fixtures/compiled_execution.py` (shared engine-test fixtures: tiny-census config, isolated-DB helpers, workspace tmp roots), `tests/invariants/test_comparison.py`, `tests/unit/engine/{test_workspace,test_context,test_preflight,test_transaction}.py` placeholders, and `planalign_orchestrator/engine/{workspace,context,preflight,transaction}.py` empty modules; verify `var/` gitignore covers `var/compiled_execution/`

---

## Phase 2: Foundational — the six #470 regressions, RED first

**Purpose**: Encode the prototype's known defects as failing tests before touching implementation (plan step 1; quickstart "Red regression suite")

**⚠️ CRITICAL**: Each test MUST fail against the current prototype for its intended reason before any Phase 3 work

- [X] T002 [P] Regression 1 in `tests/unit/engine/test_preflight.py`: a project hook that is a pure dbt `log()` expression classifies as `informational_log` (no SQL, no delegation); prototype's `render_hook` raises `UnsupportedNodeError` → RED
- [X] T003 [P] Regression 2 in `tests/unit/engine/test_preflight.py`: an unsupported/unproven selector (e.g. `state:modified`, `@model`, misspelled name) must yield typed `KnownUnsupportedSemantics(code='selector_context'|'empty_selection')`, never a successful zero-node invocation; prototype's hand matcher returns `[]` → direct success → RED
- [X] T004 [P] Regression 3 in `tests/unit/engine/test_workspace.py`: in-process dbt delegation must target the runner's explicit database even when ambient `DATABASE_PATH` points elsewhere (assert via generated run profile + a probe table landing in the explicit DB); prototype's `invoke_dbt_inprocess` inherits ambient env → RED
- [X] T005 [P] Regression 4 in `tests/unit/engine/test_transaction.py`: a multi-node invocation whose second node fails must leave the target database byte-unchanged (rollback before any error propagation/delegation); prototype writes node 1 without a transaction → RED
- [X] T006 [P] Regression 5 in `tests/unit/engine/test_workspace.py`: after a bundle is published, a delegated dbt build/run (which recompiles into its own target) must not change the SQL bytes the engine subsequently executes (hash-verify bundle content); prototype reads shared `dbt/target/compiled` → RED
- [X] T007 [P] Regression 6 in `tests/invariants/test_comparison.py`: baseline `(x,x,y)` vs candidate `(x,y,y)` (equal totals, different multiplicities) must report divergence with per-row multiplicity counts; current comparison uses set-`EXCEPT` → RED
- [X] T008 Run the six regressions and record each failure mode (`pytest -q tests/unit/engine/test_preflight.py tests/unit/engine/test_transaction.py tests/unit/engine/test_workspace.py tests/invariants/test_comparison.py`); confirm every failure matches its intended prototype defect before proceeding

**Checkpoint**: the defect surface is pinned — hardening begins

---

## Phase 3: User Story 2 — Preserve dbt semantics and database isolation (Priority: P1)

**Goal**: Isolated workspaces, immutable bundles, dbt-native selection, complete fail-closed preflight, transactional execution, typed-only delegation

**Independent Test**: the six regressions turn GREEN; a full tiny compiled run leaves the shared dev DB and shared `dbt/target` untouched; forced partial failure rolls back; `engine=dbt` behavior is unchanged

- [X] T009 [US2] Implement `planalign_orchestrator/engine/workspace.py`: `RunArtifactWorkspace` per data-model.md — root `var/compiled_execution/<run_id>/`, generated run-scoped `profiles.yml` embedding the normalized absolute `db_manager.db_path` (assert equality; refuse shared dev DB during validation runs), unique `staging/`, `delegations/<seq>-<uuid>/`, `logs/`, `bundles/` roots, `CREATED→ACTIVE→CLOSED/FAILED_RETAINED` lifecycle; unit tests in `tests/unit/engine/test_workspace.py`
- [X] T010 [US2] Rework `planalign_orchestrator/engine/fallback.py`: every programmatic dbt call passes `--project-dir <repo>/dbt --profiles-dir <workspace>/profile --target-path <fresh delegation dir> --log-path <fresh log dir> --threads 1` (contract §3); no ambient `DATABASE_PATH` reliance; fresh mutable target per delegation; greens regression 3 and the delegation half of regression 5
- [X] T011 [P] [US2] Implement `planalign_orchestrator/engine/context.py`: `StaticProjectContext` (project/package/selector digest, dbt+adapter versions, profile digest, manifest digest), `RelationState` (existence/type/columns → state digest, read-only inspection), `RenderContext` (canonical digest over command semantics, vars, selected ids, relation-state, render identity, database-path digest) per data-model.md; unit tests in `tests/unit/engine/test_context.py`
- [X] T012 [US2] Rebuild `planalign_orchestrator/engine/plan_cache.py`: DELETE the hand-written selector matcher; deserialize the dbt manifest and resolve selection/exclusion/order through dbt 1.8.8 selector+graph APIs (research R5) with a fail-closed supported-option allowlist; manifest reuse keyed by `StaticProjectContext`; compile into a unique staging target and atomically publish immutable bundles under `bundles/<context_digest>/` with `bundle.json` + per-file SHA-256 verification (contracts/compiled-bundle.md publication protocol); zero-node resolution → typed `empty_selection`; greens regression 2 and the bundle half of regression 5; update `tests/unit/engine/test_plan_cache.py` to the dbt-native semantics (real-project session fixture replaces the miniature manifest where selector fidelity matters)
- [X] T013 [US2] Implement `planalign_orchestrator/engine/preflight.py`: typed `InvocationRequest` parsing (every token consumed or classified), hook classification (`informational_log` for pure `log()`, `connection_sql` for known PRAGMA/SET, `transactional_sql` for the guarded-delete idiom, anything else → `KnownUnsupportedSemantics(code='hook')`), relation-state freeze, precomputed DDL/DML + projections + schema-change decisions, frozen `InvocationPlan` or typed unsupported result (research R6/R7); greens regression 1; unit tests in `tests/unit/engine/test_preflight.py`
- [X] T014 [US2] Implement `planalign_orchestrator/engine/transaction.py` and trim `materialize.py` to frozen-operation execution (no semantic discovery inside the transaction): context-managed connection per invocation, connection hooks before `BEGIN`, all frozen operations inside one transaction, `COMMIT`/`ROLLBACK`+close on every exception with rollback outcome captured (research R8); greens regression 4; unit tests in `tests/unit/engine/test_transaction.py`
- [X] T015 [US2] Rebuild `planalign_orchestrator/engine/compiled_runner.py` as the contract §2 state machine (`RECEIVED→PREFLIGHTING→{UNSUPPORTED→DELEGATING | PLANNED→EXECUTING→{COMMITTED | ROLLED_BACK | ROLLED_BACK_UNSUPPORTED→DELEGATING}}`): delegation ONLY on typed `KnownUnsupportedSemantics` (late occurrence = rolls back first + counts unexpected); generic compile/SQL/lock/catalog/hash/internal errors fail with run/year/stage/invocation/node/phase/statement context; workspace lifecycle owned here; rewrite `tests/unit/engine/test_compiled_runner.py` to the state machine (valid/invalid transitions, typed-only delegation, error context)
- [X] T016 [US2] Integration `tests/integration/test_engine_isolation.py`: full tiny compiled run in an isolated DB — shared dev DB SHA-256 unchanged, shared `dbt/target/` mtimes untouched during the run, all dbt work under `var/compiled_execution/<run_id>/`, plus an `engine=dbt` compatibility smoke proving default behavior is untouched
- [X] T017 [US2] Green everything: six regressions + all `tests/unit/engine` + `pytest -m "fast and orchestrator" -q` with zero regressions

**Checkpoint**: the compiled path is isolated, atomic, fail-closed — proof layer next

---

## Phase 4: User Story 1 — Faster without changing results (Priority: P1)

**Goal**: The comparators and harnesses that can PROVE parity, determinism, memory, and speed

**Independent Test**: `planalign parity` verdicts IDENTICAL on tiny; Feature 113 suites pass under `engine=compiled`; harness produces paired-engine artifacts with RSS + fallback fields

- [X] T018 [US1] Implement `planalign_orchestrator/tools/parity.py` + `planalign_cli/commands/parity.py` (`planalign parity <years> --config --census --seed [--json]`) per contracts/parity-report.md: two fresh isolated DBs (refuse shared dev DB), ordered schema comparison first, symmetric `EXCEPT ALL` value comparison (`fct_yearly_events` excl. `created_at` values, `fct_workforce_snapshot` excl. `snapshot_created_at` values), grouped multiplicity diagnostics with bounded samples, exit 0 iff IDENTICAL AND zero unexpected fallbacks; update `tests/invariants/comparison.py` (or the comparator it delegates to) to multiset semantics — greens regression 6; register command in `planalign_cli/main.py`
- [X] T019 [P] [US1] Engine-parametrize the Feature 113 suites (`tests/integration/test_multi_year_invariants.py`, `tests/integration/test_determinism.py`) so both engines are selectable (session fixture/env toggle); compiled parametrization green locally including the rerun-on-top path
- [X] T020 [P] [US1] Extend the perf harness for paired-engine evidence (research R13): `scripts/perf_profile/profile_config.py` + `run_matrix.py` gain campaign ID + engine dimensions in sample names (baseline and candidate never overwrite), config/census fingerprints, delegation/unexpected-fallback totals, and recursive process-tree peak RSS via psutil; `make_large_census.py --factor 14` documented for the 105,070-row memory census; `build_report.py` renders paired-engine tables
- [X] T021 [US1] Integration `tests/integration/test_engine_parity.py`: in-test tiny parity (both engines, isolated DBs, multiset comparator) as the fast standing guard for Gate 1

**Checkpoint**: proof machinery exists — evidence phases can run

---

## Phase 5: User Story 3 — Understand every delegation and parity failure (Priority: P2)

**Goal**: Structured, append-only evidence: per-invocation records, terminal run metadata, forced-delegation safety

**Independent Test**: run summary shows mode/nodes/timing/zero-delegations for a clean run; every forced unsupported code delegates pre-write with identical outputs; terminal metadata row appended per run

- [X] T022 [US3] Emit `InvocationExecutionRecord` for every terminal state (data-model.md fields incl. planned/attempted/completed nodes, rollback outcome, bounded error context) and implement `planalign_orchestrator/run_summary.py` aggregation surfaced in the CLI run summary (direct/delegated/unexpected counts + stable reason codes; explicit "0 unexpected fallbacks" line)
- [X] T023 [US3] Implement `planalign_orchestrator/run_execution_metadata.py`: append-only terminal relation keyed by `run_id` (schema per data-model.md `RunExecutionMetadata`; insert-only, never touching the Feature 109 startup row), written on success AND failure paths; unit tests + a test proving `execution_engine` stays excluded from the drift `config_fingerprint`
- [X] T024 [US3] Forced-delegation matrix in `tests/integration/test_engine_forced_delegation.py`: force each stable reason code (`command`, `option`, `selector_context`, `empty_selection`, `resource_type`, `materialization`, `incremental_strategy`, `hook`, `schema_change`, `full_refresh`) — each delegates before any write, completes with outputs identical to the dbt path (SC-007), and appears in summary + terminal metadata with its code

**Checkpoint**: every behavior is observable and auditable

---

## Phase 6: Ordered Acceptance Gates, Default Flip, Close-out

**Purpose**: spec "Acceptance Gate Order" — strictly sequential; stop at first failure; later evidence never waives an earlier gate

- [X] T025 Gate 1 — Tiny isolated exact parity: `planalign parity 2025-2027 --config tests/fixtures/invariant_config.yaml --census tests/fixtures/invariant_census.csv --seed 42 --json` → IDENTICAL, zero `EXCEPT ALL` rows both directions, zero unexpected fallbacks, shared dev DB hash unchanged; store JSON as GateEvidence
- [X] T026 Gate 2 — Multi-year determinism: engine-parametrized Feature 113 invariants + determinism suites green under compiled, plus identical-input compiled rerun parity; store evidence
- [X] T027 Gate 3 — Development + 60K exact parity: `planalign parity` at `data/census_preprocessed.parquet` (7,505) and `var/perf_profile/census_large.parquet` (60,040) → IDENTICAL both; store evidence
- [X] T028 Gate 4 — 100K memory/completion: generate the 105,070-row census (`make_large_census --factor 14`), run compiled 3-year in an isolated DB to completion, record recursive peak RSS; no OOM; store evidence
- [X] T029 Gate 5 — Paired performance: fresh paired baseline/candidate campaigns (tiny/dev/60K, ≥3 warm reps, same environment) including ALL compilation/preflight/delegation cost → compiled ≥1.8× end-to-end on the 60K benchmark (2.0× target), tiny/dev reported; store paired samples + report
- [X] T030 Gate 6 — Zero unexpected fallbacks across the entire supported acceptance matrix (gates 1–5 runs' terminal metadata audited); assemble the ordered `GateEvidence` set proving gates 1–6
- [X] T031 ~~Default flip~~ CANCELLED per Session 2026-07-19 Gate-5 decision (close-as-oracle): default remains `dbt`; compiled ships opt-in. Documentation pass done in lieu of flip. Original text: `optimization.execution_engine` default → `compiled` in `planalign_orchestrator/config/performance.py` + `config/simulation_config.yaml` docs; rerun Gate 1 tiny parity on the new default plus an explicit `--engine dbt` compatibility smoke; documentation pass (CLAUDE.md, dbt/CLAUDE.md engine section, changelog)
- [ ] T032 Close-out: commit sequence + PR (stacked on `118-dedupe-init-invocations`) with the gate-evidence table; closes #456 and #470 on merge; comment evidence on #470, update epic #469 and roadmap tracker #463; note #471 (native-kernel spike) as next, #472–#475 remain blocked pending #471 GO

---

## Dependencies & Execution Order

- **Phases strictly sequential at boundaries**: 1 → 2 (all six RED) → 3 → 4 → 5 → 6; gates inside Phase 6 are internally ordered T025→T030 with T031 unreachable before T030
- **Phase 2**: T002–T007 all [P] (different test concerns); T008 last
- **Phase 3 internal**: T009 → T010; T011 [P] alongside T009/T010; T012 needs T009+T011; T013 needs T012; T014 needs T013; T015 needs T010+T013+T014; T016–T017 last
- **Phase 4**: T018 first (parity comparator greens regression 6); T019/T020 [P]; T021 needs T018
- **Phase 5**: T022 → T023; T024 needs T015+T022
- **Long-pole awareness**: T027–T029 are hours of simulation runs; schedule them in the background while T031's doc pass is drafted, but do NOT start T031's flip until T030's audit is written

### Suggested MVP Scope

Phases 1–4 + Gates 1–3 (T025–T027): a hardened, isolated, transactional compiled engine with proven exact parity at all measured scales — still opt-in. Gates 4–6 + flip complete the feature.

---

## Task Summary

| Phase | Tasks | Story |
|---|---|---|
| 1 Setup | T001 | — |
| 2 Six regressions RED | T002–T008 | — |
| 3 Semantics & isolation | T009–T017 | US2 (9 tasks) |
| 4 Proof machinery | T018–T021 | US1 (4 tasks) |
| 5 Evidence & visibility | T022–T024 | US3 (3 tasks) |
| 6 Gates, flip, close-out | T025–T032 | — |

**Total**: 32 tasks. Hard gates: all six regressions RED before Phase 3; all six acceptance gates PASSED in order before T031's default flip.
