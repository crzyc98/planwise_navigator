# Quickstart: Polars Mode Path Handling Fixes

**Branch**: `012-polars-path-fixes`
**Date**: 2026-01-06

## What This Fix Does

1. **Windows Compatibility**: Polars mode now works on Windows by converting all parquet paths to forward slashes before passing to DuckDB.

2. **Workspace Isolation**: When running from Studio, Polars parquet files are stored in the workspace-specific scenario folder instead of a global location.

3. **Custom Output Path**: CLI users can specify `--polars-output` to direct parquet files to a custom location.

## Usage

### CLI (Standard)

```bash
# Run Polars simulation (unchanged - works on Windows now)
planalign simulate 2025-2027 --use-polars-engine

# Specify custom output location
planalign simulate 2025-2027 --use-polars-engine --polars-output ./my-output/parquet
```

### Studio

No changes needed - workspace isolation is automatic when running from Studio.

## Testing the Fix

### Windows Path Fix

```bash
# On Windows, this should now complete without path errors
planalign simulate 2025-2027 --use-polars-engine --verbose

# Expected output includes paths like:
#   ../data/parquet/events/simulation_year=2027/*.parquet
# NOT:
#   /data\parquet\events/simulation_year=2027/*.parquet
```

### Workspace Isolation

```bash
# Launch Studio
planalign studio

# Create a workspace, run a Polars simulation
# Check that parquet files appear in:
#   workspaces/{workspace_id}/scenarios/{scenario_id}/data/parquet/events/
# NOT in:
#   data/parquet/events/
```

## Migration Notes

- **No migration required** - existing configurations continue to work
- Old parquet files in global `data/parquet/events/` are not automatically cleaned up
- For fresh starts, delete the global `data/parquet/events/` directory if desired

## Related Files

| File | Purpose |
|------|---------|
| `planalign_orchestrator/pipeline/event_generation_executor.py` | POSIX path conversion |
| `planalign_cli/commands/simulate.py` | `--polars-output` CLI option |
| `planalign_api/services/simulation_service.py` | Workspace path injection |
