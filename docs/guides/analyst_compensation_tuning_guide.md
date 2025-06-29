# Analyst Guide: Compensation Tuning System

## Quick Start for Analysts

### What This System Does
Allows you to adjust compensation parameters (COLA, merit rates) and immediately see the impact on overall compensation growth without writing any code.

### Step-by-Step Process

## 1. Open the Parameter File
```bash
# Navigate to the project directory
cd /Users/nicholasamaral/planwise_navigator

# Open the compensation parameters file
open dbt/seeds/comp_levers.csv
# OR use your preferred editor:
# code dbt/seeds/comp_levers.csv
```

## 2. Understanding the Parameter File

The CSV has these columns:
- **scenario_id**: Keep as "default"
- **fiscal_year**: Year the parameter applies (2025, 2026, etc.)
- **job_level**: Employee level (1-5)
- **event_type**: RAISE, PROMOTION
- **parameter_name**: cola_rate, merit_base, promotion_raise
- **parameter_value**: The decimal rate (0.025 = 2.5%)
- **is_locked**: 1 = confirmed, 0 = draft
- **created_at**: Today's date
- **created_by**: Your name

### Example: Increase COLA from 2.5% to 4.0%
```csv
# Change these lines:
default,2025,1,RAISE,cola_rate,0.025,1,2025-06-27,system
# To:
default,2025,1,RAISE,cola_rate,0.040,1,2025-06-28,analyst_name
```

## 3. Apply Your Changes

After editing comp_levers.csv, run these commands:

```bash
# 1. Activate the Python environment
source venv/bin/activate

# 2. Load your parameter changes into the database
cd dbt
dbt seed --select comp_levers

# 3. Refresh the parameter models
dbt run --select stg_comp_levers int_effective_parameters

# 4. Go back to main directory
cd ..
```

## 4. Run the Simulation

```bash
# Start Dagster (if not already running)
dagster dev

# Open browser to http://localhost:3000
# Click on "Jobs" in the left menu
# Find "multi_year_simulation"
# Click "Materialize"
# Wait for completion (usually 2-3 minutes)
```

## 5. Analyze Results

Run this analysis script:
```bash
python scripts/analyze_compensation_growth.py
```

Or create your own analysis:
```python
import duckdb
conn = duckdb.connect('simulation.duckdb')

# Check compensation growth
query = '''
WITH yearly_avg AS (
    SELECT
        simulation_year,
        AVG(current_compensation) as avg_comp
    FROM main.fct_workforce_snapshot
    WHERE employment_status = 'active'
    GROUP BY simulation_year
)
SELECT
    simulation_year,
    avg_comp,
    (avg_comp - LAG(avg_comp) OVER (ORDER BY simulation_year))
        / LAG(avg_comp) OVER (ORDER BY simulation_year) * 100 as growth_pct
FROM yearly_avg
ORDER BY simulation_year
'''
print(conn.execute(query).df())
```

## Common Tuning Scenarios

### Scenario 1: Achieve 2% Compensation Growth
```csv
# Current baseline: -3.7% growth
# Try these adjustments:
# 1. Increase COLA to 4.0% (all levels)
# 2. Add +1.0% to all merit rates
# Expected result: ~-1.6% growth (improvement of 2.1%)
```

### Scenario 2: Budget-Conscious Growth
```csv
# Targeted approach:
# 1. Keep COLA at 2.5%
# 2. Increase merit only for levels 3-5 by +2.0%
# 3. Reduce new hire starting salaries by 5%
```

### Scenario 3: Retention Focus
```csv
# High performer retention:
# 1. COLA: 3.0% across the board
# 2. Merit: Level 1-2: +0.5%, Level 3-5: +2.0%
# 3. Promotion raises: Increase from 12% to 15%
```

## Tips for Analysts

### 1. Start Small
- Change one parameter type at a time
- Run simulation after each change
- Document what worked/didn't work

### 2. Watch for Dilution Effects
- New hire volume has massive impact
- Check the hire/termination ratio
- Consider new hire compensation gaps

### 3. Use the Audit Trail
```sql
-- See what parameters were used in each simulation
SELECT DISTINCT
    simulation_year,
    event_type,
    parameter_name,
    parameter_value
FROM main.fct_yearly_events
WHERE compensation_amount > 0
ORDER BY simulation_year, event_type
```

### 4. Create Scenarios
- Copy comp_levers.csv to comp_levers_scenario_A.csv
- Edit scenario_id from "default" to "scenario_A"
- Compare results between scenarios

## Common Issues & Solutions

### Issue: "My changes aren't showing up"
```bash
# Make sure to run ALL these steps:
cd dbt
dbt seed --select comp_levers
dbt run --select stg_comp_levers int_effective_parameters
# Then re-run simulation in Dagster
```

### Issue: "Simulation takes too long"
```bash
# Run single year first to test:
# In Dagster UI, materialize "simulation_year_state" instead
# This runs just 2025 instead of 2025-2029
```

### Issue: "How do I reset everything?"
```bash
# Restore original parameters:
cd dbt/seeds
git checkout comp_levers.csv
dbt seed --select comp_levers
# Re-run simulation
```

## Quick Reference Card

```
PARAMETER RANGES (Typical):
- COLA: 2.0% - 4.5%
- Merit (by level):
  - Level 1: 3.0% - 5.0%
  - Level 2: 3.5% - 5.5%
  - Level 3: 4.0% - 6.0%
  - Level 4: 4.5% - 6.5%
  - Level 5: 5.0% - 7.0%
- Promotion Raise: 10% - 20%

IMPACT ESTIMATES:
- +1% COLA = ~+1.0% total growth
- +1% Merit = ~+0.8% total growth
- -100 new hires = ~+0.5% total growth
- +10% new hire salary = ~+0.3% total growth
```

## Getting Help

1. Check parameter values loaded correctly:
   ```sql
   SELECT * FROM main.stg_comp_levers
   WHERE fiscal_year = 2025
   ```

2. Verify simulation ran:
   ```sql
   SELECT MAX(simulation_year) FROM main.fct_workforce_snapshot
   ```

3. Review the analysis documentation:
   - `/docs/analysis/S050_compensation_dilution_analysis.md`
   - `/docs/stories/S043-parameter-tables-foundation.md`

Remember: The goal is to experiment quickly and find the right balance between cost and growth targets!
