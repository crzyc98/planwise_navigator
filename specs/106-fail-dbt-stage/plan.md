# Implementation Plan: Fail Dbt Stage

**Branch**: `106-fail-dbt-stage` | **Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/106-fail-dbt-stage/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Fix the critical orchestration gap where a workflow stage can report an unsuccessful outcome while the outer simulation run proceeds as if the stage completed. The implementation will make the stage execution boundary fail fast on any non-successful or ambiguous stage outcome, preserve stage/year/error context in the raised failure, and add focused regression tests that prove failed required stages cannot be swallowed.

## Technical Context

**Language/Version**: Python >=3.11
**Primary Dependencies**: dbt Core/dbt DuckDB execution via the existing orchestrator, Pydantic configuration models, DuckDB-backed simulation state, pytest for tests
**Storage**: No schema or persisted data-model changes; existing DuckDB run outputs may be partially present for failed runs and must remain clearly associated with failed status
**Testing**: pytest fast unit regression around `PipelineOrchestrator._execute_stage_core`; optional integration smoke through the existing simulation CLI or orchestrator entrypoint
**Target Platform**: Local/workstation and batch execution environments supported by the PlanAlign orchestrator
**Project Type**: Python simulation engine with CLI/API entrypoints and dbt-backed transformation stages
**Performance Goals**: No measurable overhead beyond constant-time validation of a stage result after each workflow stage
**Constraints**: Preserve single-threaded default stability, existing observability/timing wrappers, event-sourced auditability, and clear failure context
**Scale/Scope**: Required workflow stages for multi-year simulations, including foundation, event-generation, state-accumulation, and validation stages

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Event Sourcing & Immutability**: PASS. The feature prevents invalid partial stage output from being treated as complete event lineage and does not mutate existing event records.
- **Modular Architecture**: PASS. The change is localized to the orchestration stage boundary and test coverage; no broad refactor or new cross-layer dependency is required.
- **Test-First Development**: PASS. A focused failing unit test must be added before the production fix, with optional smoke validation for the CLI/orchestrator path.
- **Enterprise Transparency**: PASS. The failure must preserve stage, year, and error summary for audit reconstruction and diagnosis.
- **Type-Safe Configuration**: PASS. No configuration schema changes are required.
- **Performance & Scalability**: PASS. The validation is constant-time and does not alter dbt execution, database access, or threading defaults.

## Project Structure

### Documentation (this feature)

```text
specs/106-fail-dbt-stage/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── pipeline_orchestrator.py        # Stage boundary must fail on unsuccessful outcomes
└── pipeline/
    └── year_executor.py            # Existing producer of stage outcome dictionaries

planalign_cli/
└── integration/                    # Existing CLI integration path for optional smoke checks

tests/
└── unit/
    └── orchestrator/
        └── test_pipeline_stage_failure.py  # New focused regression tests
```

**Structure Decision**: Use the existing single Python project layout. The production change belongs at the orchestrator stage execution boundary; the regression tests belong in the fast orchestrator unit test area.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations identified.
