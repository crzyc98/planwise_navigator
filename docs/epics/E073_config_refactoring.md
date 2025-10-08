# Epic E073: Config Module Refactoring

**Status**: 🟢 READY TO IMPLEMENT
**Priority**: MEDIUM (Quality of Life)
**Estimated Time**: 2-3 hours
**Created**: 2025-10-07

---

## Executive Summary

Refactor the monolithic 1,208-line `navigator_orchestrator/config.py` into a modular package structure with focused modules for compensation, enrollment, performance optimization, and configuration loading. This improves developer experience by making settings easy to find, modify, and maintain while preserving complete backward compatibility.

---

## Problem Statement

### Current State
- **Single massive file**: 1,208 lines containing 30+ Pydantic models
- **Poor navigability**: Settings scattered across 1000+ lines make specific configuration hard to find
- **Unclear boundaries**: Compensation, enrollment, performance, and safety settings all mixed together
- **Maintenance burden**: Adding new settings requires navigating entire file
- **Code review friction**: Changes to any setting require reviewing massive diff

### Pain Points
1. **Developer Friction**: "Where do I change auto-enrollment settings?" → scroll through 1200 lines
2. **Poor Discoverability**: Related settings (enrollment + opt-out rates) are hundreds of lines apart
3. **Import Bloat**: Importing any config model loads entire 1208-line module
4. **Testing Complexity**: Testing specific configuration sections requires understanding entire file structure

### Business Impact
- **Slows feature development**: 5-10 minutes per configuration change to find correct location
- **Increases error risk**: Easy to modify wrong settings when everything is in one place
- **Hampers onboarding**: New developers struggle to understand configuration organization

---

## Goals

### Primary Objectives
1. **Split config.py into focused modules** with clear single responsibilities
2. **Maintain 100% backward compatibility** - no changes to public API
3. **Improve discoverability** - settings grouped by functional domain
4. **Enable selective imports** - import only what you need
5. **Preserve all functionality** - loaders, validators, converters work identically

### Success Metrics
- ✅ All existing imports continue to work unchanged
- ✅ Each module under 300 lines (80% reduction in file size)
- ✅ All tests pass without modification
- ✅ Developer can find any setting in <30 seconds (vs 2-3 minutes currently)
- ✅ Code review diffs focused on single domain (compensation, enrollment, etc.)

### Non-Goals
- ❌ Change configuration file format (YAML structure unchanged)
- ❌ Modify dbt variable mapping logic
- ❌ Add new configuration features (pure refactoring)
- ❌ Change validation behavior (preserve all existing checks)

---

## Technical Approach

### New Package Structure

```
navigator_orchestrator/
├─ config/                          # New package (replaces config.py)
│  ├─ __init__.py                  # Public API re-exports (backward compat)
│  ├─ base.py                      # Core settings models (240 lines)
│  ├─ compensation.py              # Compensation & workforce (180 lines)
│  ├─ enrollment.py                # Enrollment & eligibility (240 lines)
│  ├─ performance.py               # Threading, optimization, Polars (320 lines)
│  ├─ safety.py                    # Production safety & backup (120 lines)
│  └─ loader.py                    # YAML loading, validation, dbt vars (280 lines)
```

### Module Boundaries

#### **base.py** (Core Settings)
- `SimulationSettings` - start_year, end_year, random_seed, target_growth_rate
- `SimulationConfig` - Top-level config model
- `OrchestrationConfig` - Complete orchestration config
- `get_database_path()` - Database path utility

#### **compensation.py** (Compensation & Workforce)
- `CompensationSettings` - COLA, merit budget
- `PromotionCompensationSettings` - Promotion increases, distribution, caps
- `WorkforceSettings` - Termination rates, hiring parameters

#### **enrollment.py** (Enrollment & Eligibility)
- `EnrollmentSettings` - Auto-enrollment, proactive enrollment
- `AutoEnrollmentSettings` - Window, deferral rates, opt-out
- `OptOutRatesSettings` - By age and income
- `ProactiveEnrollmentSettings` - Timing windows, probabilities
- `EligibilitySettings` - Waiting periods
- `PlanEligibilitySettings` - Minimum age
- `EmployerMatchSettings` - Match formulas, eligibility

#### **performance.py** (Performance Optimization)
- `OptimizationSettings` - Level, workers, batch size, memory limits
- `ThreadingSettings` - dbt threading configuration
- `E068CThreadingSettings` - E068C parallelization
- `EventGenerationSettings` - SQL vs Polars mode
- `PolarsEventSettings` - Polars-specific configuration
- `AdaptiveMemorySettings` - Memory management
- `ResourceManagerSettings` - CPU monitoring, resource cleanup
- `ModelParallelizationSettings` - Model-level parallelization

#### **safety.py** (Production Safety)
- `ProductionSafetySettings` - Backup, logging, safety checks
- `validate_production_configuration()` - Production validation

#### **loader.py** (Configuration Loading)
- `load_simulation_config()` - YAML loading with env overrides
- `load_orchestration_config()` - Orchestration config loading
- `to_dbt_vars()` - Convert config to dbt variables (470 lines)
- `create_example_orchestration_config()` - Example YAML generator
- Helper functions: `_lower_keys()`, `_apply_env_overrides()`

### Backward Compatibility Strategy

**Public API Preservation** (in `config/__init__.py`):
```python
# Re-export all public symbols for backward compatibility
from .base import (
    SimulationSettings,
    SimulationConfig,
    OrchestrationConfig,
    get_database_path,
)
from .compensation import (
    CompensationSettings,
    PromotionCompensationSettings,
    WorkforceSettings,
)
from .enrollment import (
    EnrollmentSettings,
    AutoEnrollmentSettings,
    OptOutRatesSettings,
    OptOutRatesByAge,
    OptOutRatesByIncome,
    ProactiveEnrollmentSettings,
    EnrollmentTimingSettings,
    EligibilitySettings,
    PlanEligibilitySettings,
    EmployerMatchSettings,
    EmployerMatchEligibilitySettings,
)
from .performance import (
    OptimizationSettings,
    ThreadingSettings,
    E068CThreadingSettings,
    EventGenerationSettings,
    PolarsEventSettings,
    AdaptiveMemorySettings,
    ResourceManagerSettings,
    ModelParallelizationSettings,
    OrchestratorSettings,
)
from .safety import (
    ProductionSafetySettings,
    validate_production_configuration,
)
from .loader import (
    load_simulation_config,
    load_orchestration_config,
    to_dbt_vars,
    get_backup_configuration,
    create_example_orchestration_config,
)

__all__ = [
    # Base
    "SimulationSettings",
    "SimulationConfig",
    "OrchestrationConfig",
    "get_database_path",
    # Compensation
    "CompensationSettings",
    "PromotionCompensationSettings",
    "WorkforceSettings",
    # Enrollment
    "EnrollmentSettings",
    "AutoEnrollmentSettings",
    "OptOutRatesSettings",
    "OptOutRatesByAge",
    "OptOutRatesByIncome",
    "ProactiveEnrollmentSettings",
    "EnrollmentTimingSettings",
    "EligibilitySettings",
    "PlanEligibilitySettings",
    "EmployerMatchSettings",
    "EmployerMatchEligibilitySettings",
    # Performance
    "OptimizationSettings",
    "ThreadingSettings",
    "E068CThreadingSettings",
    "EventGenerationSettings",
    "PolarsEventSettings",
    "AdaptiveMemorySettings",
    "ResourceManagerSettings",
    "ModelParallelizationSettings",
    "OrchestratorSettings",
    # Safety
    "ProductionSafetySettings",
    "validate_production_configuration",
    # Loader
    "load_simulation_config",
    "load_orchestration_config",
    "to_dbt_vars",
    "get_backup_configuration",
    "create_example_orchestration_config",
]
```

**Import Compatibility**:
```python
# All existing imports continue to work
from navigator_orchestrator.config import SimulationConfig  # ✅ Works
from navigator_orchestrator.config import load_simulation_config  # ✅ Works
from navigator_orchestrator.config import to_dbt_vars  # ✅ Works
```

---

## Implementation Plan

### Story Breakdown

#### **S073-01: Create Config Package Structure** (30 minutes, 2 points)
**Goal**: Set up the new config package with proper Python package structure.

**Tasks**:
1. Create `navigator_orchestrator/config/` directory
2. Create `__init__.py` with backward-compatible re-exports
3. Create empty module files: `base.py`, `compensation.py`, `enrollment.py`, `performance.py`, `safety.py`, `loader.py`
4. Add package docstring explaining module organization

**Acceptance Criteria**:
- ✅ `config/` directory exists with all module files
- ✅ `__init__.py` contains complete public API re-exports
- ✅ Package can be imported: `from navigator_orchestrator.config import SimulationConfig`

---

#### **S073-02: Extract Base Settings Module** (30 minutes, 2 points)
**Goal**: Move core simulation settings to `base.py` with minimal dependencies.

**Extract to base.py**:
- `get_database_path()` function (lines 21-39)
- `SimulationSettings` (lines 42-46)
- Helper for backward compatibility references

**Tasks**:
1. Copy core models to `base.py`
2. Add imports: `pathlib.Path`, `os`, `pydantic`
3. Add module docstring: "Core simulation settings and database utilities"
4. Update `__init__.py` to re-export base models

**Acceptance Criteria**:
- ✅ `base.py` imports successfully with no circular dependencies
- ✅ All base models function identically
- ✅ `get_database_path()` works in new location

---

#### **S073-03: Extract Compensation & Workforce Module** (30 minutes, 2 points)
**Goal**: Isolate compensation and workforce configuration in `compensation.py`.

**Extract to compensation.py**:
- `PromotionCompensationSettings` (lines 49-63)
- `CompensationSettings` (lines 66-69)
- `WorkforceSettings` (lines 72-74)

**Tasks**:
1. Copy compensation models to `compensation.py`
2. Add imports from `pydantic`
3. Add module docstring: "Compensation and workforce modeling configuration"
4. Update `__init__.py` to re-export compensation models

**Acceptance Criteria**:
- ✅ All compensation settings models work in new location
- ✅ Promotion compensation validation preserved
- ✅ Backward-compatible imports function correctly

---

#### **S073-04: Extract Enrollment & Eligibility Module** (45 minutes, 3 points)
**Goal**: Consolidate all enrollment-related configuration in `enrollment.py`.

**Extract to enrollment.py**:
- `OptOutRatesByAge`, `OptOutRatesByIncome`, `OptOutRatesSettings` (lines 77-94)
- `AutoEnrollmentSettings` (lines 96-103)
- `ProactiveEnrollmentSettings` (lines 106-114)
- `EnrollmentTimingSettings` (lines 117-118)
- `EnrollmentSettings` (lines 121-124)
- `EligibilitySettings`, `PlanEligibilitySettings` (lines 127-133)
- `EmployerMatchEligibilitySettings`, `EmployerMatchSettings` (lines 135-150)

**Tasks**:
1. Copy all enrollment models to `enrollment.py`
2. Group related models together (auto-enrollment, proactive, eligibility)
3. Add section comments for clarity
4. Update `__init__.py` to re-export enrollment models

**Acceptance Criteria**:
- ✅ All enrollment settings models work in new location
- ✅ Opt-out rate calculations preserved
- ✅ Employer match eligibility logic unchanged

---

#### **S073-05: Extract Performance Optimization Module** (45 minutes, 3 points)
**Goal**: Consolidate all performance, threading, and optimization settings in `performance.py`.

**Extract to performance.py**:
- `AdaptiveMemoryThresholds`, `AdaptiveBatchSizes`, `AdaptiveMemorySettings` (lines 153-191)
- `CPUMonitoringThresholds`, `CPUMonitoringSettings` (lines 193-207)
- `ResourceManagerSettings` (lines 209-238)
- `ModelParallelizationSettings` (lines 240-257)
- `ThreadingSettings` (lines 259-290)
- `OrchestratorSettings` (lines 292-294)
- `PolarsEventSettings` (lines 297-310)
- `EventGenerationSettings` (lines 313-326)
- `E068CThreadingSettings` (lines 328-356)
- `OptimizationSettings` (lines 358-373)

**Tasks**:
1. Copy all performance models to `performance.py`
2. Group by category: threading, memory, CPU, Polars, optimization
3. Preserve all validation methods
4. Update `__init__.py` to re-export performance models

**Acceptance Criteria**:
- ✅ All threading validation methods work correctly
- ✅ E068C threading configuration preserved
- ✅ Polars settings function identically
- ✅ Adaptive memory management unchanged

---

#### **S073-06: Extract Production Safety Module** (30 minutes, 2 points)
**Goal**: Move production safety and backup configuration to `safety.py`.

**Extract to safety.py**:
- `ProductionSafetySettings` (lines 375-410)
- `validate_production_configuration()` (lines 979-1054)
- `get_backup_configuration()` (lines 1106-1126)

**Tasks**:
1. Copy production safety models and functions to `safety.py`
2. Add imports: `pathlib.Path`, `duckdb`, `shutil`
3. Handle circular import with `BackupConfiguration` (use TYPE_CHECKING)
4. Update `__init__.py` to re-export safety functions

**Acceptance Criteria**:
- ✅ Production validation works identically
- ✅ Backup configuration extraction unchanged
- ✅ No circular import issues

---

#### **S073-07: Extract Configuration Loader Module** (45 minutes, 3 points)
**Goal**: Move YAML loading, validation, and dbt var mapping to `loader.py`.

**Extract to loader.py**:
- `SimulationConfig` (lines 445-554) - Top-level config with helper methods
- `OrchestrationConfig` (lines 413-443) - Complete orchestration config
- `_lower_keys()`, `_apply_env_overrides()` (lines 556-587)
- `load_simulation_config()` (lines 589-621)
- `to_dbt_vars()` (lines 623-976) - **LARGE function, keep together**
- `load_orchestration_config()` (lines 1056-1103)
- `create_example_orchestration_config()` (lines 1129-1208)

**Tasks**:
1. Copy loader functions and top-level config models to `loader.py`
2. Import all setting models from other config modules
3. Preserve complete dbt vars mapping logic (470 lines)
4. Add comprehensive module docstring explaining YAML → config → dbt vars flow
5. Update `__init__.py` to re-export loader functions

**Acceptance Criteria**:
- ✅ YAML loading works identically with env overrides
- ✅ `to_dbt_vars()` produces identical output (critical!)
- ✅ dbt variable mapping unchanged (test with actual simulation)
- ✅ Orchestration config loading preserved

---

#### **S073-08: Update Imports Throughout Codebase** (30 minutes, 2 points)
**Goal**: Update all imports to use new config package structure (optional - backward compat preserves this).

**Strategy**: Since we're maintaining backward compatibility through `__init__.py` re-exports, this story is **OPTIONAL**. However, we can selectively optimize imports in key modules.

**Optional Import Optimizations**:
```python
# Before (loads entire 1208-line module)
from navigator_orchestrator.config import PromotionCompensationSettings

# After (loads only compensation module ~180 lines)
from navigator_orchestrator.config.compensation import PromotionCompensationSettings
```

**High-value files to optimize** (optional):
1. `pipeline.py` - Use selective imports for performance settings
2. `dbt_runner.py` - Import only loader functions
3. `cli.py` - Import only what's needed for CLI

**Tasks**:
1. Scan codebase for `from navigator_orchestrator.config import` statements
2. Optionally update high-traffic modules to use selective imports
3. Leave backward-compatible imports in place for low-priority modules

**Acceptance Criteria**:
- ✅ All existing imports continue to work (backward compat)
- ✅ Optional selective imports reduce module loading overhead
- ✅ No import errors in any module

---

#### **S073-09: Validation & Testing** (30 minutes, 2 points)
**Goal**: Verify complete backward compatibility and correctness.

**Test Strategy**:
1. **Unit Tests**: Ensure all existing config tests pass without modification
2. **Integration Tests**: Run full simulation to verify dbt vars mapping
3. **Import Tests**: Test all public API imports from `config` package
4. **Validation Tests**: Verify all validation methods work identically

**Test Cases**:
```python
# Test backward-compatible imports
from navigator_orchestrator.config import SimulationConfig
from navigator_orchestrator.config import load_simulation_config
from navigator_orchestrator.config import to_dbt_vars

# Test selective imports (new capability)
from navigator_orchestrator.config.compensation import CompensationSettings
from navigator_orchestrator.config.enrollment import AutoEnrollmentSettings
from navigator_orchestrator.config.performance import OptimizationSettings

# Test dbt vars mapping (critical!)
config = load_simulation_config('config/simulation_config.yaml')
dbt_vars = to_dbt_vars(config)
assert 'start_year' in dbt_vars
assert 'cola_rate' in dbt_vars
assert 'employer_match' in dbt_vars

# Test validation methods
config.validate_threading_configuration()
config.require_identifiers()
```

**Tasks**:
1. Run existing test suite: `pytest tests/test_config.py -v`
2. Run full simulation: `python -m navigator_orchestrator run --years 2025 2026`
3. Compare dbt vars output before/after refactoring
4. Test all public API imports
5. Verify no performance regression

**Acceptance Criteria**:
- ✅ All existing tests pass without modification
- ✅ Full simulation completes successfully
- ✅ dbt vars mapping produces identical output
- ✅ All imports work (backward-compatible and selective)
- ✅ No performance regression (<5% import time increase acceptable)

---

## Dependencies

### Internal Dependencies
- None (pure refactoring, no feature dependencies)

### External Dependencies
- `pydantic` v2.7.4 (existing)
- `pyyaml` (existing)

### Breaking Changes
- **None** - Complete backward compatibility maintained through `__init__.py` re-exports

---

## Risks & Mitigation

### Risk: Breaking existing imports
**Likelihood**: LOW
**Impact**: HIGH
**Mitigation**: Comprehensive `__init__.py` re-exports preserve all existing imports. Test all imports before merging.

### Risk: Circular import issues
**Likelihood**: MEDIUM
**Impact**: MEDIUM
**Mitigation**:
- Use `TYPE_CHECKING` for type hints that cause circular imports
- Keep `SimulationConfig` and `OrchestrationConfig` in `loader.py` (they depend on all other models)
- Test imports in isolation for each module

### Risk: dbt vars mapping broken
**Likelihood**: LOW
**Impact**: CRITICAL
**Mitigation**:
- Keep `to_dbt_vars()` function completely unchanged (copy-paste)
- Run integration test comparing dbt vars output before/after
- Test full simulation to verify correct behavior

### Risk: Performance regression
**Likelihood**: LOW
**Impact**: LOW
**Mitigation**:
- Package imports should be faster (selective loading)
- Measure import time before/after
- Backward-compatible imports have negligible overhead (single `__init__.py` re-export)

---

## Testing Strategy

### Unit Tests
```bash
# Test all config models
pytest tests/test_config.py -v

# Test specific modules
pytest tests/test_config.py::test_simulation_settings -v
pytest tests/test_config.py::test_compensation_settings -v
pytest tests/test_config.py::test_enrollment_settings -v
```

### Integration Tests
```bash
# Full simulation test
python -m navigator_orchestrator run --years 2025 2026 --verbose

# dbt vars mapping test
python -c "
from navigator_orchestrator.config import load_simulation_config, to_dbt_vars
config = load_simulation_config('config/simulation_config.yaml')
dbt_vars = to_dbt_vars(config)
print(f'Generated {len(dbt_vars)} dbt variables')
assert 'start_year' in dbt_vars
assert 'cola_rate' in dbt_vars
print('✅ dbt vars mapping working correctly')
"
```

### Import Tests
```bash
# Test backward-compatible imports
python -c "
from navigator_orchestrator.config import (
    SimulationConfig,
    CompensationSettings,
    EnrollmentSettings,
    OptimizationSettings,
    load_simulation_config,
    to_dbt_vars,
)
print('✅ All backward-compatible imports working')
"

# Test selective imports
python -c "
from navigator_orchestrator.config.base import SimulationSettings
from navigator_orchestrator.config.compensation import PromotionCompensationSettings
from navigator_orchestrator.config.enrollment import AutoEnrollmentSettings
from navigator_orchestrator.config.performance import E068CThreadingSettings
from navigator_orchestrator.config.loader import to_dbt_vars
print('✅ All selective imports working')
"
```

### Performance Tests
```bash
# Measure import time before/after refactoring
python -c "
import time
start = time.time()
from navigator_orchestrator.config import SimulationConfig
elapsed = time.time() - start
print(f'Import time: {elapsed*1000:.2f}ms')
"
```

---

## Success Criteria

### Functional Requirements
- ✅ All existing imports work unchanged (backward compatibility)
- ✅ All tests pass without modification
- ✅ Full simulation runs successfully
- ✅ dbt vars mapping produces identical output
- ✅ All validation methods work correctly

### Quality Requirements
- ✅ Each module under 300 lines (vs 1208-line monolith)
- ✅ Clear module boundaries (single responsibility per module)
- ✅ Comprehensive docstrings explaining module purpose
- ✅ No circular import issues
- ✅ <5% import time regression (acceptable overhead)

### Developer Experience Requirements
- ✅ Settings easy to find (<30 seconds vs 2-3 minutes)
- ✅ Code review diffs focused on single domain
- ✅ New developers can understand config organization quickly
- ✅ Selective imports enable performance optimization

---

## Future Enhancements

### Phase 2 (Future)
1. **Selective import optimization**: Update all modules to use domain-specific imports
2. **Config validation CLI**: `planwise config validate` command
3. **Config migration utilities**: Automated config upgrade scripts
4. **Type stub generation**: Generate `.pyi` stubs for better IDE support

### Technical Debt Reduction
1. **Simplify to_dbt_vars()**: Break down 470-line function into smaller functions
2. **Extract dbt var converters**: Create dedicated converter classes per domain
3. **Add configuration schemas**: JSON Schema for YAML validation

---

## Rollout Plan

### Phase 1: Implementation (2-3 hours)
1. Create package structure (S073-01)
2. Extract modules in order: base → compensation → enrollment → performance → safety → loader (S073-02 to S073-07)
3. Optional import optimization (S073-08)
4. Validation and testing (S073-09)

### Phase 2: Deployment (Immediate)
1. Merge to `main` branch (all tests passing)
2. No migration required (backward compatibility)
3. Update documentation with new module structure
4. Communicate new package organization to team

### Phase 3: Optimization (Optional)
1. Update high-traffic modules to use selective imports
2. Measure performance improvements
3. Document best practices for config imports

---

## Documentation Updates

### Required Documentation
1. **CLAUDE.md**: Update config section to reference new package structure
2. **README.md**: Update config examples to show selective imports
3. **Architecture docs**: Document config package organization

### Example Documentation

#### CLAUDE.md Update
```markdown
### Configuration Management

PlanWise Navigator uses a modular configuration package for type-safe settings management:

- `navigator_orchestrator/config/base.py` - Core simulation settings
- `navigator_orchestrator/config/compensation.py` - Compensation and workforce settings
- `navigator_orchestrator/config/enrollment.py` - Enrollment and eligibility settings
- `navigator_orchestrator/config/performance.py` - Threading and optimization settings
- `navigator_orchestrator/config/safety.py` - Production safety and backup settings
- `navigator_orchestrator/config/loader.py` - YAML loading and dbt variable mapping

**Backward-compatible imports** (all existing code works):
```python
from navigator_orchestrator.config import SimulationConfig, load_simulation_config
```

**Selective imports** (performance optimization):
```python
from navigator_orchestrator.config.compensation import PromotionCompensationSettings
from navigator_orchestrator.config.enrollment import AutoEnrollmentSettings
```
```

---

## Metrics & Monitoring

### Implementation Metrics
- Lines per module (target: <300 lines per module)
- Import time (target: <5% regression)
- Test coverage (maintain 95%+)

### Success Metrics
- Developer time to find settings (target: <30 seconds)
- Code review cycle time (expect 20-30% improvement)
- Onboarding time for config changes (expect 40-50% improvement)

---

## Conclusion

Epic E073 delivers a focused, high-impact refactoring that improves developer experience without any breaking changes. By splitting the 1,208-line config monolith into six focused modules, we enable:

1. **Faster development** - settings easy to find and modify
2. **Better maintainability** - clear module boundaries and single responsibilities
3. **Improved performance** - selective imports reduce module loading overhead
4. **Enhanced code review** - diffs focused on single domain
5. **Better onboarding** - new developers quickly understand config organization

**Recommendation**: Implement immediately. Low risk, high value, executable in a single 2-3 hour session.

---

## Story Summary

| Story | Description | Time | Points | Priority |
|-------|-------------|------|--------|----------|
| S073-01 | Create config package structure | 30 min | 2 | P0 |
| S073-02 | Extract base settings module | 30 min | 2 | P0 |
| S073-03 | Extract compensation & workforce module | 30 min | 2 | P0 |
| S073-04 | Extract enrollment & eligibility module | 45 min | 3 | P0 |
| S073-05 | Extract performance optimization module | 45 min | 3 | P0 |
| S073-06 | Extract production safety module | 30 min | 2 | P0 |
| S073-07 | Extract configuration loader module | 45 min | 3 | P0 |
| S073-08 | Update imports throughout codebase | 30 min | 2 | P1 (optional) |
| S073-09 | Validation & testing | 30 min | 2 | P0 |
| **TOTAL** | **Complete refactoring** | **2.5-3 hours** | **21 points** | **MEDIUM** |

**Ready to execute TODAY. All stories are well-defined, testable, and independent.**
