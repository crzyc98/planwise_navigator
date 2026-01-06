# Feature Specification: Polars Mode Path Handling Fixes

**Feature Branch**: `012-polars-path-fixes`
**Created**: 2026-01-06
**Status**: Draft
**Input**: Fix two Polars mode path handling issues: (1) Windows backslash compatibility in parquet paths for DuckDB, and (2) workspace-specific Polars output isolation when running from Studio.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Windows User Runs Polars Mode Simulation (Priority: P1)

A user on Windows runs a simulation using the Polars engine mode. The simulation generates parquet files and DuckDB successfully reads them without path format errors.

**Why this priority**: This is a blocking bug that prevents Windows users from using the high-performance Polars mode at all. The 375x performance improvement is completely inaccessible on Windows due to path formatting issues.

**Independent Test**: Can be fully tested by running `planalign simulate 2025-2027 --use-polars-engine` on a Windows machine and verifying the simulation completes without path-related errors.

**Acceptance Scenarios**:

1. **Given** a Windows environment with Polars mode enabled, **When** the simulation generates parquet files and passes the path to DuckDB, **Then** the path uses forward slashes consistently (e.g., `../data/parquet/events/simulation_year=2027/*.parquet`)
2. **Given** a Windows environment with Polars mode enabled, **When** an absolute path is converted to a relative path, **Then** the resulting path uses forward slashes for DuckDB compatibility
3. **Given** a Linux/macOS environment with Polars mode enabled, **When** the simulation runs, **Then** the behavior is unchanged (already uses forward slashes)

---

### User Story 2 - Studio User Runs Polars Mode with Workspace Isolation (Priority: P1)

A user running simulations from PlanAlign Studio with Polars engine has their parquet output files stored within the workspace-specific scenario folder, matching the database isolation pattern already in place.

**Why this priority**: This is also a blocking bug for Studio users. Without workspace isolation, fresh installs fail because the global directory doesn't exist, and multiple workspaces could corrupt each other's data.

**Independent Test**: Can be fully tested by launching Studio, creating a workspace, running a Polars simulation, and verifying parquet files appear in `{workspace}/{scenario}/data/parquet/events/` rather than the global `data/parquet/events/`.

**Acceptance Scenarios**:

1. **Given** a user running a simulation from Studio with Polars engine, **When** parquet files are generated, **Then** they are stored in the workspace-specific scenario folder (e.g., `{workspace}/{scenario}/data/parquet/events/`)
2. **Given** a user with multiple workspaces, **When** running Polars simulations in different workspaces concurrently, **Then** each workspace's parquet files are isolated and do not interfere with each other
3. **Given** a fresh Studio install with a new workspace, **When** running a Polars simulation, **Then** the simulation succeeds (output directories are created automatically)

---

### User Story 3 - CLI User Specifies Custom Polars Output Path (Priority: P2)

A CLI user running simulations can optionally specify a custom output directory for Polars parquet files, giving flexibility for different deployment configurations.

**Why this priority**: This enables the Studio workspace isolation (P1) and provides advanced users with additional configuration control. It's a supporting capability rather than a direct user need.

**Independent Test**: Can be tested by running `planalign simulate 2025 --use-polars-engine --polars-output /custom/path` and verifying parquet files are written to the specified location.

**Acceptance Scenarios**:

1. **Given** a user specifies `--polars-output /custom/path` on the CLI, **When** the Polars simulation runs, **Then** parquet files are written to `/custom/path` instead of the default location
2. **Given** a user does not specify `--polars-output`, **When** the Polars simulation runs from CLI, **Then** the default behavior is unchanged (`data/parquet/events`)

---

### Edge Cases

- What happens when the specified `--polars-output` directory does not exist? The system creates it automatically.
- What happens when the user lacks write permissions to the specified output path? The system provides a clear error message before simulation starts.
- What happens when a path contains spaces or special characters? The system handles paths with spaces correctly on both Windows and Unix systems.
- How does the system handle mixed path scenarios (e.g., absolute polars-output with relative dbt directory)? All paths are normalized to forward slashes before passing to DuckDB.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST convert all parquet file paths to POSIX format (forward slashes) before passing them to DuckDB, regardless of the operating system.
- **FR-002**: System MUST support a `--polars-output` CLI option that specifies the directory for Polars parquet file output.
- **FR-003**: When running from Studio with Polars engine, system MUST store parquet files in the workspace-specific scenario folder (`{workspace}/{scenario}/data/parquet/events/`).
- **FR-004**: System MUST automatically create the Polars output directory if it does not exist.
- **FR-005**: System MUST maintain backward compatibility with existing CLI behavior when `--polars-output` is not specified (default to `data/parquet/events` from project root).
- **FR-006**: System MUST correctly handle both absolute and relative paths when constructing DuckDB-compatible parquet paths.

### Key Entities

- **Polars Output Path**: The directory where Polars parquet files are written. Can be customized via CLI option or determined automatically based on context (CLI vs Studio).
- **DuckDB Parquet Path**: The path passed to DuckDB's `read_parquet()` function. Must always use forward slashes for cross-platform compatibility.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Polars mode simulations complete successfully on Windows without path-related errors (0% failure rate due to path formatting).
- **SC-002**: Studio-launched Polars simulations store parquet files in workspace-specific directories (100% isolation compliance).
- **SC-003**: Fresh Studio installations can run Polars simulations without manual directory creation.
- **SC-004**: Existing Linux/macOS CLI workflows continue to function identically (no regression).
- **SC-005**: Multiple concurrent workspace simulations do not experience data corruption or cross-contamination.

## Assumptions

- The `Path.as_posix()` method is available in Python's `pathlib` (standard library since Python 3.4).
- DuckDB accepts forward-slash paths on all operating systems including Windows.
- The orchestrator's configuration system can accept and propagate custom output paths.
- Studio's simulation service has access to the workspace and scenario path context.
