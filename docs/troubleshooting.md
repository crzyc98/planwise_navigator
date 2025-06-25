# Troubleshooting Guide - Modular Simulation Pipeline

**Date**: June 25, 2025
**Version**: 1.0 (Post-Epic E013)
**Audience**: Developers and operations teams

---

## Overview

This guide provides troubleshooting procedures for the **modular simulation pipeline** introduced in Epic E013. Issues are organized by component to enable targeted debugging.

## General Debugging Approach

### 1. Identify the Component
The modular pipeline has **6 main components**. Identify which component is failing:

- **`execute_dbt_command()`** - dbt command execution issues
- **`clean_duckdb_data()`** - data cleaning problems
- **`run_dbt_event_models_for_year()`** - event processing failures
- **`run_dbt_snapshot_for_year()`** - snapshot management errors
- **`run_year_simulation()`** - single-year simulation issues
- **`run_multi_year_simulation()`** - multi-year orchestration problems

### 2. Check Component-Specific Logs
Each component has distinct logging patterns:

```bash
# Filter logs by component
dagster logs | grep "execute_dbt_command"
dagster logs | grep "run_dbt_event_models_for_year"
dagster logs | grep "run_dbt_snapshot_for_year"
dagster logs | grep "🔍 HIRING CALCULATION"
dagster logs | grep "📸 Creating snapshot"
```

### 3. Use Isolation Testing
Test individual components separately:

```python
# Test individual operations
execute_dbt_command(context, ["run", "--select", "int_baseline_workforce"], {}, False, "test")
clean_duckdb_data(context, [2025])
run_dbt_event_models_for_year(context, 2025, test_config)
```

## Component-Specific Troubleshooting

### 1. dbt Command Execution (`execute_dbt_command`)

#### Common Error: "Failed to run [command] for [description]"

**Symptoms:**
```
ERROR - Failed to run run --select int_hiring_events for hiring events for 2025
ERROR - Exit code: 1
ERROR - stdout: [dbt output]
ERROR - stderr: [dbt compilation error]
```

**Diagnosis Steps:**
1. **Check dbt model syntax**:
   ```bash
   cd dbt
   dbt compile --select int_hiring_events
   ```

2. **Verify variable passing**:
   ```python
   # Check if variables are correctly formatted
   vars_dict = {"simulation_year": 2025, "random_seed": 42}
   # Should produce: {simulation_year: 2025, random_seed: 42}
   ```

3. **Test model independently**:
   ```bash
   cd dbt
   dbt run --select int_hiring_events --vars '{simulation_year: 2025}'
   ```

**Common Fixes:**
- **SQL syntax errors**: Fix model SQL in `/dbt/models/`
- **Missing variables**: Add required variables to function call
- **Model dependencies**: Ensure upstream models exist and are built
- **Database connectivity**: Check DuckDB file path and permissions

#### Error: "Variables dictionary format incorrect"

**Symptoms:**
```python
# Incorrect variable string format in logs
--vars "{simulation_year: 2025, random_seed: 42}"  # Missing quotes around values
```

**Fix:**
```python
# Ensure variables are properly typed
vars_dict = {
    "simulation_year": 2025,        # int, not string
    "random_seed": 42,              # int, not string
    "target_growth_rate": 0.03      # float, not string
}
```

### 2. Data Cleaning (`clean_duckdb_data`)

#### Error: "Table does not exist during cleanup"

**Symptoms:**
```
ERROR - Failed to clean data for year 2025
ERROR - Table 'int_hiring_events' does not exist
```

**Diagnosis:**
```sql
-- Check which tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'main';
```

**Fixes:**
- **First-time setup**: Run `dbt run` to create initial tables
- **Partial cleanup**: Specify only years with existing data
- **Ignore missing tables**: Modify cleanup to handle missing tables gracefully

#### Error: "Database locked during cleanup"

**Symptoms:**
```
ERROR - database is locked
ERROR - Failed to acquire exclusive lock
```

**Fixes:**
1. **Check active connections**:
   ```bash
   # Ensure no other processes are using the database
   lsof simulation.duckdb
   ```

2. **Restart Dagster**:
   ```bash
   # Stop and restart Dagster to clear connections
   dagster dev --stop
   dagster dev
   ```

3. **Use transaction safety**:
   ```python
   # Ensure cleanup uses proper transaction handling
   with duckdb.connect(db_path) as conn:
       conn.execute("BEGIN TRANSACTION")
       # cleanup operations
       conn.execute("COMMIT")
   ```

### 3. Event Processing (`run_dbt_event_models_for_year`)

#### Error: "Hiring calculation produces zero hires"

**Symptoms:**
```
🔍 HIRING CALCULATION DEBUG:
📊 Current workforce count: 1000 employees
🎯 TOTAL HIRES CALLING FOR: 0 new employees  # Should not be 0
```

**Diagnosis Steps:**
1. **Check workforce baseline**:
   ```sql
   SELECT COUNT(*) FROM int_baseline_workforce;
   -- Should return > 0
   ```

2. **Verify termination calculations**:
   ```sql
   SELECT
       COUNT(*) as total_workforce,
       SUM(CASE WHEN termination_flag = 1 THEN 1 ELSE 0 END) as terminations
   FROM int_termination_events
   WHERE simulation_year = 2025;
   ```

3. **Check configuration parameters**:
   ```python
   # Verify rates are reasonable
   assert 0.0 <= config["total_termination_rate"] <= 1.0
   assert 0.0 <= config["target_growth_rate"] <= 1.0
   assert 0.0 <= config["new_hire_termination_rate"] <= 1.0
   ```

**Common Fixes:**
- **Configuration error**: Check `target_growth_rate` > 0
- **Missing baseline**: Ensure baseline workforce exists
- **Termination rate too high**: Check if `total_termination_rate` > `target_growth_rate`

#### Error: "Event models run out of sequence"

**Symptoms:**
```
ERROR - Table 'int_termination_events' referenced before creation
ERROR - Model dependencies not satisfied
```

**Fix:**
```python
# Ensure correct Epic 11.5 sequence in run_dbt_event_models_for_year
event_models = [
    "int_termination_events",      # Must be first
    "int_promotion_events",        # Depends on terminations
    "int_merit_events",           # Depends on promotions
    "int_hiring_events",          # Depends on all above
    "int_new_hire_termination_events"  # Must be last
]
```

### 4. Snapshot Management (`run_dbt_snapshot_for_year`)

#### Error: "Snapshot prerequisites not met"

**Symptoms:**
```
ERROR - Cannot create snapshot for year 2025
ERROR - Previous year workforce data not found
```

**Diagnosis:**
```sql
-- Check if previous year data exists
SELECT COUNT(*) FROM fct_workforce_snapshot
WHERE simulation_year = 2024;

-- Check baseline workforce
SELECT COUNT(*) FROM int_baseline_workforce;
```

**Fixes:**
1. **Create baseline snapshot**:
   ```python
   run_dbt_snapshot_for_year(context, start_year - 1, "baseline")
   ```

2. **Run previous year simulation**:
   ```python
   run_year_simulation(context, year - 1, config)
   ```

3. **Skip snapshot validation** (if appropriate):
   ```python
   # Modify snapshot operation to handle missing prerequisites
   ```

#### Error: "Snapshot table conflicts"

**Symptoms:**
```
ERROR - Snapshot table already exists with different structure
ERROR - Schema mismatch in scd_workforce_state
```

**Fixes:**
1. **Drop and recreate snapshot**:
   ```sql
   DROP TABLE IF EXISTS scd_workforce_state;
   ```

2. **Use fresh snapshot**:
   ```bash
   cd dbt
   dbt snapshot --full-refresh --select scd_workforce_state
   ```

### 5. Single-Year Simulation (`run_year_simulation`)

#### Error: "Year validation failed"

**Symptoms:**
```
ERROR - Year 2025 simulation failed validation
ERROR - AssertionError: Previous year data not complete
```

**Diagnosis:**
```python
# Check what assert_year_complete is validating
def debug_year_completeness(year):
    # Check workforce snapshot exists
    # Check event processing completed
    # Check validation criteria met
```

**Fixes:**
1. **Complete previous year**:
   ```python
   run_year_simulation(context, year - 1, config)
   ```

2. **Force baseline creation**:
   ```python
   run_dbt_snapshot_for_year(context, year - 1, "baseline")
   ```

#### Error: "YearResult construction failed"

**Symptoms:**
```
ERROR - Failed to construct YearResult for year 2025
ERROR - Missing required fields: active_employees
```

**Diagnosis:**
```sql
-- Check if final tables exist and have data
SELECT * FROM fct_workforce_snapshot WHERE simulation_year = 2025;
SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = 2025;
```

**Fix:**
```python
# Ensure all event processing completed before YearResult construction
# Check that workforce snapshot model ran successfully
```

### 6. Multi-Year Simulation (`run_multi_year_simulation`)

#### Error: "Multi-year orchestration stopped early"

**Symptoms:**
```
INFO - Year 2025 completed successfully
ERROR - Year 2026 failed, stopping simulation
ERROR - Failed to process year 2026 in multi-year sequence
```

**Diagnosis:**
```python
# Check which specific operation failed in year 2026
# Look for the last successful log message
# Identify if it's event processing, snapshot, or validation
```

**Fixes:**
1. **Continue on failure** (if appropriate):
   ```python
   # Modify multi-year to continue processing remaining years
   try:
       year_result = run_year_simulation(context, year, config)
   except Exception as e:
       context.log.warning(f"Year {year} failed: {e}")
       year_result = YearResult.failed(year, str(e))
   ```

2. **Fix underlying issue**: Use single-year troubleshooting for the failing year

#### Error: "Data cleaning failed for multi-year range"

**Symptoms:**
```
ERROR - Failed to clean years [2024, 2025, 2026, 2027]
ERROR - Some tables do not exist for specified years
```

**Fix:**
```python
# Make data cleaning more resilient
def safe_clean_duckdb_data(context, years):
    for year in years:
        try:
            # Clean individual year
            clean_year_data(context, year)
        except Exception as e:
            context.log.warning(f"Could not clean year {year}: {e}")
            # Continue with other years
```

## Configuration-Related Issues

### Error: "Configuration validation failed"

**Symptoms:**
```
ERROR - ValidationError: start_year must be between 2020 and 2050
ERROR - Configuration parameter out of valid range
```

**Fixes:**
1. **Check configuration file**:
   ```yaml
   # config/simulation_config.yaml
   simulation:
     start_year: 2024      # Must be 2020-2050
     end_year: 2028        # Must be >= start_year
     target_growth_rate: 0.03  # Must be 0.0-1.0
   ```

2. **Validate configuration programmatically**:
   ```python
   from config.config_manager import SimulationConfig
   config = SimulationConfig.from_yaml("config/simulation_config.yaml")
   # Will raise ValidationError if invalid
   ```

## Database-Related Issues

### Error: "DuckDB serialization error"

**Symptoms:**
```
ERROR - Object of type DuckDBPyRelation is not JSON serializable
ERROR - Dagster cannot serialize DuckDB objects
```

**Fix:**
```python
# ✅ Always convert to pandas DataFrame
@asset
def workforce_asset(context, duckdb_resource):
    with duckdb_resource.get_connection() as conn:
        # Convert immediately to serializable format
        df = conn.execute("SELECT * FROM table").df()
        return df  # Safe to return

# ❌ Never return DuckDB objects
@asset
def broken_asset():
    conn = duckdb.connect("db.duckdb")
    return conn.table("employees")  # NOT SERIALIZABLE!
```

### Error: "Database file corruption"

**Symptoms:**
```
ERROR - database disk image is malformed
ERROR - I/O error reading database
```

**Fixes:**
1. **Backup and restore**:
   ```bash
   # Create backup
   cp simulation.duckdb simulation_backup.duckdb

   # Export/import to new file
   duckdb simulation.duckdb "EXPORT DATABASE 'backup_dir'"
   duckdb new_simulation.duckdb "IMPORT DATABASE 'backup_dir'"
   ```

2. **Start fresh**:
   ```bash
   # Remove corrupted database
   rm simulation.duckdb

   # Rebuild from scratch
   dbt run --full-refresh
   ```

## Performance Issues

### Issue: "Simulation running slowly"

**Diagnosis:**
```python
# Add timing to identify bottlenecks
import time

start_time = time.time()
run_dbt_event_models_for_year(context, year, config)
event_time = time.time() - start_time

start_time = time.time()
run_dbt_snapshot_for_year(context, year, "end_of_year")
snapshot_time = time.time() - start_time

context.log.info(f"Event processing: {event_time:.2f}s")
context.log.info(f"Snapshot creation: {snapshot_time:.2f}s")
```

**Optimizations:**
1. **DuckDB settings**:
   ```python
   # Increase memory and threads
   conn.execute("SET memory_limit = '8GB'")
   conn.execute("SET threads = 8")
   ```

2. **Reduce data scope**:
   ```python
   # Test with smaller year ranges
   config["end_year"] = config["start_year"] + 2
   ```

3. **Use incremental models**:
   ```bash
   # Avoid full-refresh when possible
   dbt run --select model_name  # Instead of --full-refresh
   ```

## Getting Additional Help

### Log Analysis
```bash
# Collect comprehensive logs
dagster logs --verbose > simulation_debug.log

# Filter specific errors
grep -i error simulation_debug.log
grep "Failed to" simulation_debug.log
```

### Database Inspection
```sql
-- Check database state
SELECT table_name, row_count
FROM (
    SELECT table_name, COUNT(*) as row_count
    FROM information_schema.tables t
    JOIN table_name ON true  -- This would need proper join
) ORDER BY table_name;

-- Check simulation progress
SELECT simulation_year, COUNT(*) as records
FROM fct_workforce_snapshot
GROUP BY simulation_year
ORDER BY simulation_year;
```

### Validation Scripts
```bash
# Run Epic E013 validation
python validate_epic_e013_comprehensive.py

# Run individual story validations
python validate_s013_01.py  # dbt command utility
python validate_s013_06.py  # Multi-year orchestration
```

## Emergency Procedures

### Complete Reset
```bash
# 1. Stop all processes
dagster dev --stop

# 2. Clean database
rm simulation.duckdb

# 3. Reset configuration
git checkout config/simulation_config.yaml

# 4. Rebuild from scratch
dbt run --full-refresh
dagster dev
```

### Partial Recovery
```python
# Resume from specific year
config = {
    "start_year": 2026,  # Start from failed year
    "end_year": 2028,
    # ... other config
}

# Create recovery snapshot for previous year
run_dbt_snapshot_for_year(context, 2025, "recovery")

# Continue simulation
results = run_multi_year_simulation(config)
```

---

**Quick Reference**: For immediate help, check logs first (`dagster logs`), identify the failing component, and use the component-specific troubleshooting section above.
