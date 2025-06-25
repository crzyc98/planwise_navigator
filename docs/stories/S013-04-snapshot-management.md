# Story S013-04: Snapshot Management Operation

**Epic**: E013 - Dagster Simulation Pipeline Modularization
**Priority**: Medium
**Estimate**: 3 story points
**Status**: Not Started

## User Story

**As a** PlanWise Navigator developer
**I want** dbt snapshot operations extracted into a dedicated operation
**So that** workforce state snapshot management is centralized and reusable across different simulation contexts

## Background

The current pipeline has snapshot execution logic scattered across multiple locations:
- Line 1085-1102 in `run_multi_year_simulation` (current year snapshot)
- Line 888-909 in `run_multi_year_simulation` (previous year snapshot for year > start_year)
- Embedded within single-year simulation contexts

Snapshot operations have specific requirements:
- Year-end workforce state capture for SCD (Slowly Changing Dimension) tracking
- Dependency on completed workforce snapshot generation
- Special handling for baseline snapshots vs regular year snapshots

## Acceptance Criteria

### Functional Requirements
1. **Snapshot Operation Creation**
   - [ ] Create `run_dbt_snapshot_for_year` operation
   - [ ] Support both current year and historical year snapshots
   - [ ] Use `execute_dbt_command` utility (from S013-01)
   - [ ] Handle snapshot-specific error scenarios

2. **Snapshot Types Support**
   - [ ] **End-of-year snapshots**: Capture final workforce state after all events
   - [ ] **Baseline snapshots**: Capture state for year before simulation starts
   - [ ] **Recovery snapshots**: Support rebuilding missing snapshots during validation

3. **Integration Points**
   - [ ] Replace snapshot logic in `run_multi_year_simulation`
   - [ ] Support both single-year and multi-year simulation contexts
   - [ ] Maintain existing error handling and logging behavior

### Technical Requirements
1. **Operation Signature**
```python
@op(required_resource_keys={"dbt"})
def run_dbt_snapshot_for_year(
    context: OpExecutionContext,
    year: int,
    snapshot_type: str = "end_of_year"
) -> Dict[str, Any]:
    """
    Execute dbt snapshot for workforce state.

    Args:
        year: Simulation year for snapshot
        snapshot_type: Type of snapshot - 'end_of_year', 'baseline', 'recovery'

    Returns:
        Dict with snapshot metadata and execution info
    """
```

2. **Snapshot Execution Logic**
   - [ ] Execute `dbt snapshot --select scd_workforce_state --vars {simulation_year: year}`
   - [ ] Handle full_refresh appropriately (snapshots rarely need this)
   - [ ] Validate snapshot completion with record count checks
   - [ ] Return metadata about snapshot success and record counts

3. **Error Handling**
   - [ ] Specific error messages for snapshot failures
   - [ ] Graceful handling when scd_workforce_state doesn't exist
   - [ ] Validation that prerequisite workforce data exists
   - [ ] Recovery suggestions in error messages

## Implementation Details

### Current Snapshot Code Locations
**Multi-year simulation - previous year snapshot (lines 888-909)**:
```python
context.log.info(f"Running dbt snapshot for end of year {year - 1}")
snapshot_cmd = [
    "snapshot",
    "--select",
    "scd_workforce_state",
    "--vars",
    f"{{simulation_year: {year - 1}}}"
]
if full_refresh and year == start_year + 1:
    snapshot_cmd.append("--full-refresh")

snap_invocation = dbt.cli(snapshot_cmd, context=context).wait()
if (snap_invocation.process is None or snap_invocation.process.returncode != 0):
    stdout = snap_invocation.get_stdout() or ""
    stderr = snap_invocation.get_stderr() or ""
    raise Exception(f"Failed to run dbt snapshot for year {year - 1}. STDOUT: {stdout}, STDERR: {stderr}")
```

**Multi-year simulation - current year snapshot (lines 1085-1102)**:
```python
context.log.info(f"Running dbt snapshot for end of year {year}")
snapshot_cmd_curr = [
    "snapshot",
    "--select",
    "scd_workforce_state",
    "--vars",
    f"{{simulation_year: {year}}}"
]
snap_invocation_curr = dbt.cli(snapshot_cmd_curr, context=context).wait()
if (snap_invocation_curr.process is None or snap_invocation_curr.process.returncode != 0):
    stdout = snap_invocation_curr.get_stdout() or ""
    stderr = snap_invocation_curr.get_stderr() or ""
    raise Exception(f"Failed to run dbt snapshot for year {year}. STDOUT: {stdout}, STDERR: {stderr}")
```

### New Modular Implementation
```python
@op(required_resource_keys={"dbt"})
def run_dbt_snapshot_for_year(
    context: OpExecutionContext,
    year: int,
    snapshot_type: str = "end_of_year",
    full_refresh: bool = False
) -> Dict[str, Any]:
    """Execute dbt snapshot for workforce state."""

    # Validate prerequisites based on snapshot type
    if snapshot_type == "end_of_year":
        _validate_workforce_snapshot_exists(context, year)
    elif snapshot_type == "baseline":
        _validate_baseline_workforce_exists(context)

    # Execute snapshot
    context.log.info(f"Running dbt snapshot for {snapshot_type} of year {year}")

    try:
        execute_dbt_command(
            context,
            ["snapshot", "--select", "scd_workforce_state"],
            {"simulation_year": year},
            full_refresh,
            f"{snapshot_type} snapshot for year {year}"
        )

        # Validate snapshot success
        record_count = _count_snapshot_records(context, year)

        result = {
            "year": year,
            "snapshot_type": snapshot_type,
            "record_count": record_count,
            "success": True
        }

        context.log.info(
            f"Snapshot completed successfully: {record_count} records for year {year}"
        )
        return result

    except Exception as e:
        context.log.error(f"Snapshot failed for year {year}: {e}")
        return {
            "year": year,
            "snapshot_type": snapshot_type,
            "success": False,
            "error": str(e)
        }

def _validate_workforce_snapshot_exists(context: OpExecutionContext, year: int) -> None:
    """Validate that workforce snapshot exists for the year before snapshotting."""
    conn = duckdb.connect(str(DB_PATH))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
            [year]
        ).fetchone()[0]

        if count == 0:
            raise ValueError(
                f"No workforce snapshot found for year {year}. "
                f"Cannot create SCD snapshot without workforce data."
            )

        context.log.info(f"Validated workforce snapshot exists: {count} records for year {year}")

    finally:
        conn.close()

def _validate_baseline_workforce_exists(context: OpExecutionContext) -> None:
    """Validate that baseline workforce exists before creating baseline snapshot."""
    conn = duckdb.connect(str(DB_PATH))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'"
        ).fetchone()[0]

        if count == 0:
            raise ValueError(
                "No baseline workforce found. Cannot create baseline snapshot."
            )

        context.log.info(f"Validated baseline workforce exists: {count} active employees")

    finally:
        conn.close()

def _count_snapshot_records(context: OpExecutionContext, year: int) -> int:
    """Count records in SCD snapshot for validation."""
    conn = duckdb.connect(str(DB_PATH))
    try:
        # Note: Actual SCD table name may differ - adjust based on dbt snapshot config
        count = conn.execute(
            "SELECT COUNT(*) FROM scd_workforce_state WHERE simulation_year = ?",
            [year]
        ).fetchone()[0]
        return count
    except Exception as e:
        context.log.warning(f"Could not validate snapshot record count: {e}")
        return -1  # Indicate validation failed but don't fail the operation
    finally:
        conn.close()
```

### Integration Updates
```python
# In run_multi_year_simulation - replace both snapshot blocks with:

# Previous year snapshot (if needed)
if year > start_year:
    run_dbt_snapshot_for_year(context, year - 1, "end_of_year", full_refresh and year == start_year + 1)

# Current year snapshot
run_dbt_snapshot_for_year(context, year, "end_of_year")

# Baseline snapshot (at start of simulation)
if year == start_year:
    run_dbt_snapshot_for_year(context, start_year - 1, "baseline")
```

## Testing Requirements

### Unit Tests
1. **Basic Functionality**
   - [ ] Test end_of_year snapshot execution
   - [ ] Test baseline snapshot execution
   - [ ] Test different year values
   - [ ] Test full_refresh flag handling

2. **Validation Logic**
   - [ ] Test prerequisite validation for different snapshot types
   - [ ] Test behavior when workforce data missing
   - [ ] Test record count validation
   - [ ] Test error handling and recovery

3. **Integration Testing**
   - [ ] Test operation integration with multi-year pipeline
   - [ ] Test operation integration with single-year contexts
   - [ ] Verify no behavior changes from current implementation

### Edge Cases
1. **Data Scenarios**
   - [ ] Empty workforce snapshots
   - [ ] Missing baseline data
   - [ ] Corrupted SCD table
   - [ ] Very large datasets

2. **Error Scenarios**
   - [ ] dbt snapshot command failures
   - [ ] Database connection issues
   - [ ] Insufficient permissions
   - [ ] Disk space limitations

## Definition of Done

- [ ] `run_dbt_snapshot_for_year` operation implemented and tested
- [ ] Validation helper functions implemented and tested
- [ ] Snapshot logic removed from multi-year simulation
- [ ] Integration points updated to use new operation
- [ ] Unit tests written and passing (>95% coverage)
- [ ] Integration tests confirm identical behavior
- [ ] Error handling scenarios tested and validated
- [ ] Code review completed and approved

## Dependencies

- **Upstream**: S013-01 (dbt Command Utility) - required for execute_dbt_command
- **Downstream**: S013-06 (Multi-Year Transformation) - will integrate this operation

## Risk Mitigation

1. **Snapshot Integrity**:
   - Comprehensive validation before and after snapshot execution
   - Record count verification to detect partial failures
   - Clear error messages for troubleshooting

2. **Performance Impact**:
   - Monitor snapshot execution time with large datasets
   - Consider parallel snapshot execution if beneficial

3. **SCD Schema Dependencies**:
   - Validate SCD table structure and naming conventions
   - Test with different dbt snapshot configurations
   - Handle schema evolution gracefully

---

**Implementation Notes**: Focus on robustness and validation since snapshots are critical for year-over-year simulation continuity. Start with comprehensive unit tests before integration.
