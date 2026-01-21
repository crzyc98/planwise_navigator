# Research: Remove Polars Event Factory

**Branch**: `024-remove-polars-pipeline` | **Date**: 2026-01-21

## Purpose

This research document captures the technical investigation required to safely remove the Polars event factory system. Since this is a deletion/removal task rather than new feature development, the research focuses on:

1. Complete inventory of files to delete
2. Complete inventory of files requiring modification
3. Dependencies and import chains
4. Deletion order to avoid import errors
5. Validation strategy

## Decision 1: Deletion Scope

**Decision**: Remove all Polars-specific code (core modules, tests, benchmarks) while preserving SQL mode functionality.

**Rationale**:
- The Polars pipeline was implemented for E076/E077 performance optimization
- Maintaining dual execution paths creates testing complexity
- SQL mode provides equivalent functionality with better dbt test integration
- Polars mode bypasses dbt validation framework

**Alternatives Considered**:
- Deprecation warnings only (rejected: doesn't reduce maintenance burden)
- Disable Polars at runtime (rejected: dead code remains in codebase)
- Keep Polars as optional install (rejected: complexity of maintaining two paths remains)

## Decision 2: Deletion Order Strategy

**Decision**: Delete in reverse-dependency order to prevent import errors during incremental commits.

**Rationale**:
- Tests depend on core modules → delete tests first
- CLI/API depend on orchestrator → modify orchestrator first
- Core modules depend on config → simplify config before deleting modules

**Order**:
1. Tests and benchmarks (no dependencies on them)
2. Orchestrator methods that call Polars (removes usage)
3. Configuration classes (removes definitions)
4. Core Polars modules (final cleanup)

**Alternatives Considered**:
- Delete all at once (rejected: harder to debug if issues arise)
- Delete core modules first (rejected: causes immediate import errors)

## Decision 3: Legacy Configuration Handling

**Decision**: Silently ignore `advanced.engine: 'polars'` in workspace configurations.

**Rationale**:
- FR-006 requires backward compatibility with existing workspaces
- Users should not need to manually edit saved workspaces
- No functional impact since SQL mode is now the only path

**Implementation**:
- TypeScript types accept 'polars' but UI doesn't display selector
- Backend ignores engine setting and always uses SQL
- No migration utility needed

**Alternatives Considered**:
- Error on Polars config (rejected: breaks existing workspaces)
- Auto-migrate configs (rejected: unnecessary complexity)
- Deprecation warning in logs (rejected: noise for silent transition)

## Decision 4: Polars Library Dependency

**Decision**: Keep `polars` as optional dependency in pyproject.toml.

**Rationale**:
- Polars may be used for other data analysis tasks outside event generation
- Removing from requirements could break other workflows
- Out of scope per spec: "Removing the polars Python library from the project"

**Implementation**:
- No changes to pyproject.toml dependencies
- Code simply no longer imports/uses polars for event generation

## File Inventory

### Files to Delete (12 files, ~9,894 lines)

| Category | File | Lines |
|----------|------|-------|
| Core | `planalign_orchestrator/polars_event_factory.py` | 1,988 |
| Core | `planalign_orchestrator/polars_state_pipeline.py` | 2,175 |
| Core | `planalign_orchestrator/polars_integration.py` | 226 |
| Test | `tests/test_polars_state_pipeline.py` | 894 |
| Test | `tests/test_e077_integration.py` | 255 |
| Test | `tests/integration/test_hybrid_pipeline.py` | 486 |
| Test | `tests/test_deferral_rate_builder.py` | 427 |
| Test | `tests/test_enrollment_state_builder.py` | 368 |
| Test | `tests/test_tenure_calculation.py` | 366 |
| Test | `tests/test_escalation_hire_date_filter.py` | 248 |
| Script | `scripts/benchmark_state_accumulation.py` | 748 |
| Script | `scripts/benchmark_event_generation.py` | 1,187 |

### Files to Modify (13 files)

| Category | File | Changes |
|----------|------|---------|
| Orchestrator | `pipeline_orchestrator.py` | Remove imports, settings, calls |
| Orchestrator | `pipeline/event_generation_executor.py` | Remove `_execute_polars_event_generation()` |
| Orchestrator | `pipeline/year_executor.py` | Remove Polars state methods |
| Config | `config/performance.py` | Remove `PolarsEventSettings` class |
| Config | `config/loader.py` | Remove Polars getter methods |
| Config | `config/export.py` | Remove Polars dbt_vars export |
| CLI | `main.py` | Remove `--use-polars-engine`, `--polars-output` |
| CLI | `commands/simulate.py` | Remove Polars parameters |
| CLI | `integration/orchestrator_wrapper.py` | Remove Polars config logic |
| API | `services/simulation_service.py` | Remove Polars branching |
| Frontend | `types.ts` | Simplify engine type |
| Frontend | `constants.ts` | Change default engine |
| Frontend | `components/ConfigStudio.tsx` | Remove engine selector UI |

## Import Chain Analysis

```
planalign_cli/
├── commands/simulate.py
│   └── imports orchestrator_wrapper.py
│       └── imports pipeline_orchestrator.py
│           └── imports polars_integration.py  ← REMOVE
│               └── imports polars_event_factory.py  ← DELETE
│
planalign_orchestrator/
├── pipeline_orchestrator.py
│   └── imports polars_integration.py  ← REMOVE
│
├── pipeline/event_generation_executor.py
│   └── lazy imports polars_event_factory.py  ← REMOVE (line 264)
│
├── pipeline/year_executor.py
│   └── imports polars_state_pipeline.py  ← REMOVE (line 34)
│       └── StateAccumulatorEngine, StateAccumulatorConfig
```

## Validation Strategy

### Pre-Deletion Checks
- [ ] Run `pytest -m fast` to establish baseline
- [ ] Run `dbt test --threads 1` to establish baseline
- [ ] Count existing test files: `ls tests/test_*.py | wc -l`

### Post-Deletion Checks
- [ ] `pytest -m fast` passes (fewer tests, same success rate)
- [ ] `dbt test --threads 1` passes (no regressions)
- [ ] `planalign simulate --help` shows no Polars options
- [ ] `planalign simulate 2025` completes successfully
- [ ] `grep -r "polars_event_factory" planalign_*` returns nothing
- [ ] `grep -r "polars_state_pipeline" planalign_*` returns nothing

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Import error after deletion | Medium | High | Delete in reverse-dependency order |
| Test failure in unrelated test | Low | Medium | Run tests after each deletion phase |
| Missing Polars reference | Low | Low | grep audit before final commit |
| Legacy workspace failure | Low | High | Explicit ignore logic for engine setting |

## Conclusion

The research confirms the deletion is feasible and low-risk when executed in the proper order. All NEEDS CLARIFICATION items from the technical context are resolved:

- No new dependencies needed
- No new patterns to research
- Deletion order established
- Legacy config handling defined
- Validation strategy clear

Ready to proceed to task generation.
