# Implementation Plan: Temporal State Accumulator Contract

**Branch**: `007-state-accumulator-contract` | **Date**: 2025-12-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-state-accumulator-contract/spec.md`

## Summary

Formalize the implicit temporal dependency pattern in state accumulator models (Year N depends on Year N-1 data) with explicit runtime validation. This prevents silent data corruption from out-of-order year execution by failing fast with clear error messages. Implementation follows existing registry patterns (`EventRegistry`, `RegistryManager`) with a new `StateAccumulatorRegistry` that tracks accumulator models and validates year dependencies before STATE_ACCUMULATION stage execution.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Pydantic v2 (type-safe contracts), existing `planalign_orchestrator` modules
**Storage**: DuckDB 1.0.0 (existing `dbt/simulation.duckdb`)
**Testing**: pytest with `tests/fixtures/` (fast tests <10s, integration tests)
**Target Platform**: Linux server (on-premises deployment)
**Project Type**: Single Python package (`planalign_orchestrator`)
**Performance Goals**: Validation overhead <100ms per year (negligible vs. dbt model execution)
**Constraints**: Must not change existing simulation results; must integrate with existing checkpoint system
**Scale/Scope**: 2 initial accumulator models (`int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator`), extensible to future accumulators

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Event Sourcing & Immutability | ✅ Pass | Feature validates existing event-sourced state accumulators; does not modify event store |
| II. Modular Architecture | ✅ Pass | New module `state_accumulator_registry.py` follows existing registry patterns (~200 lines); single responsibility |
| III. Test-First Development | ✅ Pass | Plan includes unit tests (fast suite) and integration tests; coverage targets 90%+ |
| IV. Enterprise Transparency | ✅ Pass | Validation errors include year, required dependencies, resolution hints |
| V. Type-Safe Configuration | ✅ Pass | Contract uses Pydantic v2 models with explicit validation |
| VI. Performance & Scalability | ✅ Pass | Validation is O(n) where n = number of accumulators (currently 2); <100ms overhead |

**Gate Status**: ✅ PASSED - No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/007-state-accumulator-contract/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── state_accumulator/              # New module for state accumulator contracts
│   ├── __init__.py                # Public API exports
│   ├── contract.py                # StateAccumulatorContract Pydantic model
│   ├── registry.py                # StateAccumulatorRegistry (follows EventRegistry pattern)
│   └── validator.py               # YearDependencyValidator for runtime checks
├── pipeline/
│   └── year_executor.py           # Modified: Add pre-stage validation hook
├── registries.py                  # Reference: Existing registry patterns
└── generators/
    └── registry.py                # Reference: EventRegistry pattern

dbt/
└── models/
    └── intermediate/
        ├── int_enrollment_state_accumulator.sql    # Add metadata comment for registry
        └── int_deferral_rate_state_accumulator.sql # Add metadata comment for registry

tests/
├── unit/
│   └── test_state_accumulator_registry.py         # Fast unit tests
├── integration/
│   └── test_year_dependency_validation.py         # Integration tests
└── fixtures/
    └── state_accumulator.py                       # Test fixtures for accumulators
```

**Structure Decision**: Single Python package extension following existing `planalign_orchestrator` conventions. New `state_accumulator/` submodule mirrors `generators/` and `pipeline/` organization for consistency.

## Complexity Tracking

No constitution violations to justify.

## Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PipelineOrchestrator                              │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │              execute_multi_year_simulation()                     ││
│  │  for year in range(start, end+1):                               ││
│  │      _execute_year_workflow(year)                               ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    YearExecutor                                  ││
│  │  execute_workflow_stage(stage, year):                           ││
│  │    if stage == STATE_ACCUMULATION:                              ││
│  │        validator.validate_year_dependencies(year)  ◄── NEW      ││
│  │    # ... existing stage execution                               ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │              YearDependencyValidator (NEW)                       ││
│  │  - Queries StateAccumulatorRegistry for registered models       ││
│  │  - Checks database for prior year data existence                ││
│  │  - Raises YearDependencyError if validation fails               ││
│  └─────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │             StateAccumulatorRegistry (NEW)                       ││
│  │  - Tracks registered accumulator models                          ││
│  │  - Provides contract metadata (table name, dependencies)        ││
│  │  - Follows EventRegistry singleton pattern                       ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Pipeline starts year N execution
2. YearExecutor receives STATE_ACCUMULATION stage
3. YearDependencyValidator.validate_year_dependencies(N) called
   a. If N == start_year: Skip validation (no prior dependency)
   b. Query StateAccumulatorRegistry for all registered accumulators
   c. For each accumulator:
      - Query database: SELECT COUNT(*) WHERE simulation_year = N-1
      - If count == 0: Collect missing dependency
   d. If any missing: Raise YearDependencyError with full context
4. If validation passes: Execute STATE_ACCUMULATION models normally
```

## Key Design Decisions

### D1: Follow EventRegistry Pattern
**Decision**: Model `StateAccumulatorRegistry` after the existing `EventRegistry` (singleton, class methods, decorator registration).
**Rationale**: Consistency with existing codebase; developers already understand this pattern; reduces cognitive load.

### D2: Validation in YearExecutor (Not PipelineOrchestrator)
**Decision**: Add validation hook in `YearExecutor.execute_workflow_stage()` rather than `PipelineOrchestrator`.
**Rationale**: YearExecutor is the appropriate abstraction level for per-year, per-stage operations; keeps PipelineOrchestrator focused on multi-year orchestration.

### D3: Database Query for State Validation
**Decision**: Check for prior year data existence by querying `SELECT COUNT(*) FROM {table} WHERE simulation_year = {N-1}`.
**Rationale**: Simple, direct, and handles both SQL and Polars execution modes; doesn't require additional metadata tables.

### D4: Pydantic v2 Contract Model
**Decision**: Use Pydantic `BaseModel` for `StateAccumulatorContract` with explicit field validation.
**Rationale**: Aligns with Constitution Principle V (Type-Safe Configuration); provides validation at registration time.

### D5: Registration via Configuration (Not Decorator)
**Decision**: Register accumulators programmatically in `__init__.py` rather than via decorator on SQL files.
**Rationale**: SQL files can't use Python decorators; explicit registration in Python is clearer and testable.

## Integration Points

### Existing Components Modified

1. **`planalign_orchestrator/pipeline/year_executor.py`**
   - Add: `YearDependencyValidator` import
   - Add: Validation call before STATE_ACCUMULATION stage execution
   - Error handling: Catch `YearDependencyError`, re-raise with context

2. **`planalign_orchestrator/pipeline/state_manager.py`**
   - Add: Optional method to validate checkpoint dependency chain
   - Used by: Checkpoint recovery flow

### New Components

1. **`planalign_orchestrator/state_accumulator/__init__.py`**
   - Exports: `StateAccumulatorContract`, `StateAccumulatorRegistry`, `YearDependencyValidator`
   - Registers: `int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator`

2. **`planalign_orchestrator/state_accumulator/contract.py`**
   - Defines: `StateAccumulatorContract` Pydantic model
   - Fields: `model_name`, `table_name`, `prior_year_columns`, `start_year_source`

3. **`planalign_orchestrator/state_accumulator/registry.py`**
   - Defines: `StateAccumulatorRegistry` singleton class
   - Methods: `register()`, `get()`, `list_all()`, `get_registered_tables()`

4. **`planalign_orchestrator/state_accumulator/validator.py`**
   - Defines: `YearDependencyValidator` class
   - Methods: `validate_year_dependencies(year)`, `get_missing_years(year)`
   - Raises: `YearDependencyError` on validation failure

5. **`planalign_orchestrator/exceptions.py`** (modified)
   - Add: `YearDependencyError` exception class
