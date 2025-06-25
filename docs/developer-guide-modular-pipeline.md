# Developer Guide - Modular Simulation Pipeline

**Date**: June 25, 2025
**Version**: 1.0 (Post-Epic E013)
**Audience**: PlanWise Navigator developers

---

## Overview

This guide helps developers understand and work with the **modular simulation pipeline** introduced in Epic E013. The pipeline is built from single-responsibility operations that can be tested, modified, and composed independently.

## Quick Start

### Understanding the Modular Architecture

The simulation pipeline is now built from **6 modular operations**:

1. **`execute_dbt_command()`** - Centralized dbt command utility
2. **`clean_duckdb_data()`** - Data cleaning operation
3. **`run_dbt_event_models_for_year()`** - Event processing for one year
4. **`run_dbt_snapshot_for_year()`** - Snapshot management
5. **`run_year_simulation()`** - Single-year simulation orchestrator
6. **`run_multi_year_simulation()`** - Multi-year simulation orchestrator

Each operation handles one specific responsibility and can be used independently or composed together.

### Basic Usage Patterns

#### Running a Complete Simulation
```python
# Multi-year simulation (most common)
from orchestrator.simulator_pipeline import run_multi_year_simulation

config = {
    "start_year": 2024,
    "end_year": 2027,
    "target_growth_rate": 0.03,
    "random_seed": 42
}

results = run_multi_year_simulation(config)
```

#### Running a Single Year
```python
# Single-year simulation
from orchestrator.simulator_pipeline import run_year_simulation

year_config = {
    "simulation_year": 2025,
    "target_growth_rate": 0.03,
    "random_seed": 42,
    "full_refresh": False
}

result = run_year_simulation(context, year_config)
```

## Working with Modular Operations

### 1. Adding New dbt Commands

**Use the centralized utility instead of direct dbt.cli() calls:**

```python
# ❌ Old pattern (avoid)
invocation = dbt.cli(
    ["run", "--select", "my_model", "--vars", f"{{year: {year}}}"],
    context=context
).wait()
if invocation.process is None or invocation.process.returncode != 0:
    # error handling...

# ✅ New pattern (preferred)
from orchestrator.simulator_pipeline import execute_dbt_command

execute_dbt_command(
    context,
    ["run", "--select", "my_model"],
    {"year": year},
    full_refresh=False,
    description="my model execution"
)
```

**Benefits of using `execute_dbt_command()`:**
- Standardized error handling with detailed messages
- Consistent logging format
- Automatic variable string construction
- Built-in full_refresh flag handling

### 2. Modifying Event Processing

Event model logic is centralized in `run_dbt_event_models_for_year()`.

**To add new event models:**

```python
def run_dbt_event_models_for_year(context, year, config):
    # Add your new model to this list
    event_models = [
        "int_termination_events",
        "int_promotion_events",
        "int_merit_events",
        "int_hiring_events",
        "int_new_hire_termination_events",
        "int_your_new_event_model"  # Add here
    ]

    for model in event_models:
        execute_dbt_command(
            context,
            ["run", "--select", model],
            vars_dict,
            config.get("full_refresh", False),
            f"{model} for {year}"
        )
```

**Requirements for new event models:**
1. Must accept standard simulation variables (`simulation_year`, `random_seed`, etc.)
2. Should follow Epic 11.5 sequence requirements if order matters
3. Must be added to the event_models list in correct sequence position
4. Should include appropriate tests in the test suite

### 3. Working with Snapshots

Snapshot management is handled by `run_dbt_snapshot_for_year()`.

**Creating different snapshot types:**

```python
from orchestrator.simulator_pipeline import run_dbt_snapshot_for_year

# Baseline snapshot (before simulation)
run_dbt_snapshot_for_year(context, year - 1, "baseline")

# End-of-year snapshot (after simulation)
run_dbt_snapshot_for_year(context, year, "end_of_year")

# Recovery snapshot (for error handling)
run_dbt_snapshot_for_year(context, year, "recovery")
```

**Snapshot naming convention:**
- Snapshots are automatically named based on year and type
- Format: `scd_workforce_state_{year}_{type}`
- Example: `scd_workforce_state_2025_end_of_year`

### 4. Data Cleaning Operations

Use `clean_duckdb_data()` for data preparation:

```python
from orchestrator.simulator_pipeline import clean_duckdb_data

# Clean specific years
years_to_clean = [2024, 2025, 2026]
clean_duckdb_data(context, years_to_clean)

# Clean all simulation data
clean_duckdb_data(context, list(range(2020, 2030)))
```

## Debugging and Troubleshooting

### Operation-Specific Logging

Each modular operation logs its execution with distinct patterns:

```bash
# Filter logs by operation
dagster logs | grep "execute_dbt_command"
dagster logs | grep "run_dbt_event_models_for_year"
dagster logs | grep "run_dbt_snapshot_for_year"
```

### Debug Output Examples

**dbt Command Execution:**
```
INFO - 🔧 Executing dbt run --select int_hiring_events --vars {simulation_year: 2025, random_seed: 42}
INFO - 📊 dbt command completed successfully for hiring events for 2025
```

**Event Processing Debug:**
```
INFO - 🔍 HIRING CALCULATION DEBUG:
INFO - 📊 Current workforce count: 1000 employees
INFO - 🎯 TOTAL HIRES CALLING FOR: 200 new employees
INFO - 💼 Expected new hire terminations: 50 employees
```

**Snapshot Management:**
```
INFO - 📸 Creating snapshot: scd_workforce_state_2025_end_of_year
INFO - ✅ Snapshot created successfully with 1000 records
```

### Common Debugging Scenarios

#### 1. Hiring Calculations Not Working
**Check the hiring debug logs:**
```python
# Look for this in run_dbt_event_models_for_year logs
🔍 HIRING CALCULATION DEBUG:
📊 Current workforce count: [X] employees
🎯 Target growth amount: [Y] employees
🎯 TOTAL HIRES CALLING FOR: [Z] new employees
```

**Common issues:**
- Incorrect `target_growth_rate` in configuration
- Wrong `total_termination_rate` or `new_hire_termination_rate`
- Missing previous year workforce data

#### 2. Snapshot Errors
**Check snapshot prerequisites:**
```python
# Ensure previous year data exists
assert_year_complete(context, year - 1)

# Check workforce baseline
baseline_count = get_baseline_workforce_count(context)
assert baseline_count > 0
```

#### 3. dbt Command Failures
**Use the detailed error output from `execute_dbt_command()`:**
```
ERROR - Failed to run run --select my_model for my description
ERROR - Exit code: 1
ERROR - stdout: [dbt output]
ERROR - stderr: [dbt errors]
```

## Testing New Components

### Unit Testing Structure

Each modular operation has dedicated unit tests:

```python
# tests/unit/test_execute_dbt_command.py
def test_basic_command_execution():
    """Test basic dbt command with no variables."""
    # Test implementation...

def test_command_with_variables():
    """Test dbt command with variables dictionary."""
    # Test implementation...

def test_full_refresh_flag():
    """Test full_refresh flag addition."""
    # Test implementation...
```

### Integration Testing

Test complete simulation behavior:

```python
# tests/integration/test_simulation_behavior_comparison.py
def test_identical_simulation_results():
    """Verify refactored pipeline produces identical results."""
    # Compare before/after simulation results...

def test_multi_year_simulation_validation():
    """Test multi-year simulation with different configurations."""
    # End-to-end testing...
```

### Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific operation tests
pytest tests/unit/test_execute_dbt_command.py -v

# Run integration tests
pytest tests/integration/ -v

# Run with coverage
pytest tests/ --cov=orchestrator --cov-report=html
```

## Advanced Usage Patterns

### Custom Operation Composition

Create your own operations using the modular components:

```python
def run_custom_analysis(context, year, config):
    """Custom analysis using modular components."""

    # Clean data for specific analysis
    clean_duckdb_data(context, [year])

    # Run specific event models
    execute_dbt_command(
        context,
        ["run", "--select", "int_termination_events", "int_hiring_events"],
        {"simulation_year": year, "random_seed": config["random_seed"]},
        False,
        f"custom analysis for {year}"
    )

    # Create analysis snapshot
    run_dbt_snapshot_for_year(context, year, "analysis")
```

### Error Recovery Patterns

Handle partial failures gracefully:

```python
def robust_simulation_year(context, year, config):
    """Simulation with error recovery."""

    try:
        # Attempt normal simulation
        return run_year_simulation(context, year, config)

    except Exception as e:
        context.log.warning(f"Year {year} failed, attempting recovery: {e}")

        # Clean and retry
        clean_duckdb_data(context, [year])
        run_dbt_snapshot_for_year(context, year - 1, "recovery")

        # Retry with modified config
        recovery_config = config.copy()
        recovery_config["full_refresh"] = True
        return run_year_simulation(context, year, recovery_config)
```

### Performance Optimization

Optimize operations for specific use cases:

```python
def fast_simulation_run(context, config):
    """Optimized simulation for development/testing."""

    # Use smaller year range
    config = config.copy()
    config["end_year"] = min(config["end_year"], config["start_year"] + 2)

    # Enable full refresh for consistency
    config["full_refresh"] = True

    return run_multi_year_simulation(context, config)
```

## Configuration Management

### Standard Configuration Structure

```yaml
# config/simulation_config.yaml
simulation:
  start_year: 2024
  end_year: 2028
  target_growth_rate: 0.03
  random_seed: 42

workforce:
  total_termination_rate: 0.12
  new_hire_termination_rate: 0.25

database:
  path: "simulation.duckdb"
  memory_limit: "6GB"
  threads: 4

dbt:
  full_refresh: false
  target: "dev"
```

### Configuration Validation

All configurations are validated using Pydantic models:

```python
from config.config_manager import SimulationConfig

# Automatic validation
config = SimulationConfig.from_yaml("config/simulation_config.yaml")

# Access validated parameters
assert 2020 <= config.simulation.start_year <= 2050
assert 0.0 <= config.workforce.total_termination_rate <= 1.0
```

## Best Practices

### 1. Always Use Modular Operations
- **Don't**: Directly call `dbt.cli()` in new code
- **Do**: Use `execute_dbt_command()` for all dbt operations

### 2. Handle Errors Gracefully
- **Don't**: Let operations fail silently
- **Do**: Use try/catch blocks and log errors with context

### 3. Follow Logging Conventions
- **Don't**: Use plain `print()` statements
- **Do**: Use `context.log.info()` with descriptive emojis and formatting

### 4. Test Modular Components
- **Don't**: Only test end-to-end simulations
- **Do**: Write unit tests for each modular operation

### 5. Maintain Configuration Validation
- **Don't**: Use raw dictionaries for configuration
- **Do**: Use Pydantic models with validation rules

## Migration from Legacy Code

For developers working with pre-Epic E013 code, see the [Migration Guide](migration-guide-pipeline-refactoring.md) for detailed change mappings and refactoring patterns.

## Related Documentation

- [System Architecture](architecture.md)
- [Migration Guide](migration-guide-pipeline-refactoring.md)
- [Troubleshooting Guide](troubleshooting.md)
- [Epic E013 Technical Specifications](epic-E013-technical-specifications.md)
