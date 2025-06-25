# Story S013-05: Single-Year Operation Refactoring

**Epic**: E013 - Dagster Simulation Pipeline Modularization
**Priority**: High
**Estimate**: 4 story points
**Status**: Not Started

## User Story

**As a** PlanWise Navigator developer
**I want** the run_year_simulation operation refactored to use new modular components
**So that** single-year and multi-year simulations share common logic and eliminate code duplication

## Background

The current `run_year_simulation` operation (lines 150-458) contains:
- Repetitive dbt command execution patterns (8+ blocks)
- Embedded event processing logic (lines 295-386) that duplicates multi-year logic
- Direct database connection management
- Mixed concerns of orchestration, validation, and execution

This operation should be refactored to use the new modular components while maintaining its role as the core single-year simulation executor.

## Acceptance Criteria

### Functional Requirements
1. **Utility Integration**
   - [ ] Replace all dbt.cli() calls with `execute_dbt_command` utility
   - [ ] Remove repetitive command building and error handling code
   - [ ] Maintain exact same dbt commands and variable passing
   - [ ] Preserve all existing logging output and behavior

2. **Modular Component Usage**
   - [ ] Replace lines 295-386 (event processing) with `run_dbt_event_models_for_year` op call
   - [ ] Use `run_dbt_snapshot_for_year` for snapshot operations if applicable
   - [ ] Maintain existing validation logic (assert_year_complete, validate_year_results)
   - [ ] Preserve all error handling and recovery mechanisms

3. **Behavior Preservation**
   - [ ] Identical simulation results for same inputs
   - [ ] Same error messages and exception handling
   - [ ] Preserved logging output including hiring debug information
   - [ ] Maintained Epic 11.5 simulation sequence integrity

### Technical Requirements
1. **Function Signature** (unchanged)
```python
@op(
    required_resource_keys={"dbt"},
    config_schema={
        "start_year": int,
        "end_year": int,
        "target_growth_rate": float,
        "total_termination_rate": float,
        "new_hire_termination_rate": float,
        "random_seed": int,
        "full_refresh": bool,
    },
)
def run_year_simulation(context: OpExecutionContext) -> YearResult:
```

2. **Refactored Structure**
   - [ ] Configuration extraction (lines 155-164) - unchanged
   - [ ] Data cleaning logic (lines 167-176) - simplified using new patterns
   - [ ] Enhanced validation (lines 182-273) - maintained
   - [ ] **Step 2**: `int_workforce_previous_year` - use execute_dbt_command
   - [ ] **Step 3**: Event models - use run_dbt_event_models_for_year
   - [ ] **Step 4**: `fct_yearly_events` - use execute_dbt_command
   - [ ] **Step 5**: Workforce snapshot - use execute_dbt_command
   - [ ] **Step 6**: Validation - maintain existing logic

3. **Error Handling**
   - [ ] Maintain existing exception types and messages
   - [ ] Preserve try/catch structure and error logging
   - [ ] Return identical YearResult structure on failures
   - [ ] Keep database connection error handling

## Implementation Details

### Current Code Structure Analysis
**run_year_simulation breakdown**:
- Lines 150-164: Configuration and setup ✅ (keep as-is)
- Lines 167-176: Data cleaning ✅ (simplify with new patterns)
- Lines 182-273: Enhanced validation ✅ (keep as-is)
- Lines 276-292: int_workforce_previous_year ⚡ (use execute_dbt_command)
- Lines 295-386: Event models processing ⚡ (replace with run_dbt_event_models_for_year)
- Lines 388-404: fct_yearly_events ⚡ (use execute_dbt_command)
- Lines 407-438: fct_workforce_snapshot ⚡ (use execute_dbt_command)
- Lines 441-458: Validation and result ✅ (keep as-is)

### Refactored Implementation
```python
@op(
    required_resource_keys={"dbt"},
    config_schema={
        "start_year": int,
        "end_year": int,
        "target_growth_rate": float,
        "total_termination_rate": float,
        "new_hire_termination_rate": float,
        "random_seed": int,
        "full_refresh": bool,
    },
)
def run_year_simulation(context: OpExecutionContext) -> YearResult:
    """
    Executes complete simulation for a single year.
    Implements the precise sequence from Epic 11.5.
    """
    # Get configuration from op config (unchanged)
    config = context.op_config
    year = config["start_year"]
    full_refresh = config.get("full_refresh", False)

    context.log.info(f"Starting simulation for year {year}")
    if full_refresh:
        context.log.info(
            "🔄 Full refresh enabled - will rebuild all incremental models from scratch"
        )

    # Clean existing data for this year (simplified)
    context.log.info(f"Cleaning existing data for year {year}")
    conn = duckdb.connect(str(DB_PATH))
    try:
        conn.execute("DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year])
        context.log.info("Existing events for year %s deleted", year)
    except Exception as e:
        context.log.warning(f"Error cleaning year {year} data: {e}")
    finally:
        conn.close()

    try:
        # Step 1: Enhanced validation (unchanged - lines 182-273)
        if year > 2025:
            # ... existing validation logic ...
            pass

        # Step 2: int_workforce_previous_year (refactored)
        context.log.info(f"Running int_workforce_previous_year for year {year}")
        execute_dbt_command(
            context,
            ["run", "--select", "int_workforce_previous_year"],
            {"simulation_year": year},
            full_refresh,
            f"int_workforce_previous_year for year {year}"
        )

        # Step 3: Event models processing (replaced with modular op)
        context.log.info(f"Running event models for year {year}")
        event_results = run_dbt_event_models_for_year(context, year, config)

        # Step 4: Consolidate events (refactored)
        context.log.info(f"Running fct_yearly_events for year {year}")
        execute_dbt_command(
            context,
            ["run", "--select", "fct_yearly_events"],
            {"simulation_year": year},
            full_refresh,
            f"fct_yearly_events for year {year}"
        )

        # Step 5a: Clean fct_workforce_snapshot (simplified)
        context.log.info(f"Cleaning fct_workforce_snapshot for year {year}")
        conn = duckdb.connect(str(DB_PATH))
        try:
            conn.execute(
                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?", [year]
            )
            context.log.info("Existing snapshot records for year %s deleted", year)
        except Exception as e:
            context.log.warning(
                f"Error cleaning fct_workforce_snapshot for year {year} data: {e}"
            )
        finally:
            conn.close()

        # Step 5b: Generate final workforce snapshot (refactored)
        context.log.info(f"Running fct_workforce_snapshot for year {year}")
        execute_dbt_command(
            context,
            ["run", "--select", "fct_workforce_snapshot"],
            {"simulation_year": year},
            full_refresh,
            f"fct_workforce_snapshot for year {year}"
        )

        # Step 6: Validate results (unchanged)
        year_result = validate_year_results(context, year, config)

        context.log.info(f"Year {year} simulation completed successfully")
        return year_result

    except Exception as e:
        # Error handling (unchanged)
        context.log.error(f"Simulation failed for year {year}: {e}")
        return YearResult(
            year=year,
            success=False,
            active_employees=0,
            total_terminations=0,
            experienced_terminations=0,
            new_hire_terminations=0,
            total_hires=0,
            growth_rate=0.0,
            validation_passed=False,
        )
```

### Code Reduction Analysis
**Before**: 308 lines total
- Lines removed by using execute_dbt_command: ~60 lines (8 dbt command blocks)
- Lines removed by using run_dbt_event_models_for_year: ~91 lines (event processing)
- Net reduction: ~151 lines (49% reduction)

**After**: ~157 lines total (focused on orchestration and validation)

## Testing Requirements

### Unit Tests
1. **dbt Command Integration**
   - [ ] Test all execute_dbt_command calls with various parameters
   - [ ] Test full_refresh flag handling across all commands
   - [ ] Test error handling when dbt commands fail
   - [ ] Test configuration parameter passing

2. **Modular Operation Integration**
   - [ ] Test run_dbt_event_models_for_year integration
   - [ ] Verify event processing results are handled correctly
   - [ ] Test error propagation from modular operations
   - [ ] Validate configuration passing to sub-operations

3. **Behavior Validation**
   - [ ] Compare simulation results before/after refactoring
   - [ ] Validate identical YearResult objects
   - [ ] Test error scenarios produce same exceptions
   - [ ] Verify logging output character-for-character

### Integration Tests
1. **End-to-End Simulation**
   - [ ] Run complete single-year simulation
   - [ ] Compare workforce metrics with baseline
   - [ ] Validate event counts and distributions
   - [ ] Test with various configuration parameters

2. **Error Recovery**
   - [ ] Test behavior when individual steps fail
   - [ ] Validate error messages and logging
   - [ ] Test partial completion scenarios
   - [ ] Verify cleanup on exceptions

### Performance Tests
1. **Execution Time**
   - [ ] Benchmark before/after refactoring
   - [ ] Measure overhead of modular operations
   - [ ] Validate no significant performance regression
   - [ ] Test with large datasets

## Definition of Done

- [ ] run_year_simulation operation refactored and tested
- [ ] All repetitive dbt command blocks replaced with execute_dbt_command calls
- [ ] Event processing replaced with run_dbt_event_models_for_year operation
- [ ] Code reduction of 40%+ achieved (150+ lines removed)
- [ ] Unit tests written and passing (>95% coverage)
- [ ] Integration tests confirm identical behavior
- [ ] Performance benchmarking shows no regression
- [ ] All existing tests continue to pass without modification
- [ ] Code review completed and approved

## Dependencies

- **Upstream**:
  - S013-01 (dbt Command Utility) - required for execute_dbt_command
  - S013-03 (Event Processing) - required for run_dbt_event_models_for_year
- **Downstream**: S013-06 (Multi-Year Transformation) - will use refactored single-year op

## Risk Mitigation

1. **Behavior Changes**:
   - Extensive before/after testing with identical inputs
   - Character-by-character comparison of log output
   - Mathematical validation of simulation results

2. **Integration Complexity**:
   - Incremental refactoring approach
   - Test each modular component integration separately
   - Maintain rollback capability during development

3. **Performance Impact**:
   - Continuous benchmarking during development
   - Profile function call overhead
   - Optimize if significant regression detected

---

**Implementation Notes**: This is a critical refactoring that affects the core simulation logic. Start with comprehensive testing infrastructure before making changes. Consider implementing changes incrementally and validating each step.
