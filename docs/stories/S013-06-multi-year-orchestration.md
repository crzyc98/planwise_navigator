# Story S013-06: Multi-Year Orchestration Transformation

**Epic**: E013 - Dagster Simulation Pipeline Modularization
**Priority**: High
**Estimate**: 4 story points
**Status**: Not Started

## User Story

**As a** PlanWise Navigator developer
**I want** the run_multi_year_simulation operation transformed into a pure orchestrator
**So that** it focuses solely on coordination while leveraging refactored single-year simulation logic

## Background

The current `run_multi_year_simulation` operation is 325+ lines that duplicates significant logic from `run_year_simulation`. After the modular components are implemented, this operation should be transformed into a lean orchestrator (~50 lines) that:

- Calls `clean_duckdb_data` once at the start
- Manages the year-by-year loop
- Calls the refactored `run_year_simulation` for each year
- Handles baseline snapshots and year dependencies
- Aggregates results and provides summary logging

## Acceptance Criteria

### Functional Requirements
1. **Pure Orchestration Focus**
   - [ ] Remove all embedded simulation logic (lines 932-1026 duplicated from single-year)
   - [ ] Remove all repetitive dbt command execution blocks
   - [ ] Focus solely on year loop management and coordination
   - [ ] Maintain identical simulation results and behavior

2. **Modular Component Integration**
   - [ ] Use `clean_duckdb_data` operation for initial data cleaning
   - [ ] Call refactored `run_year_simulation` for each simulation year
   - [ ] Use `run_dbt_snapshot_for_year` for baseline snapshots
   - [ ] Leverage all new utility functions and operations

3. **Coordination Responsibilities**
   - [ ] Manage configuration for each year
   - [ ] Handle baseline snapshot creation for start_year - 1
   - [ ] Execute year-by-year validation and dependency checks
   - [ ] Aggregate YearResult objects and provide summary logging
   - [ ] Maintain error handling that allows continuation after year failures

### Technical Requirements
1. **Operation Signature** (unchanged)
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
def run_multi_year_simulation(
    context: OpExecutionContext, baseline_valid: bool
) -> List[YearResult]:
```

2. **Streamlined Implementation** (~50 lines)
   - [ ] Configuration setup and validation (5-10 lines)
   - [ ] Data cleaning call (1 line)
   - [ ] Baseline snapshot setup (3-5 lines)
   - [ ] Year loop with single-year simulation calls (20-25 lines)
   - [ ] Result aggregation and summary logging (10-15 lines)

3. **Preserved Functionality**
   - [ ] Identical error handling behavior (continue on year failure)
   - [ ] Same summary logging format and content
   - [ ] Maintained baseline snapshot creation logic
   - [ ] Preserved year dependency validation

## Implementation Details

### Current Code Analysis (325 lines)
**Lines to Remove/Refactor**:
- Lines 834-848: Data cleaning → Replace with `clean_duckdb_data()` call
- Lines 888-909: Previous year snapshot → Move to single-year or dedicated logic
- Lines 912-929: int_workforce_previous_year → Handled by single-year simulation
- Lines 932-1026: Event processing → Handled by single-year simulation
- Lines 1028-1046: fct_yearly_events → Handled by single-year simulation
- Lines 1048-1082: fct_workforce_snapshot → Handled by single-year simulation
- Lines 1085-1102: Current year snapshot → Handled by single-year or dedicated logic

**Lines to Keep**:
- Lines 819-831: Configuration setup and validation
- Lines 852-885: Year loop structure and validation calls
- Lines 1105-1137: Result aggregation and summary logging

### New Streamlined Implementation
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
def run_multi_year_simulation(
    context: OpExecutionContext, baseline_valid: bool
) -> List[YearResult]:
    """
    Executes complete multi-year workforce simulation.
    Pure orchestrator - delegates to modular components.
    """
    if not baseline_valid:
        raise Exception("Baseline workforce validation failed")

    config = context.op_config
    start_year = config["start_year"]
    end_year = config["end_year"]
    full_refresh = config.get("full_refresh", False)

    context.log.info(f"Starting multi-year simulation from {start_year} to {end_year}")
    if full_refresh:
        context.log.info(
            "🔄 Full refresh enabled - will rebuild all incremental models from scratch"
        )

    # Step 1: Clean all simulation data once
    years_to_clean = list(range(start_year, end_year + 1))
    cleaning_results = clean_duckdb_data(context, years_to_clean)
    context.log.info(f"Cleaned data for years {start_year}-{end_year}")

    # Step 2: Create baseline snapshot for year before simulation starts
    context.log.info(f"Creating baseline snapshot for year {start_year - 1}")
    run_dbt_snapshot_for_year(context, start_year - 1, "baseline", full_refresh)

    # Step 3: Execute simulation for each year
    results = []
    for year in range(start_year, end_year + 1):
        context.log.info(f"=== Starting simulation for year {year} ===")

        # Validate previous year completion (if not first year)
        if year > start_year:
            try:
                assert_year_complete(context, year - 1)
            except Exception as e:
                context.log.error(f"Simulation failed for year {year}: {e}")
                failed_result = YearResult(
                    year=year,
                    success=False,
                    active_employees=0,
                    total_terminations=0,
                    experienced_terminations=0,
                    new_hire_terminations=0,
                    total_hires=0,
                    growth_rate=0,
                    validation_passed=False,
                )
                results.append(failed_result)
                continue  # Skip to next year

        # Execute single year simulation
        try:
            # Prepare configuration for this specific year
            year_config = config.copy()
            year_config["start_year"] = year  # Override for single-year execution

            # Create temporary op execution context for single-year simulation
            year_result = run_year_simulation_with_config(context, year_config)
            results.append(year_result)

            context.log.info(f"=== Year {year} simulation completed successfully ===")

        except Exception as e:
            context.log.error(f"Simulation failed for year {year}: {e}")
            failed_result = YearResult(
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
            results.append(failed_result)
            continue  # Continue with next year

    # Step 4: Summary logging
    context.log.info("=== Multi-year simulation summary ===")
    for result in results:
        if result.success:
            context.log.info(
                f"Year {result.year}: {result.active_employees} employees, {result.growth_rate:.1%} growth"
            )
        else:
            context.log.error(f"Year {result.year}: FAILED")

    return results

def run_year_simulation_with_config(
    context: OpExecutionContext,
    year_config: Dict[str, Any]
) -> YearResult:
    """
    Wrapper to execute run_year_simulation with specific year configuration.
    This handles the context/config translation needed for modular execution.
    """
    # Create a temporary context that includes the year-specific config
    # Implementation will depend on Dagster patterns for dynamic op execution
    # This might require refactoring to use Dagster's op invocation patterns

    # For now, directly call the simulation logic with the config
    # (This may need adjustment based on Dagster's execution model)
    return run_year_simulation_core_logic(context, year_config)
```

### Alternative Implementation (Direct Logic Call)
If dynamic op execution proves complex, we can extract the core logic:

```python
# Step 3: Execute simulation for each year (alternative approach)
for year in range(start_year, end_year + 1):
    context.log.info(f"=== Starting simulation for year {year} ===")

    # Validate previous year completion
    if year > start_year:
        try:
            assert_year_complete(context, year - 1)
        except Exception as e:
            # ... error handling ...
            continue

    # Execute single year simulation by calling core logic directly
    try:
        year_result = _execute_single_year_simulation(context, year, config)
        results.append(year_result)
        context.log.info(f"=== Year {year} simulation completed successfully ===")
    except Exception as e:
        # ... error handling ...
        continue

def _execute_single_year_simulation(
    context: OpExecutionContext,
    year: int,
    config: Dict[str, Any]
) -> YearResult:
    """Execute the core single-year simulation logic."""
    # This would call the refactored run_year_simulation logic
    # but with direct parameter passing rather than op config
    year_config = config.copy()
    year_config["start_year"] = year

    # Call the core simulation logic that run_year_simulation uses
    return run_year_simulation_core(context, year_config)
```

### Code Reduction Analysis
**Before**: 325 lines
**After**: ~50 lines (85% reduction)

**Lines Eliminated**:
- Data cleaning logic: 14 lines → 2 lines (call to clean_duckdb_data)
- Event processing duplication: 94 lines → 0 lines (handled by single-year)
- dbt command repetition: 80+ lines → 0 lines (handled by utilities)
- Snapshot management: 35 lines → 3 lines (call to snapshot operation)

## Testing Requirements

### Unit Tests
1. **Orchestration Logic**
   - [ ] Test year loop execution with various year ranges
   - [ ] Test configuration passing to single-year simulations
   - [ ] Test error handling and continuation after year failures
   - [ ] Test baseline snapshot creation logic

2. **Integration Points**
   - [ ] Test clean_duckdb_data integration
   - [ ] Test run_year_simulation integration
   - [ ] Test run_dbt_snapshot_for_year integration
   - [ ] Test assert_year_complete validation calls

3. **Result Aggregation**
   - [ ] Test YearResult collection and summary generation
   - [ ] Test mixed success/failure scenario handling
   - [ ] Test summary logging format and content
   - [ ] Test return value structure and content

### Behavior Validation Tests
1. **End-to-End Comparison**
   - [ ] Run same multi-year simulation before/after refactoring
   - [ ] Compare all YearResult objects field-by-field
   - [ ] Validate identical workforce progression across years
   - [ ] Confirm identical event counts and distributions

2. **Error Scenario Testing**
   - [ ] Test behavior when individual years fail
   - [ ] Validate error messages and logging output
   - [ ] Test recovery and continuation logic
   - [ ] Verify no data corruption on partial failures

3. **Performance Validation**
   - [ ] Benchmark execution time before/after refactoring
   - [ ] Measure memory usage patterns
   - [ ] Validate no significant performance regression
   - [ ] Test with large year ranges (10+ years)

## Definition of Done

- [ ] run_multi_year_simulation transformed into 50-line orchestrator
- [ ] All duplicated simulation logic removed
- [ ] Integration with all modular components implemented
- [ ] 85%+ code reduction achieved (275+ lines eliminated)
- [ ] Unit tests written and passing (>95% coverage)
- [ ] Behavior validation tests confirm identical results
- [ ] Performance benchmarking shows no significant regression
- [ ] All existing integration tests continue to pass
- [ ] Code review completed and approved
- [ ] Documentation updated to reflect new architecture

## Dependencies

- **Upstream**:
  - S013-01 (dbt Command Utility)
  - S013-02 (Data Cleaning)
  - S013-03 (Event Processing)
  - S013-04 (Snapshot Management)
  - S013-05 (Single-Year Refactoring)
- **Downstream**: S013-07 (Validation & Testing)

## Risk Mitigation

1. **Complex Integration**:
   - Implement incrementally with rollback capability
   - Test each modular component integration separately
   - Maintain extensive before/after validation

2. **Op Execution Patterns**:
   - Research Dagster best practices for dynamic op execution
   - Consider alternative approaches if dynamic execution is complex
   - Validate with Dagster community/documentation

3. **Behavior Preservation**:
   - Comprehensive simulation result comparison
   - Character-by-character logging output validation
   - Mathematical verification of year-over-year calculations

---

**Implementation Notes**: This is the culmination of the modularization effort. The success of this story validates the entire refactoring approach. Focus on extensive testing and validation to ensure zero behavior changes while achieving maximum code reduction.
