# Implementation Plan: Unified Database Path Resolver

**Branch**: `005-database-path-resolver` | **Date**: 2025-12-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-database-path-resolver/spec.md`

## Summary

Unify duplicated database path resolution logic across three API services (AnalyticsService, ComparisonService, SimulationService) into a single `DatabasePathResolver` service class. The resolver implements the existing fallback chain (scenario-specific → workspace → project default) with added security (path traversal prevention), configurability (project_root override, multi-tenant isolation mode), and testability (stateless design, dependency injection).

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Pydantic v2 (validation), FastAPI (dependency injection context), pathlib (path handling)
**Storage**: DuckDB databases at multiple levels (scenario, workspace, project)
**Testing**: pytest with fixtures from `tests/fixtures/`
**Target Platform**: Linux server, Windows workstations (cross-platform path handling)
**Project Type**: Backend API service
**Performance Goals**: Path resolution in <1ms, unit tests in <100ms
**Constraints**: Stateless (thread-safe), no filesystem I/O for mocking in tests
**Scale/Scope**: 3 services to refactor, 1 new service class, ~150 lines of code

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Event Sourcing & Immutability** | ✅ N/A | Feature is infrastructure; does not modify event store |
| **II. Modular Architecture** | ✅ Pass | Single-responsibility resolver class; eliminates duplication across 3 services |
| **III. Test-First Development** | ✅ Pass | SC-003 requires <100ms unit tests; SC-006 requires 95%+ coverage |
| **IV. Enterprise Transparency** | ✅ Pass | FR-005 requires warning logs; FR-006 returns source metadata |
| **V. Type-Safe Configuration** | ✅ Pass | ResolvedDatabasePath uses Pydantic model; isolation_mode is typed enum |
| **VI. Performance & Scalability** | ✅ Pass | Stateless design (FR-010); no memory accumulation |

**Gate Result**: PASS - No violations. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/005-database-path-resolver/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal Python interface)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_api/
├── services/
│   ├── database_path_resolver.py   # NEW: DatabasePathResolver class
│   ├── analytics_service.py        # MODIFY: inject resolver
│   ├── comparison_service.py       # MODIFY: inject resolver
│   └── simulation_service.py       # MODIFY: inject resolver
└── models/
    └── database.py                 # NEW: ResolvedDatabasePath model (or in resolver file)

tests/
├── unit/
│   └── test_database_path_resolver.py  # NEW: unit tests with mocks
└── integration/
    └── test_service_integration.py     # MODIFY: verify backward compatibility
```

**Structure Decision**: Single project structure. New resolver lives in `planalign_api/services/` alongside existing services. Pydantic model can be co-located in the resolver module or split to `models/` based on reuse patterns.

## Complexity Tracking

> No Constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
