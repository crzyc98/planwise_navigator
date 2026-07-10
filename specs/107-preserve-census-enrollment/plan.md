# Implementation Plan: Preserve Census Enrollment

**Branch**: `107-preserve-census-enrollment` (Spec Kit context; Git remains on `main`) | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/107-preserve-census-enrollment/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Prevent year-two census enrollment corruption by separating one-time run reset behavior from per-year dbt execution and by making immutable `fct_yearly_events` the sole post-census authority for enrollment state. Before each event-generation stage, the orchestrator will validate prior-year dependencies and atomically rebuild a scenario/plan-scoped enrollment-decision projection from the census baseline plus prior fact events. dbt enrollment models will consume that projection through a declared source and staging `ref()`, avoiding both hidden dependencies and reverse DAG edges. Isolated two-scenario integration tests, a timed audit trace, a 100K/200K-row performance gate, and an enforced sub-10-second fast-suite gate complete the validation design.

## Technical Context

**Language/Version**: Python >=3.11; dbt SQL/Jinja compatible with dbt Core 1.8.8
**Primary Dependencies**: PlanAlign orchestrator, Pydantic v2 configuration, dbt Core 1.8.8, dbt DuckDB 1.8.1, DuckDB 1.0.0, pytest 7.4, psutil
**Storage**: Existing scenario-isolated DuckDB outputs plus one disposable internal `enrollment_decision_projection` table rebuilt from census and immutable fact events; no public mart, API, or configuration schema change
**Testing**: pytest unit/integration/performance tests, dbt singular tests, a hard-timed fast-suite wrapper, and isolated temporary DuckDB databases
**Target Platform**: Local/workstation CLI runs and Studio/API-launched scenario subprocesses
**Project Type**: Python simulation engine with CLI/API entrypoints and dbt-backed event/state stages
**Performance Goals**: Fold 100K employees and 200K two-year enrollment-history inputs into exactly 100K decision-state rows in <=30 seconds with <=1,024 MiB RSS growth; fail regressions above 15% runtime or 20% memory versus the accepted baseline; complete `pytest -m fast` in <10 seconds
**Constraints**: `fct_yearly_events` remains the only post-census event authority; single-threaded dbt remains default; no mid-simulation full refresh of temporal models; no raw table reads from dbt enrollment models; no dbt cycle; all projection rebuilds are atomic, deterministic, scenario/plan scoped, and restricted to prior years
**Scale/Scope**: Multi-year scenarios across FOUNDATION, projection rebuild, enrollment decisions, event persistence, state accumulation, workforce snapshots, Studio-style minimal setup configs, explicit reset configs, and two isolated scenario/run outputs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Gate

- **I. Event Sourcing & Immutability**: PASS. Census supplies only the initial state; every later transition is replayed from immutable, scenario-scoped `fct_yearly_events`. The projection is disposable derived state, never an event store.
- **II. Modular Architecture**: PASS. A focused projection component owns fact replay; orchestration owns ordering; staging owns the declared source boundary; enrollment models own decisions. No reverse dbt dependency is introduced.
- **III. Test-First Development**: PASS. Failing unit, integration, dbt, performance, and timing gates precede production changes.
- **IV. Enterprise Transparency**: PASS. Projection rows retain fact provenance, rebuild reconciliation is logged, dependency failures retain structured context, and a timed participant trace validates audit usability.
- **V. Type-Safe Configuration**: PASS. Existing Pydantic scenario/plan identifiers scope the projection. dbt consumes it through `source()` and `ref()` rather than raw relation names.
- **VI. Performance & Scalability**: PASS. The design defines absolute 100K memory/runtime caps, accepted-baseline regression thresholds, and the constitutional fast-suite limit.

### Post-Design Re-check

- **I. Event Sourcing & Immutability**: PASS. The data flow is `census + prior fct_yearly_events -> disposable projection -> enrollment decisions -> fct_yearly_events`; intermediate event rows are no longer treated as historical authority.
- **II. Modular Architecture**: PASS. The projection module remains independent of dbt model code, and the source/staging boundary prevents a cycle.
- **III. Test-First Development**: PASS. Every production slice has a preceding failing test and an independently runnable checkpoint.
- **IV. Enterprise Transparency**: PASS. Scenario/plan identity, source event ID/year, reconciliation counts, and the under-five-minute trace are explicitly tested.
- **V. Type-Safe Configuration**: PASS. No new user configuration field is introduced; fixed internal schemas and existing validated IDs are used.
- **VI. Performance & Scalability**: PASS. The 100K/200K-row projection gate is isolated from the fast suite, while the full fast suite is independently capped at 10 seconds.

## Project Structure

### Documentation (this feature)

```text
specs/107-preserve-census-enrollment/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── prior-enrollment-projection.md
│   └── setup-clear-mode.md
└── tasks.md
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── pipeline_orchestrator.py
└── pipeline/
    ├── enrollment_projection.py
    ├── stage_validator.py
    ├── state_manager.py
    └── year_executor.py

dbt/
├── models/
│   ├── sources.yml
│   ├── staging/
│   │   ├── schema.yml
│   │   └── stg_prior_enrollment_state.sql
│   └── intermediate/
│       ├── int_enrollment_events.sql
│       ├── int_proactive_voluntary_enrollment.sql
│       ├── int_voluntary_enrollment_decision.sql
│       └── schema.yml
└── tests/
    ├── assert_no_multi_cycle_enrollment.sql
    ├── assert_voluntary_enrollment_persists.sql
    ├── test_census_participants_not_reenrolled.sql
    ├── test_enrollment_population_split.sql
    ├── test_multi_year_state_history_retained.sql
    ├── analysis/test_enrollment_continuity.sql
    └── data_quality/test_enrollment_architecture.sql

tests/
├── fixtures/
│   ├── __init__.py
│   └── census_enrollment.py
├── conftest.py
├── integration/
│   ├── test_census_enrollment_persistence.py
│   └── test_year_dependency_validation.py
├── performance/
│   └── test_census_enrollment_performance.py
├── unit/
│   ├── scripts/test_check_fast_suite_runtime.py
│   ├── test_year_dependency_validator.py
│   └── orchestrator/
│       ├── test_cleanup_scoping.py
│       ├── test_enrollment_projection.py
│       ├── test_pipeline.py
│       ├── test_stage_validator.py
│       └── test_year_executor.py

scripts/
└── check_fast_suite_runtime.py

benchmark_baselines/
└── census_enrollment_projection_sql_baseline.json

docs/guides/
└── error_troubleshooting.md
```

**Structure Decision**: Add one focused orchestration projection module and one thin dbt staging boundary. All enrollment decision models use the same fact-derived projection, while tests are split into fast control-flow coverage, isolated end-to-end outcomes, dbt invariants, timed auditability, and opt-in 100K performance validation. The full file inventory is explicit so tasks and implementation scope cannot drift.

## Complexity Tracking

No constitution violations identified.
