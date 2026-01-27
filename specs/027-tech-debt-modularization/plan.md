# Implementation Plan: Technical Debt Modularization

**Branch**: `027-tech-debt-modularization` | **Date**: 2026-01-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/027-tech-debt-modularization/spec.md`

## Summary

Split 4 large monolithic Python files (totaling 4,004 lines) into focused module packages following the proven E072/E073 patterns. Each package will have a foundation layer with zero dependencies, focused modules under 500 lines (750 max for cohesion), and backward-compatible re-exports.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Existing codebase (no new dependencies)
**Storage**: N/A (code refactoring only)
**Testing**: pytest with existing fixtures from `tests/fixtures/`
**Target Platform**: Linux/macOS (work laptop deployment)
**Project Type**: Single monorepo (existing structure)
**Performance Goals**: No regression - identical simulation results pre/post refactoring
**Constraints**: Maintain 90%+ test coverage, 100% backward-compatible imports
**Scale/Scope**: 4 files → 4 packages (19 new modules total)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Event Sourcing & Immutability | N/A | No event store changes |
| II. Modular Architecture | ✅ ALIGNS | Directly supports: "no module exceeds ~600 lines" |
| III. Test-First Development | ✅ ALIGNS | FR-006/FR-007 require 90%+ coverage preservation |
| IV. Enterprise Transparency | N/A | No logging/audit changes |
| V. Type-Safe Configuration | N/A | No configuration changes |
| VI. Performance & Scalability | ✅ ALIGNS | No performance regression allowed (SC-006) |

**Gate Status**: ✅ PASSED - This refactoring directly supports Constitution Principle II (Modular Architecture).

## Project Structure

### Documentation (this feature)

```text
specs/027-tech-debt-modularization/
├── plan.md              # This file
├── research.md          # Phase 0 output (E072/E073 patterns)
├── spec.md              # Feature specification
├── checklists/
│   └── requirements.md  # Quality checklist
└── tasks.md             # Phase 2 output (after /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── monitoring/                    # NEW: Split from performance_monitor.py
│   ├── __init__.py               # Re-exports for backward compat
│   ├── data_models.py            # PerformanceMetrics, PerformanceCheckpoint, etc.
│   ├── base.py                   # PerformanceMonitor class
│   ├── duckdb_monitor.py         # DuckDBPerformanceMonitor class
│   └── recommendations.py        # Optimization recommendation logic
│
├── resources/                     # NEW: Split from resource_manager.py
│   ├── __init__.py               # Re-exports for backward compat
│   ├── data_models.py            # MemoryUsageSnapshot, CPUUsageSnapshot, etc.
│   ├── memory_monitor.py         # MemoryMonitor class
│   ├── cpu_monitor.py            # CPUMonitor class
│   ├── adaptive_scaling.py       # AdaptiveThreadAdjuster class
│   ├── benchmarker.py            # PerformanceBenchmarker class
│   └── manager.py                # ResourceManager facade
│
├── reports/                       # NEW: Split from reports.py
│   ├── __init__.py               # Re-exports for backward compat
│   ├── data_models.py            # WorkforceBreakdown, EventSummary, etc.
│   ├── year_auditor.py           # YearAuditor class
│   ├── multi_year_reporter.py    # MultiYearReporter class
│   └── formatters.py             # ConsoleReporter, ReportTemplate
│
├── performance_monitor.py         # MODIFIED: Backward compat wrapper
├── resource_manager.py            # MODIFIED: Backward compat wrapper
└── reports.py                     # MODIFIED: Backward compat wrapper

planalign_api/services/
├── simulation/                    # NEW: Split from simulation_service.py
│   ├── __init__.py               # Re-exports for backward compat
│   ├── service.py                # SimulationService orchestrator
│   ├── subprocess_handler.py     # Platform-specific subprocess mgmt
│   ├── result_exporter.py        # Excel export functionality
│   ├── output_parser.py          # Log parsing, progress extraction
│   └── telemetry_publisher.py    # WebSocket broadcasting
│
└── simulation_service.py          # MODIFIED: Backward compat wrapper

tests/unit/
├── monitoring/                    # NEW: Tests for monitoring package
│   ├── __init__.py
│   ├── test_base_monitor.py
│   └── test_duckdb_monitor.py
│
├── resources/                     # NEW: Tests for resources package
│   ├── __init__.py
│   ├── test_memory_monitor.py
│   └── test_cpu_monitor.py
│
├── reports/                       # NEW: Tests for reports package
│   ├── __init__.py
│   ├── test_year_auditor.py
│   └── test_multi_year_reporter.py
│
└── simulation/                    # NEW: Tests for simulation package
    ├── __init__.py
    ├── test_service.py
    └── test_subprocess_handler.py
```

**Structure Decision**: Follow existing E072 pattern - create subpackages within existing directories, maintain original files as backward-compatibility wrappers.

## Complexity Tracking

No constitution violations. This refactoring directly aligns with Principle II (Modular Architecture).

## Implementation Phases

### Phase 1: monitoring/ Package (Lowest Risk)

**Source**: `planalign_orchestrator/performance_monitor.py` (1,110 lines)

| New Module | Classes/Functions | Est. Lines |
|------------|-------------------|------------|
| `data_models.py` | PerformanceMetrics, PerformanceLevel, PerformanceCheckpoint, PerformanceOptimization | ~100 |
| `base.py` | PerformanceMonitor | ~200 |
| `duckdb_monitor.py` | DuckDBPerformanceMonitor | ~550 |
| `recommendations.py` | Optimization suggestion logic (extracted from DuckDBPerformanceMonitor) | ~200 |

**Dependency Order**: data_models → base → recommendations → duckdb_monitor

### Phase 2: resources/ Package (Medium Complexity)

**Source**: `planalign_orchestrator/resource_manager.py` (1,067 lines)

| New Module | Classes/Functions | Est. Lines |
|------------|-------------------|------------|
| `data_models.py` | MemoryUsageSnapshot, CPUUsageSnapshot, ResourcePressure, BenchmarkResult | ~100 |
| `memory_monitor.py` | MemoryMonitor | ~250 |
| `cpu_monitor.py` | CPUMonitor | ~180 |
| `adaptive_scaling.py` | AdaptiveThreadAdjuster | ~200 |
| `benchmarker.py` | PerformanceBenchmarker | ~200 |
| `manager.py` | ResourceManager (facade) | ~150 |

**Dependency Order**: data_models → memory_monitor, cpu_monitor → adaptive_scaling, benchmarker → manager

### Phase 3: reports/ Package (Straightforward)

**Source**: `planalign_orchestrator/reports.py` (881 lines)

| New Module | Classes/Functions | Est. Lines |
|------------|-------------------|------------|
| `data_models.py` | WorkforceBreakdown, EventSummary, YearAuditReport, MultiYearSummary | ~100 |
| `year_auditor.py` | YearAuditor | ~350 |
| `multi_year_reporter.py` | MultiYearReporter | ~300 |
| `formatters.py` | ConsoleReporter, ReportTemplate | ~100 |

**Dependency Order**: data_models → formatters → year_auditor, multi_year_reporter

### Phase 4: simulation/ Package (Highest Complexity)

**Source**: `planalign_api/services/simulation_service.py` (946 lines)

| New Module | Classes/Functions | Est. Lines |
|------------|-------------------|------------|
| `subprocess_handler.py` | _create_subprocess, _wait_subprocess, platform detection | ~150 |
| `output_parser.py` | Log parsing, progress extraction, year/stage detection | ~150 |
| `result_exporter.py` | _export_results_to_excel, Excel formatting | ~150 |
| `telemetry_publisher.py` | WebSocket broadcasting logic | ~100 |
| `service.py` | SimulationService (orchestrates above) | ~350 |

**Dependency Order**: subprocess_handler, output_parser, result_exporter, telemetry_publisher → service

## Verification Strategy

### After Each Phase

```bash
# Unit tests pass
pytest -m fast

# System health check
planalign health

# Simulation preview works
planalign simulate 2025 --dry-run

# Import compatibility
python -c "from planalign_orchestrator.performance_monitor import PerformanceMonitor; print('OK')"
```

### After All Phases

```bash
# Full test suite with coverage
pytest --cov=planalign_orchestrator --cov=planalign_api --cov-report=html

# Complete simulation
planalign simulate 2025-2027

# Verify coverage maintained
coverage report --fail-under=90
```

## Risk Mitigations

| Risk | Mitigation | Verification |
|------|------------|--------------|
| Circular imports | Foundation layer first (data_models.py has no internal deps) | `python -c "import package"` after each module |
| Broken imports | Re-export all public symbols in `__init__.py` | Existing tests catch import errors |
| Test coverage drop | Run coverage after each phase | `pytest --cov --cov-fail-under=90` |
| Merge conflicts | Complete one package per PR | Small, focused commits |
