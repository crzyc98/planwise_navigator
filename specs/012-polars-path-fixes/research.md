# Research: Polars Mode Path Handling Fixes

**Branch**: `012-polars-path-fixes`
**Date**: 2026-01-06

## Research Questions

### 1. Path Conversion Best Practices for DuckDB

**Question**: What is the correct approach to ensure DuckDB `read_parquet()` works on Windows?

**Decision**: Use `Path.as_posix()` for all paths passed to DuckDB.

**Rationale**:
- DuckDB accepts forward-slash paths universally on all platforms (Windows, Linux, macOS)
- `Path.as_posix()` is part of Python's standard library (pathlib) since Python 3.4
- This is the idiomatic Python approach for cross-platform path handling
- The conversion is O(1) and has no measurable performance impact

**Alternatives Considered**:
- `str(path).replace('\\', '/')`: Works but less readable and not idiomatic
- `os.path.normpath()`: Does NOT convert to forward slashes on Windows
- `pathlib.PurePosixPath()`: Requires additional import, more verbose

**Evidence**:
- DuckDB documentation confirms forward slashes work universally
- Python pathlib documentation recommends `as_posix()` for cross-platform compatibility

### 2. CLI Option Design Pattern

**Question**: How should the `--polars-output` option integrate with the existing CLI?

**Decision**: Add as an optional `typer.Option()` with `None` default, propagate through orchestrator config.

**Rationale**:
- Follows existing pattern in `simulate.py` (see `--database`, `--config` options)
- `None` default preserves backward compatibility
- Typer provides automatic path validation and type conversion

**Alternatives Considered**:
- Environment variable (`POLARS_OUTPUT_PATH`): Less discoverable, harder to document
- Config file only: Doesn't work for Studio's per-scenario path override
- Positional argument: Breaks existing CLI interface

**Evidence**: Existing CLI options in `simulate.py` lines 47-73 follow this pattern.

### 3. Workspace Isolation Pattern

**Question**: How does Studio currently achieve workspace isolation for databases?

**Decision**: Follow the existing pattern in `simulation_service.py` line 340: `scenario_db_path = scenario_path / "simulation.duckdb"`

**Rationale**:
- Consistent with existing database isolation implementation
- Uses the same `scenario_path` context already available
- Follows the `{workspace}/{scenario}/` directory structure

**Alternatives Considered**:
- Global registry mapping workspace IDs to paths: Over-engineered for this use case
- Store path in database metadata: Circular dependency issue
- Configuration file per workspace: Adds complexity, harder to manage

**Evidence**: `simulation_service.py` line 318-352 shows the existing workspace isolation pattern.

### 4. Directory Auto-Creation Pattern

**Question**: Should the system auto-create the Polars output directory?

**Decision**: Yes, use `Path.mkdir(parents=True, exist_ok=True)` before writing.

**Rationale**:
- Matches user expectation from FR-004: "System MUST automatically create the Polars output directory"
- Follows existing pattern (see `results_dir.mkdir(parents=True, exist_ok=True)` at simulation_service.py:152)
- Prevents cryptic errors on fresh installs

**Alternatives Considered**:
- Require pre-existing directory: Poor UX, violates FR-003 for fresh installs
- Create only on CLI (not Studio): Inconsistent behavior
- Create at orchestrator startup: Could create empty directories for unused configurations

**Evidence**: FR-004 explicitly requires auto-creation. Existing code already uses this pattern.

## Summary

All research questions resolved. No outstanding clarifications needed.

| Question | Decision | Confidence |
|----------|----------|------------|
| Path conversion | `Path.as_posix()` | High |
| CLI option design | `typer.Option(None)` | High |
| Workspace isolation | Follow `scenario_path` pattern | High |
| Directory creation | `mkdir(parents=True, exist_ok=True)` | High |
