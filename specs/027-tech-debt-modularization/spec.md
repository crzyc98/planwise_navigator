# Feature Specification: Technical Debt Modularization

**Feature Branch**: `027-tech-debt-modularization`
**Created**: 2026-01-27
**Status**: Draft
**Input**: User description: "PlanAlign Engine Technical Debt Refactoring Roadmap - Split large monolithic files into focused modules following E072 and E073 patterns"

## Clarifications

### Session 2026-01-27

- Q: How strictly to follow line limits if natural class boundaries don't align? → A: Cohesion-first - Allow exceeding limits by up to 50% when natural class boundaries require it (e.g., 500 → 750 max, 400 → 600 max)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer Navigates Codebase Efficiently (Priority: P1)

As a developer working on PlanAlign Engine, I need large monolithic files split into focused modules so I can quickly locate and modify specific functionality without scrolling through 1,000+ line files.

**Why this priority**: Developer productivity is the primary driver for this refactoring. Large files slow down code comprehension, increase merge conflicts, and make debugging harder.

**Independent Test**: Can be fully tested by verifying that importing classes from the original module paths still works, all existing tests pass, and the largest file is under 500 lines.

**Acceptance Scenarios**:

1. **Given** a developer imports `PerformanceMonitor` from `planalign_orchestrator.performance_monitor`, **When** the refactoring is complete, **Then** the import continues to work via re-exports while the actual implementation lives in `planalign_orchestrator/monitoring/base.py`.

2. **Given** a developer needs to modify DuckDB monitoring logic, **When** they search for the relevant code, **Then** they find it in a focused 500-line `duckdb_monitor.py` file instead of a 1,110-line monolith.

---

### User Story 2 - Test Suite Validates Module Isolation (Priority: P2)

As a QA engineer, I need the refactored modules to have dedicated test files so I can run targeted tests during development without executing the entire test suite.

**Why this priority**: Faster test feedback loops improve development velocity and catch regressions earlier.

**Independent Test**: Can be verified by running `pytest tests/unit/monitoring/` and seeing only monitoring-related tests execute.

**Acceptance Scenarios**:

1. **Given** a developer modifies `memory_monitor.py`, **When** they run `pytest tests/unit/resources/test_memory_monitor.py`, **Then** only memory monitoring tests execute in under 5 seconds.

2. **Given** all refactoring is complete, **When** the full test suite runs, **Then** test coverage remains at 90%+ with no regressions.

---

### User Story 3 - CI Pipeline Maintains Build Stability (Priority: P3)

As a DevOps engineer, I need the refactoring to maintain backward-compatible imports so existing CI pipelines and downstream code continue working without modification.

**Why this priority**: Breaking changes would require coordinated updates across multiple systems, increasing rollout risk.

**Independent Test**: Can be verified by running `planalign health` and `planalign simulate 2025 --dry-run` successfully after each refactoring phase.

**Acceptance Scenarios**:

1. **Given** the original import `from planalign_orchestrator.resource_manager import ResourceManager`, **When** using the refactored codebase, **Then** the import succeeds and returns the same class.

2. **Given** the `planalign simulate 2025-2027` command, **When** executed against the refactored codebase, **Then** results are identical to pre-refactoring execution.

---

### Edge Cases

- What happens when a developer imports from both old and new paths in the same file? Both should work and return the same class instances.
- How does the system handle circular imports between newly split modules? Careful dependency ordering and lazy imports where needed.
- What happens if a module is partially refactored and tests run mid-phase? Tests should continue passing at all intermediate states.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain backward-compatible imports from original module paths via re-exports in `__init__.py` files
- **FR-002**: System MUST split `performance_monitor.py` (1,110 lines) into a `monitoring/` package with target 500 lines per file (max 750 when cohesion requires)
- **FR-003**: System MUST split `resource_manager.py` (1,067 lines) into a `resources/` package with target 500 lines per file (max 750 when cohesion requires)
- **FR-004**: System MUST split `reports.py` (881 lines) into a `reports/` package with target 400 lines per file (max 600 when cohesion requires)
- **FR-005**: System MUST split `simulation_service.py` (946 lines) into a `simulation/` package with target 400 lines per file (max 600 when cohesion requires)
- **FR-006**: System MUST preserve all existing test coverage (90%+) after refactoring
- **FR-007**: System MUST pass all existing pytest markers (`-m fast`, `-m integration`) without modification
- **FR-008**: Original module files MUST include deprecation comments directing developers to new locations
- **FR-009**: Each new module MUST have corresponding unit test files in `tests/unit/<package>/`

### Key Entities

- **Module Package**: A Python package (directory with `__init__.py`) containing related focused modules
- **Re-export**: An import in `__init__.py` that makes classes available from the package level
- **Deprecation Comment**: A code comment indicating the original file is maintained for backward compatibility only

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Largest Python file in `planalign_orchestrator/` is under 750 lines with most under 500 (currently 1,110)
- **SC-002**: Largest Python file in `planalign_api/services/` is under 600 lines with most under 400 (currently 946)
- **SC-003**: Test coverage remains at 90%+ after all refactoring phases
- **SC-004**: All 256 existing tests pass without modification
- **SC-005**: `planalign health` command succeeds on refactored codebase
- **SC-006**: `planalign simulate 2025-2027` produces identical results pre/post refactoring
- **SC-007**: Zero import errors when using original module paths (100% backward compatibility)
- **SC-008**: Each new package has at least one dedicated test file

## Scope & Boundaries

### In Scope

- Split `performance_monitor.py` into `monitoring/` package (4 modules)
- Split `resource_manager.py` into `resources/` package (6 modules)
- Split `reports.py` into `reports/` package (4 modules)
- Split `simulation_service.py` into `simulation/` package (5 modules)
- Create corresponding test files for new modules
- Update imports in any files that directly reference internal implementation

### Out of Scope

- SQL model cleanup (originally proposed deletion of `int_workforce_snapshot_optimized.sql` is **NOT safe** - it is actively referenced in `simulation_service.py:237`)
- Any changes to dbt models or SQL transformations
- Performance optimizations beyond modularization
- API changes or new features
- Documentation updates to `CLAUDE.md` (optional follow-up)

## Assumptions

- The existing test suite at 90%+ coverage adequately validates functionality
- Re-exports in `__init__.py` provide sufficient backward compatibility
- No external systems directly import from internal module paths (only package-level imports)
- The `planalign_orchestrator/pipeline/` package (E072) serves as a proven pattern for modularization
- Python 3.11 import system handles re-exports without circular dependency issues

## Dependencies

- E072 (Pipeline Modularization) - Provides proven pattern for splitting monoliths
- E073 (Config Module Refactoring) - Provides proven pattern for package structure
- Existing test infrastructure (E075) - Required for validation
- pytest and coverage tools - Required for regression testing

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Circular imports after split | Medium | High | Careful dependency ordering; lazy imports where needed |
| Broken external integrations | Low | Medium | Comprehensive backward compatibility via re-exports |
| Test coverage drop | Low | Medium | Run coverage after each phase; do not proceed if below 90% |
| Merge conflicts with concurrent work | Medium | Low | Complete one package at a time; merge to main frequently |
