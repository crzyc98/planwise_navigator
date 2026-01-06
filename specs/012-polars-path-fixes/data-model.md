# Data Model: Polars Mode Path Handling Fixes

**Branch**: `012-polars-path-fixes`
**Date**: 2026-01-06

## Overview

This feature is a bug fix that does not introduce new data entities. It modifies how existing path data flows through the system.

## Entities

### Existing: PolarsSettings (Modified)

The existing `PolarsSettings` Pydantic model will accept an optional `output_path` override.

**Current Fields** (unchanged):
- `enabled: bool`
- `max_threads: int`
- `batch_size: int`
- `output_path: str` - default: `"data/parquet/events"`
- `fallback_on_error: bool`
- `enable_profiling: bool`
- `enable_compression: bool`
- `compression_level: int`
- `max_memory_gb: float`
- `lazy_evaluation: bool`
- `streaming: bool`
- `parallel_io: bool`

**Behavior Change**:
- `output_path` can now be overridden at runtime via CLI `--polars-output` option
- When specified, takes precedence over config file value

### Data Flow: Path Normalization

```

  CLI/Studio Input          Path Processing          DuckDB Query
  ================         ================         ==============

  Windows path       →     Path object        →     POSIX string
  "C:\ws\data"             Path("C:/ws/data")       "C:/ws/data"

  Relative path      →     Path object        →     POSIX string
  "data\parquet"           Path("data/parquet")     "../data/parquet"

  POSIX path         →     Path object        →     POSIX string
  "data/parquet"           Path("data/parquet")     "../data/parquet"

```

## Validation Rules

1. **Output Path Validation**:
   - Path must be a valid filesystem path
   - Parent directory is automatically created if it doesn't exist
   - Write permission check performed before simulation starts

2. **DuckDB Path Normalization**:
   - All paths passed to DuckDB MUST use forward slashes
   - Paths relative to dbt/ directory MUST start with `../` for project-relative paths
   - Absolute paths are converted to dbt-relative paths when possible

## State Transitions

No state transitions - this feature modifies path handling logic only, not stateful entities.

## Relationships

```
SimulationConfig  ──contains──>  PolarsSettings
       │                               │
       │                               │ output_path
       ▼                               ▼
  CLI Option      ──overrides──>  Runtime Path
  --polars-output                      │
                                       │ as_posix()
                                       ▼
                              DuckDB Parquet Query
```
