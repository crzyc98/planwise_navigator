# PlanWise Navigator Debugging Cookbook

A comprehensive guide for debugging common issues in the workforce simulation system.

## Quick Start Debugging

### Environment Setup
```bash
# Always run from correct directories
cd /Users/nicholasamaral/planwise_navigator/dbt    # For dbt commands
cd /Users/nicholasamaral/planwise_navigator/       # For dagster commands

# Database location
Database: /Users/nicholasamaral/planwise_navigator/simulation.duckdb
Schema: main
```

### Launch Simulation
```bash
make run-simulation                    # Start Dagster UI
# Then use UI to run multi_year_simulation asset
```

## Multi-Year Simulation Debugging

### 1. Verify Baseline Data
```bash
cd dbt
dbt seed                              # Load configuration CSVs
dbt run --select staging             # Prepare staging models
dbt run --select int_baseline_workforce  # Verify baseline workforce
```

**Expected Result**: ~4,378 active employees in baseline

### 2. Check Database State
```sql
-- Connect to database
python3 -c "
import duckdb
conn = duckdb.connect('/Users/nicholasamaral/planwise_navigator/simulation.duckdb')
conn.execute('USE main')

# Check available tables
tables = conn.execute('SHOW TABLES').fetchall()
print('Tables:', [t[0] for t in tables])

# Check baseline count
baseline = conn.execute('SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = \"active\"').fetchone()[0]
print(f'Baseline active workforce: {baseline}')
"
```

### 3. Multi-Year Simulation Sequence

The proper execution order (from `orchestrator/simulator_pipeline.py`):

1. **Data Cleaning**: `clean_duckdb_data()` - removes existing simulation data
2. **Baseline Validation**: Ensures baseline workforce exists
3. **Year-by-Year Loop** (2025-2029):
   - `int_workforce_previous_year` - establishes workforce base
   - `int_termination_events` - processes departures
   - `int_promotion_events` - handles promotions
   - `int_merit_events` - applies merit increases
   - `int_hiring_events` - calculates and executes hires
   - `int_new_hire_termination_events` - processes new hire departures
   - `fct_yearly_events` - consolidates all events
   - `fct_workforce_snapshot` - final workforce state
   - `scd_workforce_state` snapshot - preserves state for next year

## Common Issues & Solutions

### Issue 1: Model Name Typos
```python
# ❌ WRONG: Common typo
int_previous_year_workforce

# ✅ CORRECT: Actual model name
int_workforce_previous_year
```

### Issue 2: Snapshot Dependencies Missing
**Error**: "Table with name scd_workforce_state does not exist"

**Solution**: Add to `dbt/models/sources.yml`:
```yaml
sources:
  - name: snapshots
    tables:
      - name: scd_workforce_state
```

### Issue 3: Growth Rate Issues
**Symptoms**:
- 2026: 3.1% growth ✅
- 2027: 6.8% growth ⚠️
- 2028: 9.3% growth ❌
- 2029: 17.5% growth ❌❌

**Debug Steps**:
1. Check workforce count consistency:
```sql
-- Should return dynamic counts, not baseline 4,378
SELECT COUNT(*) FROM int_workforce_previous_year WHERE employment_status = 'active'
```

2. Verify termination classification:
```sql
SELECT
    employee_type,
    COUNT(*) as termination_count
FROM int_termination_events
WHERE simulation_year = 2029
GROUP BY employee_type
```

3. Check hiring calculation:
```python
# Look for debug logs in Dagster:
context.log.info(f"📊 Starting workforce: {workforce_count}")
context.log.info(f"🎯 TOTAL HIRES CALLING FOR: {total_hires_needed}")
```

### Issue 4: Database Connection Errors
**Symptoms**: "Table does not exist" or connection failures

**Solutions**:
```python
# ✅ CORRECT: Use context managers
with duckdb.get_connection() as conn:
    conn.execute("USE main")  # Always set schema
    result = conn.execute(query).df()

# ❌ WRONG: Direct connection without schema
conn = duckdb.connect("simulation.duckdb")
```

## Validation Patterns

### Expected Growth Progression
Target 3% annual growth from 4,378 baseline:
- 2025: 4,510 (+3.0%)
- 2026: 4,645 (+3.0%)
- 2027: 4,780 (+3.0%)
- 2028: 4,922 (+3.0%)
- 2029: 5,066 (+3.0%)

### Key Validation Queries
```sql
-- Year-over-year growth rates
SELECT
    simulation_year,
    active_end_count,
    LAG(active_end_count, 1) OVER (ORDER BY simulation_year) as prev_count,
    ROUND(((active_end_count - LAG(active_end_count, 1) OVER (ORDER BY simulation_year)) * 100.0 /
           LAG(active_end_count, 1) OVER (ORDER BY simulation_year)), 2) as growth_pct
FROM fct_workforce_snapshot
ORDER BY simulation_year;

-- Event counts by year
SELECT simulation_year, event_type, COUNT(*)
FROM fct_yearly_events
GROUP BY simulation_year, event_type
ORDER BY simulation_year, event_type;

-- Mathematical validation
SELECT
    simulation_year,
    baseline_count + hires - terminations as calculated_workforce,
    active_end_count as actual_workforce,
    (active_end_count - (baseline_count + hires - terminations)) as variance
FROM fct_workforce_snapshot;
```

## Test Data Setup

### Quick Test Environment
```bash
cd dbt
dbt deps                              # Install dbt packages
dbt seed                              # Load CSV config data
python tests/utils/generate_fake_census.py --employees 10000  # Generate test data
```

### Integration Testing
```bash
./scripts/run_ci_tests.sh             # Full CI test suite
pytest tests/integration/test_five_year_projections.py  # Specific tests
```

## Performance Debugging

### Expected Benchmarks
- 5-year simulation: <30 seconds (10K employees)
- Single year: <5 seconds
- Database queries: <2 seconds (95th percentile)

### Memory Issues
```bash
# Check DuckDB memory settings in profiles.yml
memory_limit: '2GB'
threads: 1
```

## Emergency Recovery

### Reset Simulation State
```python
# From Dagster UI or Python
from orchestrator.operations import clean_duckdb_data
clean_duckdb_data(context, duckdb_resource)
```

### Rebuild from Scratch
```bash
cd dbt
dbt clean                             # Clear dbt artifacts
dbt deps                              # Reinstall packages
dbt seed                              # Reload configuration
dbt run --select staging             # Rebuild staging
# Then run multi-year simulation via Dagster
```

This cookbook provides the essential debugging patterns for maintaining the PlanWise Navigator simulation system.
