# Story S013-02: Data Cleaning Operation Extraction

**Epic**: E013 - Dagster Simulation Pipeline Modularization
**Priority**: High
**Estimate**: 2 story points
**Status**: Not Started

## User Story

**As a** PlanWise Navigator developer
**I want** data cleaning logic extracted into a dedicated operation
**So that** the multi-year simulation orchestrator focuses solely on coordination rather than data management

## Background

The current `run_multi_year_simulation` operation contains embedded data cleaning logic (lines 834-848) that:
- Deletes existing simulation data for the year range
- Handles database connection management
- Includes error handling and logging

This mixing of concerns makes the main orchestration logic harder to follow and test. The cleaning logic should be separated into a focused, reusable operation.

## Acceptance Criteria

### Functional Requirements
1. **New Operation Creation**
   - [ ] Create `clean_duckdb_data` operation with appropriate decorators
   - [ ] Accept list of years to clean as parameter
   - [ ] Handle database connection lifecycle properly
   - [ ] Maintain existing error handling behavior

2. **Data Cleaning Logic**
   - [ ] Delete from `fct_yearly_events` WHERE `simulation_year` IN (year_list)
   - [ ] Delete from `fct_workforce_snapshot` WHERE `simulation_year` IN (year_list)
   - [ ] Execute deletions in transaction for consistency
   - [ ] Log number of records deleted per table

3. **Integration with Multi-Year Pipeline**
   - [ ] Call once at start of multi-year simulation
   - [ ] Pass years list from simulation configuration
   - [ ] Remove embedded cleaning logic from `run_multi_year_simulation`
   - [ ] Maintain existing logging messages for compatibility

### Technical Requirements
1. **Operation Signature**
```python
@op(
    config_schema={
        "years": list,
        "db_path": str
    }
)
def clean_duckdb_data(context: OpExecutionContext) -> Dict[str, int]:
    """
    Clean simulation data for specified years.

    Returns:
        Dict containing counts of deleted records per table
    """
```

2. **Database Operations**
   - [ ] Use DuckDB connection from shared database path
   - [ ] Implement proper connection context management (try/finally)
   - [ ] Handle case where tables don't exist yet (graceful failure)
   - [ ] Return deletion counts for observability

3. **Error Handling**
   - [ ] Log warnings for missing tables rather than failing
   - [ ] Capture and log specific SQL errors
   - [ ] Ensure connection is closed even on exceptions
   - [ ] Don't fail pipeline if cleaning partially succeeds

## Implementation Details

### Current Code Location
Lines 834-848 in `run_multi_year_simulation`:
```python
# Clean all data for the simulation years to ensure fresh start
context.log.info(f"Cleaning existing data for years {start_year}-{end_year}")
conn = duckdb.connect(str(DB_PATH))
try:
    for clean_year in range(start_year, end_year + 1):
        conn.execute(
            "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [clean_year]
        )
    context.log.info(
        "Existing events for years %s-%s deleted", start_year, end_year
    )
except Exception as e:
    context.log.warning(f"Error cleaning simulation data: {e}")
finally:
    conn.close()
```

### New Operation Implementation
```python
@op
def clean_duckdb_data(context: OpExecutionContext, years: List[int]) -> Dict[str, int]:
    """Clean simulation data for specified years."""
    results = {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}

    context.log.info(f"Cleaning existing data for years {min(years)}-{max(years)}")
    conn = duckdb.connect(str(DB_PATH))

    try:
        # Clean yearly events
        for year in years:
            deleted_events = conn.execute(
                "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year]
            ).rowcount
            results["fct_yearly_events"] += deleted_events

        # Clean workforce snapshots
        for year in years:
            deleted_snapshots = conn.execute(
                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?", [year]
            ).rowcount
            results["fct_workforce_snapshot"] += deleted_snapshots

        context.log.info(
            f"Deleted {results['fct_yearly_events']} events, "
            f"{results['fct_workforce_snapshot']} snapshots for years {min(years)}-{max(years)}"
        )

    except Exception as e:
        context.log.warning(f"Error cleaning simulation data: {e}")
        # Don't re-raise - allow pipeline to continue
    finally:
        conn.close()

    return results
```

### Integration Pattern
```python
# In run_multi_year_simulation
def run_multi_year_simulation(context: OpExecutionContext, baseline_valid: bool) -> List[YearResult]:
    # ... configuration setup ...

    # Clean data once at start
    years_to_clean = list(range(start_year, end_year + 1))
    cleaning_results = clean_duckdb_data(context, years_to_clean)

    # ... rest of simulation logic ...
```

## Testing Requirements

### Unit Tests
1. **Basic Functionality**
   - [ ] Test single year cleaning
   - [ ] Test multiple years cleaning
   - [ ] Test empty years list handling
   - [ ] Test database connection error handling

2. **Edge Cases**
   - [ ] Test cleaning when tables don't exist
   - [ ] Test cleaning when no matching records exist
   - [ ] Test partial failure scenarios
   - [ ] Test very large year ranges

3. **Integration Testing**
   - [ ] Test operation integration with multi-year pipeline
   - [ ] Verify no impact on subsequent simulation steps
   - [ ] Confirm identical behavior to embedded logic

### Data Validation
1. **Before/After Comparison**
   - [ ] Count records before cleaning operation
   - [ ] Verify expected deletions occurred
   - [ ] Confirm no unintended data loss in other tables
   - [ ] Validate return value accuracy

## Definition of Done

- [ ] `clean_duckdb_data` operation implemented and tested
- [ ] Embedded cleaning logic removed from `run_multi_year_simulation`
- [ ] Integration point updated to call new operation
- [ ] Unit tests written and passing (>95% coverage)
- [ ] Integration test confirms identical pipeline behavior
- [ ] Code review completed and approved
- [ ] Performance impact assessed (should be minimal/positive)

## Dependencies

- **Upstream**: None (independent implementation)
- **Downstream**: S013-06 (Multi-Year Transformation) - will integrate this operation

## Risk Mitigation

1. **Data Loss Prevention**:
   - Implement with transaction safety
   - Add dry-run capability for testing
   - Validate year parameters before execution

2. **Performance Impact**:
   - Benchmark deletion performance with large datasets
   - Consider batch deletion strategies if needed

3. **Backwards Compatibility**:
   - Maintain exact same logging output initially
   - Ensure no behavior changes for downstream operations

---

**Implementation Notes**: This is a foundational change that enables cleaner separation of concerns. Start with thorough testing in development environment before integration.
