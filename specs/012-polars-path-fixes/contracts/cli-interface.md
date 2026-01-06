# CLI Interface Contract: --polars-output Option

**Feature**: 012-polars-path-fixes
**Command**: `planalign simulate`

## New Option

```
--polars-output PATH    Directory for Polars parquet output (default: data/parquet/events)
```

## Option Specification

| Property | Value |
|----------|-------|
| Name | `--polars-output` |
| Type | `Optional[Path]` |
| Default | `None` (uses config default: `data/parquet/events`) |
| Required | No |
| Requires | `--use-polars-engine` (warning if used without) |

## Behavior

1. **When specified**: Parquet files are written to the specified directory
2. **When not specified**: Uses default from `config.yaml` or hardcoded `data/parquet/events`
3. **Directory creation**: Automatically creates directory if it doesn't exist
4. **Path validation**: Validates path is writable before starting simulation

## Examples

```bash
# Use default output path
planalign simulate 2025-2027 --use-polars-engine

# Custom output path (relative)
planalign simulate 2025-2027 --use-polars-engine --polars-output ./custom/parquet

# Custom output path (absolute)
planalign simulate 2025-2027 --use-polars-engine --polars-output /data/simulations/parquet

# Warning: --polars-output without --use-polars-engine
planalign simulate 2025-2027 --polars-output ./custom
# Output: Warning: --polars-output has no effect without --use-polars-engine
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Directory doesn't exist | Auto-create with `mkdir -p` equivalent |
| No write permission | Error before simulation starts |
| Invalid path characters | Error with path validation message |
| --polars-output without --use-polars-engine | Warning message, option ignored |
