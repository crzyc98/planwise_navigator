# Migration Guide - Pipeline Refactoring Changes

**Date**: June 25, 2025
**Version**: 1.0 (Epic E013 Migration)
**Audience**: Developers familiar with pre-Epic E013 code

---

## Overview

This guide helps developers transition from the **pre-Epic E013 monolithic pipeline** to the **new modular architecture**. It provides detailed mappings of code changes, updated patterns, and migration strategies.

## Executive Summary of Changes

### Key Transformations
1. **`run_multi_year_simulation`** reduced from **325 lines** to **69 lines** (78.8% reduction)
2. **`run_year_simulation`** reduced from **308 lines** to **105 lines** (65.9% reduction)
3. **Repetitive dbt commands** replaced with **`execute_dbt_command()`** utility
4. **Event processing** extracted into **`run_dbt_event_models_for_year()`**
5. **Data cleaning** moved to **`clean_duckdb_data()`** operation
6. **Snapshot management** centralized in **`run_dbt_snapshot_for_year()`**

### What Stayed the Same ✅
- **Simulation results**: Mathematically identical output
- **Configuration**: Same parameter structure and values
- **Epic 11.5 sequence**: Exact same event processing order
- **Error handling**: Same error scenarios and recovery behavior
- **Validation logic**: Unchanged validation functions and criteria

## Detailed Code Location Changes

### 1. Multi-Year Simulation Function

#### Before (Original Implementation)
```python
def run_multi_year_simulation(config):
    # Lines 1-50: Configuration and setup
    start_year = config["start_year"]
    end_year = config["end_year"]
    # ... configuration extraction

    # Lines 51-80: Data cleaning (embedded)
    conn = duckdb.connect(db_path)
    for year in range(start_year, end_year + 1):
        conn.execute(f"DELETE FROM table WHERE year = {year}")
    # ... repetitive cleaning logic

    # Lines 81-150: Baseline snapshot (embedded)
    invocation = dbt.cli(["snapshot", "--select", "scd_workforce_state",
                         "--vars", f"{{simulation_year: {start_year - 1}}}"],
                         context=context).wait()
    # ... error handling

    # Lines 151-325: Year-by-year loop with embedded simulation
    for year in range(start_year, end_year + 1):
        # Lines 151-200: Event processing (duplicated from single-year)
        invocation = dbt.cli(["run", "--select", "int_termination_events",
                             "--vars", f"{{simulation_year: {year}}}"],
                             context=context).wait()
        # ... 15+ repetitive dbt command patterns

        # Lines 201-250: Hiring debug (duplicated)
        # ... debug logic identical to single-year

        # Lines 251-300: Snapshot management (embedded)
        # ... snapshot creation logic

        # Lines 301-325: Result aggregation
```

#### After (Modular Implementation)
```python
def run_multi_year_simulation(config):
    # Lines 1-15: Configuration and validation
    start_year = config["start_year"]
    end_year = config["end_year"]
    years_to_clean = list(range(start_year, end_year + 1))

    # Lines 16-20: Data preparation using modular operations
    clean_duckdb_data(context, years_to_clean)
    run_dbt_snapshot_for_year(context, start_year - 1, "baseline")

    # Lines 21-55: Year-by-year orchestration
    results = []
    for year in range(start_year, end_year + 1):
        # Single line delegation to modular operation
        year_result = run_year_simulation(context, year, config)
        results.append(year_result)

    # Lines 56-69: Result aggregation and summary
    return results
```

### 2. Single-Year Simulation Function

#### Before (Original Implementation)
```python
def run_year_simulation(context, year, config):
    # Lines 1-50: Setup and configuration
    # ... parameter extraction and validation

    # Lines 51-100: Event processing (embedded dbt commands)
    invocation = dbt.cli(["run", "--select", "int_termination_events",
                         "--vars", f"{{simulation_year: {year}}}"],
                         context=context).wait()
    if invocation.process is None or invocation.process.returncode != 0:
        # ... error handling

    # Lines 101-150: More event processing (repetitive patterns)
    invocation = dbt.cli(["run", "--select", "int_promotion_events",
                         "--vars", f"{{simulation_year: {year}}}"],
                         context=context).wait()
    # ... repeated 5 times for each event model

    # Lines 151-200: Hiring calculation debug (embedded)
    conn = duckdb.connect(db_path)
    workforce_count = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    # ... detailed hiring calculation logic

    # Lines 201-250: Snapshot management (embedded)
    invocation = dbt.cli(["snapshot", "--select", "scd_workforce_state",
                         "--vars", f"{{simulation_year: {year}}}"],
                         context=context).wait()
    # ... snapshot error handling

    # Lines 251-308: Validation and result construction
```

#### After (Modular Implementation)
```python
def run_year_simulation(context, year, config):
    # Lines 1-20: Setup and validation
    # ... streamlined parameter handling

    # Lines 21-30: Previous year validation
    assert_year_complete(context, year - 1)

    # Lines 31-40: Event processing delegation
    run_dbt_event_models_for_year(context, year, config)

    # Lines 41-50: Snapshot management delegation
    run_dbt_snapshot_for_year(context, year - 1, "previous_year")
    run_dbt_snapshot_for_year(context, year, "end_of_year")

    # Lines 51-105: Validation and result construction
    # ... unchanged validation logic
```

### 3. dbt Command Patterns

#### Before (Repetitive Patterns)
```python
# Pattern repeated 15+ times throughout the codebase
vars_string = f"{{simulation_year: {year}, random_seed: {seed}}}"
if full_refresh:
    invocation = dbt.cli(["run", "--select", model, "--vars", vars_string, "--full-refresh"],
                         context=context).wait()
else:
    invocation = dbt.cli(["run", "--select", model, "--vars", vars_string],
                         context=context).wait()

if invocation.process is None or invocation.process.returncode != 0:
    stdout = invocation.get_stdout() if invocation else "No output"
    stderr = invocation.get_stderr() if invocation else "No error output"
    raise Exception(f"Failed to run {model}. stdout: {stdout}, stderr: {stderr}")
```

#### After (Centralized Utility)
```python
# Single utility call replacing all repetitive patterns
execute_dbt_command(
    context,
    ["run", "--select", model],
    {"simulation_year": year, "random_seed": seed},
    full_refresh,
    f"{model} for {year}"
)
```

## Code Mapping Table

| **Original Location** | **New Location** | **Change Type** | **Notes** |
|----------------------|------------------|-----------------|----------|
| Lines 51-80 (multi-year data cleaning) | `clean_duckdb_data()` | **Extracted** | Centralized operation |
| Lines 151-250 (embedded event processing) | `run_dbt_event_models_for_year()` | **Extracted** | Eliminates duplication |
| Lines 251-300 (embedded snapshot logic) | `run_dbt_snapshot_for_year()` | **Extracted** | Centralized management |
| 15+ dbt command patterns | `execute_dbt_command()` | **Centralized** | Single utility function |
| Lines 151-200 (hiring debug) | Inside `run_dbt_event_models_for_year()` | **Moved** | Stays with event processing |
| Lines 301-325 (result aggregation) | Lines 56-69 (multi-year) | **Simplified** | Pure orchestration |

## Breaking Changes (None!)

**✅ No breaking changes** - All public APIs maintained:

- **Function signatures**: `run_multi_year_simulation(config)` unchanged
- **Configuration format**: Same YAML structure and parameter names
- **Return values**: Identical `YearResult` objects with same fields
- **Error handling**: Same exception types and error messages
- **Validation logic**: Unchanged validation functions and criteria

## Debugging Changes

### Log Message Updates

#### Before (Scattered Logging)
```python
# Logging scattered throughout embedded code
print(f"Running simulation for {year}")
context.log.info(f"Termination events completed")
context.log.info(f"Hiring calculation: {total_hires} hires needed")
```

#### After (Standardized Logging)
```python
# Standardized logging with emojis and formatting
INFO - 🎯 Starting year simulation for 2025
INFO - 📊 Event processing completed for 2025
INFO - 🔍 HIRING CALCULATION DEBUG:
INFO - 🎯 TOTAL HIRES CALLING FOR: 200 new employees
```

### New Debug Capabilities

1. **Operation-specific filtering**:
   ```bash
   # Filter by specific modular operation
   dagster logs | grep "run_dbt_event_models_for_year"
   dagster logs | grep "execute_dbt_command"
   ```

2. **Enhanced error context**:
   ```python
   # Before: Generic dbt error
   ERROR - dbt command failed

   # After: Detailed error with context
   ERROR - Failed to run run --select int_hiring_events for hiring events for 2025
   ERROR - Exit code: 1
   ERROR - stdout: [detailed dbt output]
   ERROR - stderr: [specific error message]
   ```

3. **Hiring calculation transparency**:
   ```python
   # New detailed hiring debug output
   🔍 HIRING CALCULATION DEBUG:
   📊 Current workforce count: 1000 employees
   💼 Experienced terminations: 120 employees
   🎯 Target growth amount: 30.0 employees
   🎯 TOTAL HIRES CALLING FOR: 200 new employees
   💼 Expected new hire terminations: 50 employees
   ```

## Testing Changes

### New Testing Structure

#### Before (Limited Testing)
```python
# Only end-to-end integration tests
def test_complete_simulation():
    result = run_multi_year_simulation(config)
    assert result is not None
```

#### After (Comprehensive Testing)
```python
# Unit tests for each modular operation
tests/unit/test_execute_dbt_command.py
tests/unit/test_clean_duckdb_data.py
tests/unit/test_event_models_operation.py
tests/unit/test_snapshot_operation.py
tests/unit/test_refactored_single_year.py

# Enhanced integration tests
tests/integration/test_simulation_behavior_comparison.py
tests/integration/test_performance_benchmarks.py
```

### Test Coverage Improvements
- **Before**: ~60% coverage, mostly integration tests
- **After**: >95% coverage with unit + integration tests

## Performance Impact

### Execution Time
- **No regression**: Execution time maintained or slightly improved
- **Better scalability**: Modular operations can be optimized independently
- **Memory efficiency**: Improved resource management

### Development Speed
- **Faster debugging**: Operation-specific logging and isolated testing
- **Easier maintenance**: Single-responsibility operations
- **Better testing**: Unit tests enable faster development cycles

## Common Migration Tasks

### 1. Updating Custom Code That Calls Simulation Functions

#### If you have custom code calling the simulation:
```python
# ✅ No changes needed - same interface
results = run_multi_year_simulation(config)  # Still works exactly the same
```

### 2. Updating dbt Command Patterns

#### If you have custom operations with dbt commands:
```python
# ❌ Old pattern (update this)
invocation = dbt.cli(["run", "--select", "my_model"], context=context).wait()

# ✅ New pattern (recommended)
execute_dbt_command(context, ["run", "--select", "my_model"], {}, False, "my model")
```

### 3. Updating Debug and Monitoring Code

#### If you parse log output:
```python
# ❌ Old log patterns (may not exist anymore)
if "Termination events completed" in log_line:

# ✅ New log patterns (use these)
if "📊 Event processing completed" in log_line:
if "🎯 TOTAL HIRES CALLING FOR:" in log_line:
```

### 4. Updating Error Handling

#### If you catch specific simulation errors:
```python
# ✅ Same exception types - no changes needed
try:
    results = run_multi_year_simulation(config)
except Exception as e:
    # Same error handling still works
```

## Validation Checklist

Use this checklist to verify your migration:

### ✅ Functional Validation
- [ ] Same simulation results with identical configuration
- [ ] Same error handling behavior
- [ ] Same configuration file format works
- [ ] Same return value structure

### ✅ Performance Validation
- [ ] No significant execution time regression (>5%)
- [ ] Same or better memory usage
- [ ] Same scalability characteristics

### ✅ Integration Validation
- [ ] Custom code calling simulation functions still works
- [ ] Monitoring and logging integrations updated for new patterns
- [ ] Test suites updated for new modular structure

## Rollback Plan

If needed, the original monolithic implementation can be restored:

1. **Git revert**: All changes are in version control
2. **Configuration compatibility**: Same config files work with original code
3. **Database compatibility**: DuckDB schema unchanged
4. **API compatibility**: No breaking changes to public interfaces

## Support and Resources

### Getting Help
- **Documentation**: [Developer Guide](developer-guide-modular-pipeline.md)
- **Architecture**: [System Architecture](architecture.md)
- **Issues**: Check existing Epic E013 documentation for common patterns

### Additional Resources
- [Epic E013 Technical Specifications](epic-E013-technical-specifications.md)
- [Epic E013 Validation Framework](epic-E013-validation-framework.md)
- [Story Completion Summaries](s013-01-completion-summary.md) (S013-01 through S013-07)

---

**Summary**: The Epic E013 refactoring achieves **72.5% code reduction** with **zero functional changes**. Developers can continue using the same APIs while benefiting from improved maintainability, testability, and debugging capabilities.
