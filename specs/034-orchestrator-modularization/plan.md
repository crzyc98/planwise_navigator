# Implementation Plan: Orchestrator Modularization Phase 2

**Branch**: `034-orchestrator-modularization` | **Date**: 2026-02-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/034-orchestrator-modularization/spec.md`

## Summary

Extract setup methods (~230 lines) and stage validation logic (~145 lines) from `pipeline_orchestrator.py` (1,218 lines) into two focused modules: `orchestrator_setup.py` and `pipeline/stage_validator.py`. This continues the E072 modularization pattern, reducing the orchestrator to ~650 lines while preserving the public API and ensuring zero behavioral regression.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Existing planalign_orchestrator modules (no new dependencies)
**Storage**: N/A (code refactoring only)
**Testing**: pytest (256+ existing tests, 87 fast tests)
**Target Platform**: Linux server / work laptops
**Project Type**: Single project (Python package)
**Performance Goals**: Identical behavior; no performance regression
**Constraints**: Public API must remain unchanged; all existing tests must pass
**Scale/Scope**: 1,218 lines → ~650 lines; 2 new modules (~400 lines total)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Event Sourcing & Immutability** | ✅ Pass | No changes to event handling; extraction is code organization only |
| **II. Modular Architecture** | ✅ Pass | Extraction directly aligns with constitution goal of ~600 line modules |
| **III. Test-First Development** | ✅ Pass | Existing 256 tests validate; no new features requiring new tests |
| **IV. Enterprise Transparency** | ✅ Pass | Logging/observability code moves to setup module unchanged |
| **V. Type-Safe Configuration** | ✅ Pass | No changes to Pydantic models or dbt patterns |
| **VI. Performance & Scalability** | ✅ Pass | No performance changes; same execution paths |

**Constitution Alignment**: This refactoring directly implements **Principle II (Modular Architecture)** by reducing `pipeline_orchestrator.py` from 1,218 lines (2x the 600-line guideline) to ~650 lines (within guideline).

## Project Structure

### Documentation (this feature)

```text
specs/034-orchestrator-modularization/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (minimal for refactoring)
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── __init__.py                    # Update exports (FR-008)
├── pipeline_orchestrator.py       # Reduce from 1,218 → ~650 lines
├── orchestrator_setup.py          # NEW: ~250 lines (FR-001)
└── pipeline/
    ├── __init__.py                # Update exports (FR-009)
    ├── stage_validator.py         # NEW: ~150 lines (FR-002)
    ├── workflow.py                # Unchanged
    ├── state_manager.py           # Unchanged
    ├── year_executor.py           # Unchanged
    ├── event_generation_executor.py # Unchanged
    ├── hooks.py                   # Unchanged
    └── data_cleanup.py            # Unchanged

tests/
├── unit/
│   └── orchestrator/              # Existing tests (must pass unchanged)
└── fixtures/                      # Existing fixtures
```

**Structure Decision**: Single Python package structure. New modules are placed alongside existing orchestrator code to maintain the established pattern from E072.

## Complexity Tracking

> No violations to justify. This refactoring reduces complexity by extracting cohesive concerns into focused modules.

## Extraction Analysis

### Setup Methods to Extract (orchestrator_setup.py)

| Method | Lines | Dependencies | Notes |
|--------|-------|--------------|-------|
| `_setup_adaptive_memory_manager()` | ~70 | AdaptiveMemoryManager, config, reports_dir | Returns manager or None |
| `_setup_model_parallelization()` | ~75 | ParallelExecutionEngine, ModelDependencyAnalyzer, ResourceManager | Returns tuple (engine, config, resource_manager) or (None, None, None) |
| `_setup_hazard_cache_manager()` | ~28 | HazardCacheManager, db_manager, dbt_runner | Returns manager or None |
| `_setup_performance_monitoring()` | ~24 | DuckDBPerformanceMonitor, db_manager, reports_dir | Returns monitor or None |
| `_create_resource_manager()` | ~30 | ResourceManager, config | Helper for parallelization |
| **Total** | ~227 | | |

### Validation Logic to Extract (pipeline/stage_validator.py)

| Method | Lines | Dependencies | Notes |
|--------|-------|--------------|-------|
| `_run_stage_validation()` | ~145 | db_manager, config, state_manager, verbose | Delegates per stage |
| - FOUNDATION validation | ~85 | db_manager.execute_with_retry | Row count checks |
| - EVENT_GENERATION validation | ~25 | db_manager.execute_with_retry | Hire/demand checks |
| - STATE_ACCUMULATION validation | ~10 | state_manager.verify_year_population | Delegation |
| **Total** | ~145 | | |

## Function Signatures (Design Contract)

### orchestrator_setup.py

```python
def setup_memory_manager(
    config: SimulationConfig,
    reports_dir: Path,
    verbose: bool = False
) -> Optional[AdaptiveMemoryManager]:
    """Setup adaptive memory management system. Returns None on failure."""

def setup_parallelization(
    config: SimulationConfig,
    dbt_runner: DbtRunner,
    verbose: bool = False
) -> tuple[Optional[ParallelExecutionEngine], Optional[Any], Optional[ResourceManager]]:
    """Setup model parallelization. Returns (engine, config, resource_manager) or (None, None, None)."""

def setup_hazard_cache(
    db_manager: DatabaseConnectionManager,
    dbt_runner: DbtRunner,
    verbose: bool = False
) -> Optional[HazardCacheManager]:
    """Setup hazard cache manager. Returns None on failure."""

def setup_performance_monitor(
    db_manager: DatabaseConnectionManager,
    reports_dir: Path,
    verbose: bool = False
) -> Optional[DuckDBPerformanceMonitor]:
    """Setup DuckDB performance monitoring. Returns None on failure."""
```

### pipeline/stage_validator.py

```python
class StageValidator:
    """Validates pipeline stage completion with diagnostic output."""

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        config: SimulationConfig,
        state_manager: StateManager,
        verbose: bool = False
    ):
        ...

    def validate_stage(
        self,
        stage: StageDefinition,
        year: int,
        fail_on_error: bool = False
    ) -> None:
        """Run validation for completed workflow stage. Raises PipelineStageError on critical failures."""
```

## Implementation Phases

### Phase 1: Setup Extraction (Lower Risk)

1. Create `orchestrator_setup.py` with function stubs
2. Copy `_setup_adaptive_memory_manager()` → `setup_memory_manager()`
3. Copy `_setup_model_parallelization()` → `setup_parallelization()` + `_create_resource_manager()`
4. Copy `_setup_hazard_cache_manager()` → `setup_hazard_cache()`
5. Copy `_setup_performance_monitoring()` → `setup_performance_monitor()`
6. Update `PipelineOrchestrator.__init__()` to call setup functions
7. Run `pytest -m fast` to verify
8. Run `planalign simulate 2025 --dry-run` to verify

### Phase 2: Validation Extraction

1. Create `pipeline/stage_validator.py` with `StageValidator` class
2. Copy `_run_stage_validation()` logic into `StageValidator.validate_stage()`
3. Extract helper methods for FOUNDATION, EVENT_GENERATION stages
4. Update `PipelineOrchestrator._execute_year_workflow()` to use `StageValidator`
5. Update `planalign_orchestrator/pipeline/__init__.py` exports
6. Run full test suite
7. Run `planalign simulate 2025-2027` for full integration test

### Phase 3: Cleanup & Documentation

1. Remove old private methods from `PipelineOrchestrator`
2. Update `planalign_orchestrator/__init__.py` exports (optional)
3. Verify line counts meet success criteria
4. Update `CLAUDE.md` if needed

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| API breakage | Constructor signature frozen; properties preserved |
| Test failures | Run tests after each extraction step; revert on failure |
| Behavior change | Same code paths; no logic modifications |
| Import cycles | Setup functions are standalone; no circular deps |

## Verification Commands

```bash
# After each phase
pytest -m fast                                    # Fast unit tests (~5s)
pytest tests/unit/orchestrator/                   # Orchestrator tests
planalign simulate 2025 --dry-run                 # Dry run validation

# Final verification
pytest                                            # Full suite (256+ tests)
planalign simulate 2025-2027                      # Full simulation
python -c "from planalign_orchestrator import create_orchestrator; print('OK')"
wc -l planalign_orchestrator/pipeline_orchestrator.py  # Should be ~650-700
wc -l planalign_orchestrator/orchestrator_setup.py     # Should be ~250
wc -l planalign_orchestrator/pipeline/stage_validator.py  # Should be ~150
```
