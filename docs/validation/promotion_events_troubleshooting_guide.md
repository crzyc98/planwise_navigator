# Promotion Events Troubleshooting Guide

This guide helps diagnose and resolve common issues with promotion event generation in the PlanWise Navigator MVP orchestrator.

## Table of Contents
1. [Overview](#overview)
2. [Common Issues and Solutions](#common-issues-and-solutions)
3. [Diagnostic Steps](#diagnostic-steps)
4. [Configuration Validation](#configuration-validation)
5. [Performance Optimization](#performance-optimization)
6. [Advanced Debugging](#advanced-debugging)

## Overview

The promotion event system uses hazard-based probability calculations to determine which employees receive promotions. This guide covers troubleshooting steps when promotion events are not generated as expected.

## Common Issues and Solutions

### Issue 1: No Promotion Events Generated (Count = 0)

**Symptoms:**
- `promotion_count` is 0 in simulation output
- No promotion events in `fct_yearly_events` table
- Debug output shows "Processing 0 eligible employees"

**Solutions:**
1. **Check workforce source data exists:**
   ```python
   # Run this diagnostic query
   python -c "
   from orchestrator_mvp.utils.db_utils import get_duckdb_connection
   conn = get_duckdb_connection()
   result = conn.execute('SELECT COUNT(*) FROM int_workforce_previous_year').fetchone()
   print(f'Workforce count: {result[0]}')
   "
   ```

2. **Verify promotion hazard configuration:**
   ```bash
   # Check if hazard rates exist
   cat dbt/seeds/int_promotion_hazard_rates.csv
   ```

3. **Ensure the MVP orchestrator is using the correct mode:**
   ```python
   # Check orchestrator_mvp/mvp_orchestrator.py
   # Should have: debug=True, use_mvp_models=True
   ```

### Issue 2: Incorrect Promotion Rates

**Symptoms:**
- Promotion rates significantly differ from expected values
- Certain levels have 0% or 100% promotion rates

**Solutions:**
1. **Validate hazard rates configuration:**
   ```sql
   -- Run in DuckDB to check rates
   SELECT level, promotion_hazard_rate
   FROM int_promotion_hazard_rates
   ORDER BY level;
   ```

2. **Check for data type issues:**
   - Ensure `promotion_hazard_rate` is numeric, not string
   - Verify `level` values match between workforce and hazard data

3. **Review random seed consistency:**
   ```python
   # Ensure consistent random seed in simulation_config.yaml
   # random_seed: 42  # Or any fixed value for reproducibility
   ```

### Issue 3: Events Not Persisting to Database

**Symptoms:**
- Debug output shows events generated but database query returns empty
- `fct_yearly_events` table missing promotion events

**Solutions:**
1. **Check database connection:**
   ```python
   # Test database write permissions
   from orchestrator_mvp.utils.db_utils import get_duckdb_connection
   conn = get_duckdb_connection()
   conn.execute("CREATE TABLE test_write (id INT)")
   conn.execute("DROP TABLE test_write")
   print("Database write test successful")
   ```

2. **Verify event structure:**
   - Ensure all required fields are present: `employee_id`, `event_type`, `effective_date`, etc.
   - Check data types match schema expectations

3. **Look for transaction rollbacks:**
   - Check logs for error messages during event insertion
   - Ensure no database locks are preventing writes

### Issue 4: Performance Degradation

**Symptoms:**
- Promotion event generation takes >30 seconds
- Memory usage spikes during processing
- System becomes unresponsive

**Solutions:**
1. **Optimize batch processing:**
   ```python
   # Adjust batch size in event_emitter.py
   BATCH_SIZE = 1000  # Reduce if memory constrained
   ```

2. **Profile the bottleneck:**
   ```bash
   # Run with profiling enabled
   python -m cProfile -o profile_output.prof scripts/validate_promotion_events_fix.py
   ```

3. **Check workforce size:**
   - Large workforces (>100k employees) may need optimization
   - Consider processing in chunks

## Diagnostic Steps

### Step 1: Run Validation Script
```bash
# This provides comprehensive diagnostics
python scripts/validate_promotion_events_fix.py
```

### Step 2: Check Debug Output
Look for these key indicators in the console output:
- "Loading promotion hazard rates..." - Confirms configuration loaded
- "Processing X eligible employees for promotions" - Shows workforce size
- "Generated X promotion events" - Final count

### Step 3: Query Event Data
```sql
-- Check promotion events in database
SELECT
    simulation_year,
    COUNT(*) as promotion_count,
    COUNT(DISTINCT employee_id) as unique_employees
FROM fct_yearly_events
WHERE event_type = 'promotion'
GROUP BY simulation_year;
```

### Step 4: Validate Event Structure
```sql
-- Check event fields
SELECT *
FROM fct_yearly_events
WHERE event_type = 'promotion'
LIMIT 5;
```

## Configuration Validation

### Required Files
1. **Promotion Hazard Rates**: `dbt/seeds/int_promotion_hazard_rates.csv`
   ```csv
   level,promotion_hazard_rate
   IC,0.30
   AVP,0.25
   VP,0.15
   ```

2. **Simulation Configuration**: `config/simulation_config.yaml`
   ```yaml
   orchestrator:
     use_mvp_models: true
     debug: true
   simulation:
     random_seed: 42  # For reproducibility
   ```

### Validation Checklist
- [ ] Hazard rates file exists and is properly formatted
- [ ] All employee levels have corresponding hazard rates
- [ ] Random seed is set for reproducibility
- [ ] MVP models are enabled in configuration
- [ ] Database has write permissions
- [ ] No conflicting database locks

## Performance Optimization

### Memory Management
```python
# For large workforces, process in chunks
CHUNK_SIZE = 10000
for i in range(0, len(workforce), CHUNK_SIZE):
    chunk = workforce[i:i+CHUNK_SIZE]
    process_promotions(chunk)
```

### Query Optimization
```sql
-- Use indexes for better performance
CREATE INDEX idx_workforce_level ON int_workforce_previous_year(level);
CREATE INDEX idx_events_type ON fct_yearly_events(event_type, simulation_year);
```

### Parallel Processing
Consider using multiprocessing for very large workforces:
```python
from multiprocessing import Pool
def process_chunk(chunk):
    return generate_promotion_events(chunk)

with Pool(processes=4) as pool:
    results = pool.map(process_chunk, workforce_chunks)
```

## Advanced Debugging

### Enable Verbose Logging
```python
# In mvp_orchestrator.py, set debug=True
orchestrator = MVPOrchestrator(conn, config, debug=True)
```

### Trace Event Generation
```python
# Add breakpoints in event_emitter.py
def _generate_promotion_events(self, workforce_df, simulation_year, scenario_id):
    import pdb; pdb.set_trace()  # Debug here
    # ... rest of the function
```

### Monitor Database Queries
```python
# Enable query logging in DuckDB
conn.execute("SET enable_profiling=true")
conn.execute("SET profiling_mode='detailed'")
```

### Check System Resources
```bash
# Monitor during execution
top -p $(pgrep -f mvp_orchestrator)
```

## Getting Help

If issues persist after following this guide:

1. **Run the test suite:**
   ```bash
   pytest tests/validation/test_promotion_events_fix_validation.py -v
   ```

2. **Collect diagnostic information:**
   - Full console output from validation script
   - Contents of `promotion_events_fix_validation_results.md`
   - Database query results
   - System specifications (memory, CPU)

3. **Check recent changes:**
   - Review git history for changes to event generation
   - Verify no conflicting modifications to hazard rates
   - Ensure dependencies are up to date

## Related Documentation

- [Promotion Events Fix Validation Results](./promotion_events_fix_validation_results.md)
- [MVP Orchestrator Architecture](../architecture.md)
- [Event Schema Documentation](../events.md)
