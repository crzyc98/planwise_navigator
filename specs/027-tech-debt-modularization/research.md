# Research: Technical Debt Modularization

**Date**: 2026-01-27
**Feature**: 027-tech-debt-modularization

## E072/E073 Pattern Analysis

### Decision: Follow E072/E073 Patterns

**Rationale**: Both patterns are production-proven with zero circular imports, clean layered dependencies, and comprehensive backward compatibility.

**Alternatives Considered**:
1. **Inline refactoring** (rejected) - Would require updating all import sites simultaneously
2. **New package names** (rejected) - Would break backward compatibility
3. **Gradual migration** (selected) - E072/E073 pattern with wrapper modules

### E072 Pipeline Pattern (Verified)

**Original**: 2,478 lines → **Result**: 6 modules (200-555 lines each)

**Key Patterns**:
- Foundation layer with zero dependencies (`workflow.py`)
- Explicit `__all__` in `__init__.py`
- Relative imports within package
- TYPE_CHECKING guards for type hints
- No backward compat wrapper needed (integrated into PipelineOrchestrator)

**Strengths**:
- Clear separation of concerns
- Layered dependency structure prevents circular imports
- Enables isolated testing
- Zero import errors detected

### E073 Config Pattern (Verified)

**Original**: 1,366 lines → **Result**: 8 modules (41-720 lines each)

**Key Patterns**:
- Foundation layer (`paths.py`) with zero external dependencies
- Domain-grouped models (simulation, workforce, performance)
- Explicit backward compat wrapper (`config.py` at package level)
- TYPE_CHECKING pattern in `export.py` to avoid circular deps

**Strengths**:
- Pure foundation layer enables isolated testing
- Grouped related models together
- Clear dependency hierarchy
- 100% backward compatibility maintained

### Adopted Best Practices

1. **Foundation Layer First**: Create `data_models.py` with zero internal dependencies
2. **Explicit Re-exports**: Include `__all__` in every `__init__.py`
3. **Relative Imports**: Use `from .module import Class` within packages
4. **TYPE_CHECKING Guards**: Use for type hints that don't execute at runtime
5. **Backward Compat Wrappers**: Keep original files as thin re-export wrappers
6. **Module Size**: Target 200-500 lines, allow up to 750 for cohesion

### Line Limit Clarification

**Decision**: Cohesion-first approach - allow exceeding line limits by up to 50% when natural class boundaries require it.

**Rationale**: E073's `export.py` is 720 lines (exceeds 400 target) because splitting helper functions would reduce cohesion. This is acceptable.

**Applied Limits**:
- Target: 500 lines per module (orchestrator), 400 lines per module (API)
- Maximum: 750 lines (orchestrator), 600 lines (API)
- Justification required for exceeding target

## Dependency Analysis

### No Circular Import Risk

All target files have clear unidirectional dependencies:

```
performance_monitor.py: dataclasses → PerformanceMonitor → DuckDBPerformanceMonitor
resource_manager.py: dataclasses → monitors → facade
reports.py: dataclasses → formatters → auditors
simulation_service.py: helpers → SimulationService
```

### No Conflicting Package Names

Verified that none of these directories exist:
- `planalign_orchestrator/monitoring/` ✓ Safe to create
- `planalign_orchestrator/resources/` ✓ Safe to create
- `planalign_orchestrator/reports/` ✓ Safe to create
- `planalign_api/services/simulation/` ✓ Safe to create

## Conclusion

The E072/E073 patterns are well-suited for this refactoring. No additional research needed - proceed to implementation with the documented patterns.
