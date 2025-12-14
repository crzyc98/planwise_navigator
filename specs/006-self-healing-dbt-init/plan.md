# Implementation Plan: Self-Healing dbt Initialization

**Branch**: `006-self-healing-dbt-init` | **Date**: 2025-12-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-self-healing-dbt-init/spec.md`

## Summary

Implement automatic database initialization that detects missing tables before simulation and triggers `dbt seed` + foundation model builds to create them. This eliminates "table does not exist" errors for first-time simulations in new workspaces while providing clear progress feedback and graceful error recovery.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, DuckDB 1.0.0, Pydantic v2
**Storage**: DuckDB (standardized location: `dbt/simulation.duckdb`)
**Testing**: pytest with existing fixture library (`tests/fixtures/`)
**Target Platform**: Linux/macOS workstations (on-premises deployment)
**Project Type**: Single project (monorepo with modular packages)
**Performance Goals**: Initialization completes within 60 seconds (per SC-003)
**Constraints**: Single-threaded initialization for stability; must use existing `get_database_path()` API
**Scale/Scope**: Supports workspaces with 100K+ employees, but initialization creates empty structure first

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Event Sourcing & Immutability | ✅ PASS | Initialization creates empty tables; does not modify existing events |
| II. Modular Architecture | ✅ PASS | New `TableExistenceChecker` class with single responsibility; integrates via hooks |
| III. Test-First Development | ✅ PASS | Tests designed first (see tasks.md); fixture library provides test databases |
| IV. Enterprise Transparency | ✅ PASS | Structured logging with step timing per NFR-001/NFR-002 |
| V. Type-Safe Configuration | ✅ PASS | Required tables defined via Pydantic model; uses `{{ ref() }}` for dbt |
| VI. Performance & Scalability | ✅ PASS | 60s timeout meets constitution; single-threaded default maintained |

**Gate Status**: PASS - All principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/006-self-healing-dbt-init/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal API contracts)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── init_database.py              # EXISTING: DatabaseInitializer class (extend)
├── self_healing/                 # NEW: Self-healing initialization module
│   ├── __init__.py
│   ├── table_checker.py          # TableExistenceChecker class
│   ├── initialization_state.py   # InitializationState enum + tracking
│   └── auto_initializer.py       # AutoInitializer orchestration
├── pipeline/
│   └── hooks.py                  # MODIFY: Add pre-simulation hook point
├── factory.py                    # MODIFY: Integrate auto-initialization
└── exceptions.py                 # MODIFY: Add InitializationError

tests/
├── fixtures/
│   └── database.py               # MODIFY: Add empty_database fixture
└── unit/orchestrator/
    └── test_self_healing.py      # NEW: Unit tests for self-healing
```

**Structure Decision**: Extend existing monorepo structure with new `self_healing/` subpackage under `planalign_orchestrator/`. This follows the modular architecture pattern established in E072.

## Complexity Tracking

> No constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
