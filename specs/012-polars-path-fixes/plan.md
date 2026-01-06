# Implementation Plan: Polars Mode Path Handling Fixes

**Branch**: `012-polars-path-fixes` | **Date**: 2026-01-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-polars-path-fixes/spec.md`

## Summary

Fix two blocking bugs in Polars mode: (1) Windows path format incompatibility where backslashes break DuckDB's `read_parquet()`, and (2) missing workspace isolation causing Polars parquet files to go to a global location instead of workspace-specific directories when running from Studio.

The fix involves converting all paths to POSIX format using `Path.as_posix()` before passing to DuckDB, and adding a `--polars-output` CLI option that Studio can use to specify workspace-specific output directories.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: pathlib (stdlib), Typer (CLI), Pydantic v2 (config), DuckDB (storage)
**Storage**: DuckDB databases (scenario-specific), Parquet files (Polars output)
**Testing**: pytest with fixtures from `tests/fixtures/`
**Target Platform**: Windows (primary fix), Linux/macOS (no regression)
**Project Type**: single (monorepo with orchestrator, CLI, API packages)
**Performance Goals**: No performance regression; maintain 375× Polars speedup
**Constraints**: Must maintain backward compatibility with existing CLI behavior
**Scale/Scope**: 3 files modified, 2 new CLI parameters, ~50 lines of changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ Pass | No changes to event storage or immutability |
| II. Modular Architecture | ✅ Pass | Changes isolated to path handling logic |
| III. Test-First Development | ✅ Pass | Will add tests for path conversion |
| IV. Enterprise Transparency | ✅ Pass | Path conversions will be logged |
| V. Type-Safe Configuration | ✅ Pass | New CLI option uses Typer type annotations |
| VI. Performance & Scalability | ✅ Pass | No performance impact; path conversion is O(1) |

**Gate Result**: PASS - All principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/012-polars-path-fixes/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (minimal - no new entities)
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── pipeline/
│   └── event_generation_executor.py  # FR-001, FR-006: POSIX path conversion
└── pipeline_orchestrator.py          # FR-002: Accept polars_output config

planalign_cli/
└── commands/
    └── simulate.py                   # FR-002: Add --polars-output option

planalign_api/
└── services/
    └── simulation_service.py         # FR-003: Pass workspace-specific path

tests/
├── unit/
│   └── test_path_handling.py         # New: Path conversion tests
└── integration/
    └── test_polars_workspace.py      # New: Workspace isolation tests
```

**Structure Decision**: Existing monorepo structure. Changes touch orchestrator pipeline, CLI commands, and API services - all within established package boundaries.

## Complexity Tracking

> No complexity violations - changes are minimal and isolated

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | N/A | N/A |
