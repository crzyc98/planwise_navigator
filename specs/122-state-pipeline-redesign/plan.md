# Implementation Plan: Normalize the Event & Workforce-State Pipeline

**Branch**: `122-state-pipeline-redesign` | **Date**: 2026-07-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/122-state-pipeline-redesign/spec.md`

## Summary

Normalize the active SQL/dbt simulation graph so each year's immutable event set is assembled once, published once, and then consumed by one authoritative workforce-state accumulator plus the existing enrollment and deferral accumulators. Migrate benefit calculations and the workforce snapshot to those declared state dependencies, replace hidden prior-snapshot lookups with a strictly prior-year orchestrator projection, and collapse STATE_ACCUMULATION to one invocation only after full-scale parity proves every preceding phase.

Before changing pipeline behavior, make Studio/API simulation attempts truly isolated: execute each attempt directly in `runs/<run_id>/simulation.duckdb`, retain failed partial databases, and atomically promote a successful run through a scenario-local current-result pointer. Every scenario-scoped API read adds backward-compatible warning headers while an attempt runs; result-bearing reads continue serving the prior successful database, and representative reads retain the two-second p95 target. Every later migration phase is compared against one frozen Feature 121 A+B database using exact schemas, bidirectional `EXCEPT ALL`, relation-column exclusions, execution counts, invariants, and shared/prior-database fingerprints.

## Technical Context

**Language/Version**: Python >=3.11; SQL/Jinja compatible with dbt Core 1.8.8; TypeScript 5.8 for the existing Studio warning surface
**Primary Dependencies**: Existing PlanAlign orchestrator and CLI, FastAPI, Pydantic v2, dbt Core 1.8.8, dbt DuckDB 1.8.1, DuckDB 1.0.0, PyYAML, pytest 7.4, psutil; no new dependency
**Storage**: Fresh DuckDB at `workspaces/<workspace>/scenarios/<scenario>/runs/<run_id>/simulation.duckdb` for each Studio/API attempt; atomic scenario-local `current_result.json`; existing run metadata/provenance files; new internal dbt workforce accumulator and disposable prior-year projection; no public mart schema change
**Testing**: pytest unit/API/integration suites, dbt schema/data tests, manifest graph-contract tests, frozen-baseline bidirectional `EXCEPT ALL`, invariant/determinism suites, and existing performance/RSS harnesses against isolated databases
**Target Platform**: Local macOS/Linux workstations running the Python API/CLI, single-threaded dbt DuckDB execution, and the existing browser-based Studio
**Project Type**: Python orchestrator/CLI/API plus dbt analytics project and a React Studio client
**Performance Goals**: One STATE_ACCUMULATION invocation per year; one execution of each publication model per year; whole-run invocation count measured as evidence with no fixed-total acceptance threshold; peak RSS no more than 110% of a freshly characterized A+B baseline; at least 95% of representative scenario reads complete within two seconds both while idle and while serving the latest success during an active run
**Constraints**: Exact public schema, deterministic IDs/sequences, row multiplicity, and unexcluded output parity; SQL-only active pipeline; newly allocated run database for every Studio/API attempt; prior databases and `dbt/simulation.duckdb` remain byte-unchanged; no PII or golden DuckDB files committed; no command boundary removed before its phase gate passes
**Scale/Scope**: Authoritative validation at 60,040 employees over 2025–2029 (accepted baseline approximately 645,130 yearly events and 351,243 workforce snapshots), plus reference/synthetic edge workloads and all dbt marts selected from the `marts` path

## Constitution Check

*GATE: Passed before Phase 0 research and re-checked after Phase 1 design.*

| Principle / gate | Status | Design evidence |
|---|---|---|
| Event immutability and determinism | PASS | The event candidate union preserves IDs, sequence, schema, and multiplicity; `fct_yearly_events` remains append-scoped and is published once per run/year. |
| Modular architecture | PASS | Workforce, enrollment, and deferral remain separate state domains. The touched 947-line simulation service and 738-line year executor are split at their run-lifecycle and execution-strategy seams so they return below the constitution's approximate 600-line ceiling rather than receiving more responsibilities. |
| Test-first development | PASS | Characterization and graph contracts precede migrations; every phase blocks on full-scale parity and regression suites. |
| Transparency and auditability | PASS | Run-local metadata/provenance and failed partial DBs are retained; pointer promotion and warning headers make served versus active runs explicit. |
| Typed configuration | PASS | No public configuration fields are added; checked artifacts and pointer/validation records receive versioned typed models. |
| Enterprise scale | PASS | The authoritative gate is the 60,040-employee, five-year workload with RSS, CPU, wall, model-time, and invocation evidence. |
| Isolated behavioral validation | PASS | All candidate/baseline tests use explicit isolated paths; file fingerprints guard the shared dev DB and pre-existing run archives. |
| SQL/dbt architecture | PASS | The active pipeline stays SQL-only and uses dbt `ref`/`source` edges except for documented, orchestrator-built prior-year projections. |
| Database path resolution | PASS | `dbt/simulation.duckdb` remains the direct-CLI default, while managed runs use the already-supported explicit path override through `get_database_path()`; API consumers stay behind the centralized resolver. No component constructs an ad hoc query target. |
| No new oversized modules | PASS | New pointer/projection/parity responsibilities are extracted into small modules; existing oversized service files are not grown with those responsibilities. |

No constitution violation requires an exception.

## Project Structure

### Documentation (this feature)

```text
specs/122-state-pipeline-redesign/
├── plan.md
├── research.md
├── data-model.md
├── baseline-characterization.json       # generated in the first implementation phase
├── phase-gates.md                        # accumulated gate outcomes during implementation
├── quickstart.md
├── contracts/
│   ├── parity-exclusions.yaml
│   ├── parity-gate.md
│   ├── run-database-lifecycle.md
│   ├── scenario-read-consistency.yaml
│   └── state-pipeline-dag.md
└── tasks.md                              # generated later by /speckit.tasks
```

### Source Code (repository root)

```text
dbt/
├── dbt_project.yml
└── models/
    ├── sources.yml
    ├── intermediate/
    │   ├── int_current_year_events.sql                 # new union/sequence boundary
    │   ├── int_workforce_state_accumulator.sql         # new canonical state
    │   ├── int_active_employees_prev_year_snapshot.sql
    │   ├── int_prev_year_workforce_summary.sql
    │   ├── int_prev_year_workforce_by_level.sql
    │   ├── int_employee_contributions.sql
    │   ├── int_employee_match_calculations.sql
    │   ├── int_employer_core_contributions.sql
    │   ├── int_employee_state_by_year.sql               # removed after parity
    │   ├── int_workforce_snapshot_optimized.sql          # removed after parity
    │   └── schema.yml
    └── marts/
        ├── fct_yearly_events.sql
        ├── fct_employer_match_events.sql
        ├── fct_workforce_snapshot.sql
        └── schema.yml

planalign_orchestrator/
├── change_validation.py
├── state_pipeline_validation.py                       # new typed artifacts/gates
├── workforce_state_projection.py                      # new prior-year boundary
├── pipeline_orchestrator.py
└── pipeline/
    ├── event_generation_executor.py
    ├── stage_execution_strategies.py                   # extracted parallel/legacy paths
    ├── workflow.py
    └── year_executor.py

planalign_api/
├── main.py
├── routers/                                            # DB-backed scenario reads/exports
├── services/
│   ├── database_path_resolver.py
│   ├── current_result.py                               # new pointer/read context
│   └── simulation/
│       ├── service.py
│       ├── run_execution.py                            # extracted process/stream lifecycle
│       ├── run_archiver.py
│       ├── result_handlers.py
│       └── results_reader.py
└── storage/workspace_storage.py

planalign_studio/
├── services/api.ts
└── components/Layout.tsx

scripts/perf_profile/
├── profile_config.py
└── run_matrix.py

tests/
├── fixtures/
├── api/
├── integration/
│   ├── test_run_database_isolation.py
│   ├── test_state_pipeline_characterization.py
│   └── test_state_pipeline_parity.py
├── performance/
│   └── test_scenario_read_latency.py
├── unit/
│   ├── orchestrator/test_pipeline_graph_contract.py
│   ├── simulation/
│   ├── storage/
│   ├── test_change_validation.py
│   └── test_database_path_resolver.py
└── helpers/
```

**Structure Decision**: Extend the existing Python/dbt/API/Studio layout. Keep database lifecycle logic behind a small current-result abstraction shared by the resolver and simulation service, extract subprocess streaming from the oversized simulation facade, and separate optional/legacy execution strategies from the oversized year executor. Keep temporal projection construction in the orchestrator and parity artifact generation separate from the already broad change-validation entry point. Move contribution/match models out of inherited event-tag ownership when necessary, while preserving their relation names.

## Implementation Strategy and User-Story Gates

1. **Foundation — freeze and characterize A+B**: regenerate a clean baseline from revision `c6ad648` (or its verified equivalent), record normalized input/code/construction fingerprints and aggregate behavior, check in the characterization and explicit parity allowlist, and extend validators so missing relations, schema drift, one-sided absence, duplicates, and unlisted differences fail.
2. **US1 — isolate run storage and preserve current results**: execute each Studio/API-managed simulation attempt in a never-before-used run DB, atomically publish only completed results, attach active-run warnings to every scenario-scoped read, serve the published DB for result-bearing reads during an active attempt, retain failed partial DBs, remove automatic run pruning from completion, preserve bounded legacy fallbacks, and prove the two-second p95 read target. Calibration retains its existing run lifecycle.
3. **US2 — publish events once**: introduce the single candidate union/sequence relation, make `fct_yearly_events` its thin incremental publisher, remove the fact from STATE_ACCUMULATION, and prove node-level execution count plus full-scale parity without removing other command boundaries.
4. **US3 — shadow workforce state**: introduce the canonical accumulator and strictly-prior workforce projection, explicitly contract-test the enrollment projection and separate enrollment/deferral domains, compare all declared workforce columns for every year against the accepted snapshot, and keep all existing consumers unchanged until the full gate passes.
5. **US3 — migrate consumers incrementally**: move employer eligibility, employee contributions, employer core, and match calculations one at a time to the authoritative domain accumulators. Run the same frozen-baseline gate after each move.
6. **US3 — compose the snapshot and remove legacy state**: rewrite `fct_workforce_snapshot` as composition, then remove the orphan and scratch models only after manifest audits prove there are no consumers. Update the calibration workflow's affected selections while preserving calibration output and failure behavior.
7. **US4 — make dependency order machine-verifiable**: enforce ownership, temporal boundaries, audit sinks, and dependency closure for both normal simulation and calibration workflows.
8. **US5 — consolidate STATE_ACCUMULATION**: remove the scratch-only full-refresh exception and execute the normalized state selection in one invocation per year. Re-run failure attribution, determinism, stale rerun, partial failure, Feature 107, Feature 112, calibration regressions, reference, Studio-scale, and RSS gates; record the observed whole-run invocation count without enforcing an assumed total.

Each phase writes ignored machine evidence to `var/state_pipeline_validation/<phase>/gate.json`, references the same checked `baseline_id`, and blocks the next phase on any failure. Prior run DB/archive fingerprints and the shared dev DB fingerprint are captured before and after every attempt.

## Complexity Tracking

No constitution violations are introduced, so no complexity exception is required.
