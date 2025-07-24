# Multi-Year Simulation with Enhanced Data Persistence

This document provides comprehensive documentation for the PlanWise Navigator multi-year simulation system with enhanced data persistence capabilities, designed to prevent data loss and enable true multi-year workforce transitions.

## Overview

The enhanced multi-year simulation system prioritizes data persistence and continuity across simulation years. Key improvements include table-based materialization for event accumulation, selective data clearing, and enhanced validation with comprehensive fallback mechanisms.

## Core Improvements

### Data Persistence Architecture

**Table Materialization for Events:**
- `fct_yearly_events` uses table materialization instead of incremental
- Events accumulate across years instead of being replaced
- Enables true multi-year analysis and year-over-year transitions

**Enhanced Data Handoff:**
- `int_workforce_previous_year_v2` includes comprehensive validation metadata
- Data quality flags and fallback tracking
- Previous year availability checking with detailed logging

**Selective Data Management:**
- Preserve existing multi-year data by default
- Force clear mode for complete data refresh
- Selective year clearing for targeted reprocessing

### MultiYearSimulationOrchestrator Enhancements

The orchestrator now supports flexible data management modes:

**Data Preservation Mode (Default):**
- `preserve_data=True` keeps existing simulation data
- Enables incremental multi-year building
- Maintains workforce continuity between years

**Force Clear Mode:**
- `force_clear=True` clears all simulation data before starting
- Useful for complete simulation refresh
- Targeted to specific year ranges only

**Selective Operations:**
- Clear specific years with `clear_specific_years()`
- Rollback individual years with `rollback_year()`
- Data integrity validation with `validate_multi_year_data_integrity()`

## Sequential Year Execution Requirement

### Circular Dependency Resolution

**Problem Solved:**
The multi-year simulation system previously suffered from a circular dependency:
```
int_active_employees_by_year → int_workforce_previous_year_v2 → fct_workforce_snapshot → int_active_employees_by_year
```

This circular dependency prevented year 2026+ from running independently when year 2025 hadn't completed yet.

**Solution Implemented - Temporal Dependency Architecture:**
The circular dependency has been completely eliminated using two new helper models that create temporal dependencies (year N depends on year N-1) instead of circular dependencies within the same year:

#### 1. Primary Helper Model: `int_active_employees_prev_year_snapshot`
- **Purpose**: Provides active employee data from the previous year's completed workforce snapshot
- **Data Source**: Queries `fct_workforce_snapshot` for `simulation_year - 1` with `employment_status = 'active'`
- **Age/Tenure Progression**: Automatically increments age and tenure by 1 year for the current simulation year
- **Band Recalculation**: Recalculates `age_band` and `tenure_band` based on incremented demographics
- **Contract Compliance**: Includes all required fields expected by `fct_workforce_snapshot`
- **Data Quality**: Comprehensive validation with quality flags and error handling
- **Performance**: Table materialization with proper indexing on `employee_id` and `simulation_year`

#### 2. Secondary Helper Model: `int_active_employees_by_year`
- **Purpose**: Unified interface for active employees across all years
- **Logic**: 
  - For year 1 (start_year): Select from `int_baseline_workforce`
  - For subsequent years: Select from `int_active_employees_prev_year_snapshot`
- **Benefits**: Provides consistent schema and serves as abstraction layer for tests
- **Error Handling**: Includes fallback logic for missing previous year data

#### 3. Updated Workforce Snapshot Logic
- **Year 1**: Uses `int_baseline_workforce` directly (unchanged)
- **Subsequent Years**: Uses `int_active_employees_prev_year_snapshot` instead of the circular path
- **Dependencies**: Clean temporal dependency chain where year N depends only on year N-1 data
- **Performance**: Eliminates complex circular dependency resolution overhead

**Sequential Year Requirement:**
- **Years must be run in chronological order** (2025 → 2026 → 2027, etc.)
- Each year depends on the previous year's completed workforce snapshot
- The orchestrator now validates and enforces this sequential requirement
- Clear error messages guide users when dependency issues occur

### Enhanced Dependency Validation

**New Validation Methods:**
- `_validate_previous_year_snapshot()`: Ensures previous year's workforce snapshot exists and has valid data
- `_validate_helper_model_readiness()`: Confirms the helper model can access required previous year data
- `_validate_sequential_dependencies()`: Comprehensive validation of all previous year requirements

**Error Handling:**
- Clear error messages when years are run out of order
- Specific guidance on which previous year needs to be completed
- Validation warnings before execution to prevent partial failures
- Recovery instructions for dependency issues

### Troubleshooting Helper Models

**Helper Model Validation:**

1. **Verify Helper Model Data Exists**
   ```sql
   SELECT COUNT(*), MIN(current_age), MAX(current_age), 
          COUNT(DISTINCT age_band), COUNT(DISTINCT tenure_band)
   FROM int_active_employees_prev_year_snapshot
   WHERE simulation_year = <target_year>;
   ```

2. **Check Data Quality Flags**
   ```sql
   SELECT data_quality_valid, COUNT(*) 
   FROM int_active_employees_prev_year_snapshot
   WHERE simulation_year = <target_year>
   GROUP BY data_quality_valid;
   ```

3. **Validate Previous Year Dependency**
   ```sql
   SELECT COUNT(*) as active_employees
   FROM fct_workforce_snapshot
   WHERE simulation_year = <target_year - 1> 
     AND employment_status = 'active';
   ```

**Common Helper Model Issues:**

1. **"No workforce snapshot found for year YYYY"**
   - **Cause**: Attempting to run year YYYY+1 before year YYYY is complete
   - **Solution**: Complete year YYYY first before running year YYYY+1

2. **"Helper model produced no data"**
   - **Cause**: Previous year's workforce snapshot has no active employees or failed data quality validation
   - **Solution**: Check previous year simulation results and data quality flags
   - **Validation**: Verify `data_quality_valid = true` in the helper model output

3. **"Age/tenure progression validation failed"**
   - **Cause**: Helper model age/tenure incrementation logic produced invalid values
   - **Solution**: Check that previous year data has realistic age and tenure values
   - **Debug**: Review `current_age + 1` and `current_tenure + 1` calculations

4. **"Multi-year simulations must be run sequentially"**
   - **Cause**: Attempting to skip years or run years out of order
   - **Solution**: Run years in chronological order starting from the first incomplete year

**Performance Considerations:**

- Helper models use table materialization for optimal performance
- Proper indexing on `employee_id` and `simulation_year` ensures fast lookups
- Data quality validation filters are applied early to reduce processing overhead
- Large datasets may require additional memory allocation for table materialization

**Recovery Procedures:**

1. **Identify Missing Years**: Check which years have completed successfully
2. **Clear Incomplete Years**: Use selective clearing to remove partial year data
3. **Sequential Execution**: Restart from the first missing year and proceed chronologically
4. **Validate Dependencies**: Ensure each year's workforce snapshot is valid before proceeding

**Best Practices for Multi-Year Execution:**

- Always run simulations in chronological order
- Validate each year's completion before proceeding to the next
- Use the orchestrator's built-in validation to check dependencies
- Monitor helper model data quality flags for troubleshooting
- Keep previous year data intact until subsequent years complete successfully

## Required Workflow Steps

The checklist enforces a 7-step workflow that must be executed for each simulation year:

### Pre-Simulation Setup (Year-Independent)

**Step:** `pre_simulation`
**Prerequisites:** None
**Description:** Database clearing and preparation, seed data loading, baseline workforce validation

**Tasks:**
- Clear existing simulation data from database
- Load configuration seed data (job levels, compensation levers, hazard configurations)
- Validate baseline workforce exists and is accessible
- Ensure all required staging tables are prepared

### For Each Simulation Year (2025-2029)

#### 1. Year Transition Validation

**Step:** `year_transition`
**Prerequisites:** `pre_simulation` (and previous year completion for years > start year)
**Description:** Verify previous year data exists and is valid for proper year transition calculations

**Tasks:**
- Validate previous year's workforce snapshot exists (skip for first year)
- Check data quality and consistency from previous year
- Ensure proper handoff of workforce state between years
- Validate event continuity across year boundaries

#### 2. Workforce Baseline Preparation

**Step:** `workforce_baseline`
**Prerequisites:** `year_transition`
**Description:** Use `int_baseline_workforce` for 2025, `int_workforce_previous_year_v2` for subsequent years

**Tasks:**
- For year 2025: Execute `int_baseline_workforce` dbt model
- For subsequent years: Execute `int_workforce_previous_year_v2` dbt model
- Validate workforce counts are reasonable and consistent
- Store workforce count for subsequent step calculations

#### 3. Workforce Requirements Calculation

**Step:** `workforce_requirements`
**Prerequisites:** `workforce_baseline`
**Description:** Calculate terminations and hires needed for growth targets

**Tasks:**
- Retrieve starting workforce count from previous step
- Apply growth rate, termination rate, and new hire termination rate from configuration
- Calculate experienced terminations needed
- Calculate gross hires needed to achieve target growth
- Calculate expected new hire terminations
- Validate calculation inputs and warn about extreme values

#### 4. Event Generation Pipeline

**Step:** `event_generation`
**Prerequisites:** `workforce_requirements`
**Description:** Generate all 5 event types in sequence and store in `fct_yearly_events`

**Tasks:**
- Generate experienced termination events by sampling from active workforce
- Generate new hire events with realistic demographic and compensation distributions
- Generate new hire termination events based on new hire termination rate
- Generate merit raise events for eligible employees (1+ years tenure)
- Generate promotion events using hazard-based probabilities
- Store all events in `fct_yearly_events` table with proper sequencing

#### 5. Workforce Snapshot Generation

**Step:** `workforce_snapshot`
**Prerequisites:** `event_generation`
**Description:** Run `fct_workforce_snapshot` dbt model with correct year parameter

**Tasks:**
- Execute `fct_workforce_snapshot` dbt model for the simulation year
- Apply all events from `fct_yearly_events` to workforce state
- Calculate final workforce demographics and compensation
- Validate snapshot data quality and completeness

#### 6. Validation & Metrics

**Step:** `validation_metrics`
**Prerequisites:** `workforce_snapshot`
**Description:** Validate results and calculate metrics

**Tasks:**
- Validate workforce continuity between years
- Check data quality flags and completeness
- Verify growth metrics align with targets (within reasonable variance)
- Calculate and log key performance indicators
- Generate validation reports and summaries

## Usage Examples

### Data Persistence Modes

```bash
# Default: Preserve existing multi-year data (recommended)
python -m orchestrator_mvp.run_mvp --multi-year --preserve-data

# Force clear all simulation data before starting
python -m orchestrator_mvp.run_mvp --multi-year --force-clear

# Clear data for specific year only
python -m orchestrator_mvp.run_mvp --multi-year --reset-year 2026
```

### Data Validation and Integrity

```bash
# Validate data integrity before starting simulation
python -m orchestrator_mvp.run_mvp --multi-year --validate-data

# Check prerequisites without executing simulation
python -m orchestrator_mvp.run_mvp --multi-year --validate-only
```

### Standard Multi-Year Simulation

```bash
# Run with data preservation (default behavior)
python -m orchestrator_mvp.run_mvp --multi-year

# Non-interactive mode with data preservation
python -m orchestrator_mvp.run_mvp --multi-year --no-breaks --preserve-data
```

### Resume and Recovery

```bash
# Resume multi-year simulation from specific year
python -m orchestrator_mvp.run_mvp --multi-year --resume-from 2027

# Resume with existing data preserved
python -m orchestrator_mvp.run_mvp --multi-year --resume-from 2027 --preserve-data
```

## Error Scenarios and Troubleshooting

### Common Step Sequence Errors

#### Attempting to Run fct_workforce_snapshot Without Events

**Error Message:**
```
❌ Cannot execute step 'workforce_snapshot' for year 2025.
Missing prerequisites: event_generation (year 2025).
Please complete these steps first before proceeding.
```

**Solution:**
1. First run event generation: Complete workforce requirements calculation step
2. Then run event generation pipeline to populate `fct_yearly_events`
3. Finally run workforce snapshot generation

#### Attempting to Skip Workforce Requirements

**Error Message:**
```
❌ Cannot execute step 'event_generation' for year 2025.
Missing prerequisites: workforce_requirements (year 2025).
Please complete these steps first before proceeding.
```

**Solution:**
1. Complete workforce baseline preparation step
2. Run workforce requirements calculation
3. Then proceed with event generation

#### Starting Year 2 Without Completing Year 1

**Error Message:**
```
❌ Cannot execute step 'year_transition' for year 2026.
Missing prerequisites: Complete all steps for year 2025.
Please complete these steps first before proceeding.
```

**Solution:**
1. Complete all 6 steps for year 2025
2. Verify year 2025 workforce snapshot exists
3. Then begin year 2026 simulation

### Data Persistence Recovery Procedures

#### Multi-Year Data Loss Issues

If multi-year data continuity is lost:

1. **Check Data Integrity:**
   ```bash
   python -m orchestrator_mvp.run_mvp --multi-year --validate-data
   ```

2. **Selective Year Recovery:**
   ```bash
   # Clear and regenerate specific problematic year
   python -m orchestrator_mvp.run_mvp --multi-year --reset-year 2026
   ```

3. **Full Data Refresh (Last Resort):**
   ```bash
   # Only if data corruption is extensive
   python -m orchestrator_mvp.run_mvp --multi-year --force-clear
   ```

#### Year-to-Year Transition Failures

If workforce transitions between years fail:

1. **Enhanced Validation Check:**
   - The system now provides detailed diagnostics for transition failures
   - Check for missing previous year snapshots or data quality issues

2. **Fallback to Baseline Handling:**
   - The system automatically falls back to baseline when previous year data is missing
   - Monitor warnings about fallback usage in logs

3. **Data Quality Diagnostics:**
   - Enhanced logging shows data source (previous_year vs baseline_fallback)
   - Review data_quality_flag and validation_flag columns for troubleshooting

#### Missing Prerequisites

If checklist validation fails due to missing data:

1. **Identify Missing Components:** Check the error message for specific prerequisites
2. **Verify Database State:** Ensure required tables exist and have data
3. **Re-run Setup Steps:** May need to re-run `pre_simulation` setup
4. **Check Configuration:** Verify `test_config.yaml` has correct parameters

### Manual Override Procedures

**⚠️ WARNING:** Manual overrides should only be used in emergency situations as they bypass important safety checks.

#### Force Step Execution

```bash
# Force a specific step (with warning)
python -m orchestrator_mvp.run_mvp --force-step <STEP_NAME>
```

**Valid Step Names:**
- `pre_simulation`
- `year_transition`
- `workforce_baseline`
- `workforce_requirements`
- `event_generation`
- `workforce_snapshot`
- `validation_metrics`

#### Direct Database Access

For advanced troubleshooting, you can query the database directly:

```python
from orchestrator_mvp.core import get_connection

conn = get_connection()
try:
    # Check simulation progress
    result = conn.execute("""
        SELECT simulation_year, COUNT(*) as event_count
        FROM fct_yearly_events
        GROUP BY simulation_year
        ORDER BY simulation_year
    """).fetchall()
    print("Events by year:", result)

    # Check workforce snapshots
    result = conn.execute("""
        SELECT simulation_year,
               COUNT(*) as total_employees,
               COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees
        FROM fct_workforce_snapshot
        GROUP BY simulation_year
        ORDER BY simulation_year
    """).fetchall()
    print("Workforce by year:", result)

finally:
    conn.close()
```

## Technical Details

### Step Dependency Mapping

The checklist enforces these dependencies:

```python
STEP_DEPENDENCIES = {
    SimulationStep.PRE_SIMULATION: [],
    SimulationStep.YEAR_TRANSITION: [SimulationStep.PRE_SIMULATION],
    SimulationStep.WORKFORCE_BASELINE: [SimulationStep.YEAR_TRANSITION],
    SimulationStep.WORKFORCE_REQUIREMENTS: [SimulationStep.WORKFORCE_BASELINE],
    SimulationStep.EVENT_GENERATION: [SimulationStep.WORKFORCE_REQUIREMENTS],
    SimulationStep.WORKFORCE_SNAPSHOT: [SimulationStep.EVENT_GENERATION],
    SimulationStep.VALIDATION_METRICS: [SimulationStep.WORKFORCE_SNAPSHOT],
}
```

### State Tracking

Completion state is tracked using keys like `{year}.{step_name}`:
- `pre_simulation` (year-independent)
- `2025.year_transition`
- `2025.workforce_baseline`
- `2025.workforce_requirements`
- `2025.event_generation`
- `2025.workforce_snapshot`
- `2025.validation_metrics`

### Integration with Existing Models

The checklist system integrates seamlessly with existing dbt models:

- **int_baseline_workforce**: Used for year 2025 workforce baseline
- **int_workforce_previous_year_v2**: Used for subsequent years' workforce baseline
- **fct_yearly_events**: Target table for event generation pipeline
- **fct_workforce_snapshot**: Final output table for workforce state

### Performance Considerations

- **Checklist Overhead:** Minimal performance impact (~1-5ms per validation)
- **State Storage:** In-memory tracking with optional database persistence
- **Resume Capability:** Fast restart from any completed checkpoint
- **Validation Caching:** Efficient prerequisite checking

## Migration Guide

### From Legacy Multi-Year Simulation

The new checklist system is backward compatible:

1. **Existing Functionality:** All existing features remain available
2. **Enhanced Safety:** Added step sequencing prevents common errors
3. **Better Error Messages:** Clear guidance when steps are attempted out of order
4. **Resume Capability:** New ability to restart from interruptions

### Configuration Changes

No changes required to existing configuration files:
- `config/test_config.yaml` works unchanged
- All existing parameters and settings preserved
- New checklist features are opt-in via command line flags

### API Compatibility

The new `MultiYearSimulationOrchestrator` maintains the same interface as the legacy `run_multi_year_simulation()` function for backward compatibility.

## Best Practices

1. **Always Use Checklist Mode:** Unless debugging specific issues, use the checklist-enforced orchestrator
2. **Monitor Progress:** Check progress summaries during long simulations
3. **Validate Before Long Runs:** Use `--validate-only` to check prerequisites
4. **Use Resume Capability:** Don't restart entire simulations after failures
5. **Save Intermediate Results:** Let the checklist track progress automatically
6. **Review Error Messages:** They provide specific guidance on missing prerequisites
7. **Avoid Force Mode:** Only use `--force-step` in genuine emergency situations

## Integration with Existing Tools

### dbt Integration

The checklist system works seamlessly with existing dbt models:
- Validates that required models are available before execution
- Ensures proper parameter passing to dbt models
- Integrates with existing dbt test and validation framework

### Streamlit Dashboard Compatibility

Existing Streamlit dashboards continue to work:
- Checklist data is available for dashboard consumption
- Progress tracking can be integrated into dashboard views
- Resume functionality works with dashboard-driven workflows

### Database Tools

All existing database tools and queries remain functional:
- DuckDB database structure unchanged
- Existing table schemas preserved
- Additional checklist metadata available for advanced users
