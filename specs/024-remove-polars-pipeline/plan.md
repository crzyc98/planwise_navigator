# Implementation Plan: Remove Polars Event Factory

**Branch**: `024-remove-polars-pipeline` | **Date**: 2026-01-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/024-remove-polars-pipeline/spec.md`

## Summary

Remove the Polars event factory system completely to simplify the codebase and rely exclusively on SQL/dbt mode for event generation. This involves deleting ~4,400 lines of core Polars implementation, ~3,600 lines of Polars-specific tests, and modifying 13+ files to remove hybrid SQL/Polars branching logic. The result is a simpler, more maintainable single-path architecture where all data flows through dbt's validation framework.

## Technical Context

**Language/Version**: Python 3.11, TypeScript 5.x (frontend)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, FastAPI (API), React 18 + Vite (frontend), Pydantic v2 (config), Typer/Rich (CLI)
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`)
**Testing**: pytest (Python), dbt test (SQL)
**Target Platform**: Linux server, work laptops (Windows/Mac)
**Project Type**: Web application (backend + frontend) with CLI
**Performance Goals**: SQL mode acceptable for <10,000 employees over 5-10 years
**Constraints**: Single-threaded execution default for stability
**Scale/Scope**: Removing ~14,900 lines across 25 files (3 deletions of core modules, 9 deletions of tests/scripts, 13 modifications)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Event Sourcing & Immutability** | PASS | No change - SQL mode maintains immutable event store |
| **II. Modular Architecture** | PASS | Improves modularity by removing dual-path complexity |
| **III. Test-First Development** | PASS | Removing Polars tests, SQL tests remain comprehensive |
| **IV. Enterprise Transparency** | PASS | No change to audit logging |
| **V. Type-Safe Configuration** | PASS | Simplifying config by removing Polars settings |
| **VI. Performance & Scalability** | PASS | SQL mode is documented default; Polars was opt-in |

**Gate Status**: PASSED - All principles satisfied. This is a simplification/removal task that improves alignment with Constitution Principle II (Modular Architecture).

## Project Structure

### Documentation (this feature)

```text
specs/024-remove-polars-pipeline/
├── plan.md              # This file
├── research.md          # Phase 0 output (deletion inventory)
├── tasks.md             # Phase 2 output (task breakdown)
└── checklists/
    └── requirements.md  # Quality checklist
```

### Source Code Impact

```text
# FILES TO DELETE (Core Polars - 4,389 lines)
planalign_orchestrator/
├── polars_event_factory.py     # DELETE (1,988 lines)
├── polars_state_pipeline.py    # DELETE (2,175 lines)
└── polars_integration.py       # DELETE (226 lines)

# FILES TO DELETE (Tests - 3,570 lines)
tests/
├── test_polars_state_pipeline.py       # DELETE (894 lines)
├── test_e077_integration.py            # DELETE (255 lines)
├── test_deferral_rate_builder.py       # DELETE (427 lines)
├── test_enrollment_state_builder.py    # DELETE (368 lines)
├── test_tenure_calculation.py          # DELETE (366 lines)
├── test_escalation_hire_date_filter.py # DELETE (248 lines)
└── integration/
    └── test_hybrid_pipeline.py         # DELETE (486 lines)

# FILES TO DELETE (Scripts - 1,935 lines)
scripts/
├── benchmark_state_accumulation.py     # DELETE (748 lines)
└── benchmark_event_generation.py       # DELETE (1,187 lines)

# FILES TO MODIFY (Orchestrator - remove Polars branching)
planalign_orchestrator/
├── pipeline_orchestrator.py            # MODIFY: Remove polars imports, settings
├── pipeline/
│   ├── event_generation_executor.py    # MODIFY: Remove _execute_polars_event_generation()
│   └── year_executor.py                # MODIFY: Remove Polars state accumulation methods
└── config/
    ├── performance.py                  # MODIFY: Remove PolarsEventSettings class
    ├── loader.py                       # MODIFY: Remove get_polars_settings() etc.
    └── export.py                       # MODIFY: Remove Polars export to dbt_vars

# FILES TO MODIFY (CLI - remove options)
planalign_cli/
├── main.py                             # MODIFY: Remove --use-polars-engine, --polars-output
├── commands/
│   └── simulate.py                     # MODIFY: Remove Polars parameters and display
└── integration/
    └── orchestrator_wrapper.py         # MODIFY: Remove Polars config logic

# FILES TO MODIFY (API - remove engine branching)
planalign_api/
└── services/
    └── simulation_service.py           # MODIFY: Remove Polars mode branching

# FILES TO MODIFY (Frontend - remove engine selector)
planalign_studio/
├── types.ts                            # MODIFY: Remove 'polars' from engine union
├── constants.ts                        # MODIFY: Change default to 'pandas'
└── components/
    └── ConfigStudio.tsx                # MODIFY: Remove engine radio buttons
```

**Structure Decision**: Deletion-focused refactoring. No new directories or files created. Existing structure preserved with simplification.

## Complexity Tracking

> No violations - this is a simplification task that reduces complexity.

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Core Polars LOC | 4,389 | 0 | -4,389 |
| Test LOC (Polars) | 3,570 | 0 | -3,570 |
| Script LOC | 1,935 | 0 | -1,935 |
| Config complexity | Dual-path | Single-path | Simplified |
| Event generation paths | 2 (SQL + Polars) | 1 (SQL) | -1 path |

## Deletion Inventory

### Core Polars Modules (DELETE)

| File | Lines | Purpose |
|------|-------|---------|
| `planalign_orchestrator/polars_event_factory.py` | 1,988 | Core event generation (PolarsEventGenerator, EventFactoryConfig) |
| `planalign_orchestrator/polars_state_pipeline.py` | 2,175 | State accumulation (StateAccumulatorEngine, builders) |
| `planalign_orchestrator/polars_integration.py` | 226 | Integration manager (execute_polars_cohort_generation) |

### Test Files (DELETE)

| File | Lines | Purpose |
|------|-------|---------|
| `tests/test_polars_state_pipeline.py` | 894 | State accumulator tests |
| `tests/test_e077_integration.py` | 255 | E077 Polars integration tests |
| `tests/integration/test_hybrid_pipeline.py` | 486 | Hybrid pipeline tests |
| `tests/test_deferral_rate_builder.py` | 427 | DeferralRateBuilder tests |
| `tests/test_enrollment_state_builder.py` | 368 | EnrollmentStateBuilder tests |
| `tests/test_tenure_calculation.py` | 366 | Tenure calculation tests |
| `tests/test_escalation_hire_date_filter.py` | 248 | Hire date filter tests |

### Benchmark Scripts (DELETE)

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/benchmark_state_accumulation.py` | 748 | Polars state perf benchmarks |
| `scripts/benchmark_event_generation.py` | 1,187 | Polars event perf benchmarks |

## Modification Summary

### Orchestrator Layer

1. **pipeline_orchestrator.py**: Remove `from .polars_integration import execute_polars_cohort_generation`, remove `self.polars_settings`, remove Polars settings display, remove `execute_polars_cohort_generation()` calls

2. **event_generation_executor.py**: Remove `_execute_polars_event_generation()` method (~180 lines), remove Polars imports, simplify `execute_hybrid_event_generation()` to SQL-only

3. **year_executor.py**: Remove `_should_use_polars_state_accumulation()`, `_execute_polars_state_accumulation()`, `_run_polars_post_processing_models()` methods (~170 lines), remove StateAccumulatorEngine imports

### Configuration Layer

4. **config/performance.py**: Remove `PolarsEventSettings` class (~40 lines), simplify `EventGenerationConfig`

5. **config/loader.py**: Remove `get_polars_settings()`, `is_polars_mode_enabled()`, `is_polars_state_accumulation_enabled()`, `get_polars_state_accumulation_settings()` methods (~30 lines)

6. **config/export.py**: Remove Polars settings export to dbt_vars

### CLI Layer

7. **main.py**: Remove `--use-polars-engine`, `--polars-output` parameters

8. **simulate.py**: Remove Polars parameters, warnings, and display logic

9. **orchestrator_wrapper.py**: Remove Polars engine configuration logic

### API Layer

10. **simulation_service.py**: Remove Polars mode branching in scenario execution

### Frontend Layer

11. **types.ts**: Change `engine: 'polars' | 'pandas'` to just accept legacy values silently

12. **constants.ts**: Change default engine from 'polars' to 'pandas'

13. **ConfigStudio.tsx**: Remove engine selection UI (radio buttons)

## Implementation Strategy

### Phase 1: Delete Tests and Scripts (Safe, no dependencies)
- Delete all Polars test files
- Delete benchmark scripts
- Run remaining tests to confirm no breakage

### Phase 2: Remove Orchestrator Polars Logic
- Remove methods from year_executor.py
- Remove methods from event_generation_executor.py
- Remove Polars calls from pipeline_orchestrator.py
- Update imports

### Phase 3: Simplify Configuration
- Remove PolarsEventSettings from performance.py
- Remove Polars methods from loader.py
- Update export.py

### Phase 4: Update CLI
- Remove options from main.py and simulate.py
- Update orchestrator_wrapper.py

### Phase 5: Update API and Frontend
- Simplify simulation_service.py
- Update TypeScript types and constants
- Remove UI engine selector

### Phase 6: Delete Core Polars Modules
- Delete polars_event_factory.py
- Delete polars_state_pipeline.py
- Delete polars_integration.py

### Phase 7: Final Validation
- Run full test suite
- Run multi-year simulation
- Verify CLI help text
- Verify Studio UI

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing tests | Delete Polars tests before modifying code |
| Import errors after deletion | Remove imports before deleting modules |
| Legacy workspace configs | FR-006 requires silent ignore, not error |
| Missing test coverage | SQL tests remain comprehensive (90%+) |

## Acceptance Verification

After implementation, verify:

1. `planalign simulate --help` shows no Polars options
2. `planalign simulate 2025-2027` completes with SQL mode
3. `pytest -m fast` passes (no Polars test failures)
4. `dbt test --threads 1` passes
5. Studio configuration page has no engine selector
6. Legacy workspaces with `engine: 'polars'` load without error
