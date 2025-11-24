# New Hire Salary Adjustment Example

## The Problem
New hires are coming in at ~$107K while existing employees average ~$167K, creating a 37% compensation gap that dilutes overall growth.

## Solution: New Hire Salary Adjustment Parameter

### Step 1: Understanding the Parameter
The `new_hire_salary_adjustment` parameter is a multiplier applied to new hire starting salaries:
- 1.00 = baseline (no change)
- 1.15 = 15% increase
- 1.20 = 20% increase

### Step 2: Edit the Parameter File

Open `/dbt/seeds/comp_levers.csv` and find these lines:
```csv
default,2025,1,hire,new_hire_salary_adjustment,1.00,1,2025-06-28,system
default,2025,2,hire,new_hire_salary_adjustment,1.00,1,2025-06-28,system
default,2025,3,hire,new_hire_salary_adjustment,1.00,1,2025-06-28,system
default,2025,4,hire,new_hire_salary_adjustment,1.00,1,2025-06-28,system
default,2025,5,hire,new_hire_salary_adjustment,1.00,1,2025-06-28,system
```

To increase new hire salaries by 20%, change to:
```csv
default,2025,1,hire,new_hire_salary_adjustment,1.20,1,2025-06-28,analyst
default,2025,2,hire,new_hire_salary_adjustment,1.20,1,2025-06-28,analyst
default,2025,3,hire,new_hire_salary_adjustment,1.20,1,2025-06-28,analyst
default,2025,4,hire,new_hire_salary_adjustment,1.20,1,2025-06-28,analyst
default,2025,5,hire,new_hire_salary_adjustment,1.20,1,2025-06-28,analyst
```

### Step 3: Apply Changes and Run Simulation
```bash
cd /Users/nicholasamaral/planalign_engine
source venv/bin/activate
cd dbt
dbt seed --select comp_levers
dbt run --select stg_comp_levers int_effective_parameters int_hiring_events
cd ..
# Run multi_year_simulation in Dagster UI
```

### Step 4: Expected Impact
With a 20% new hire salary increase:
- New hire average: $107K → $128K
- Compensation gap: 37% → 23%
- Overall growth impact: +0.6% to +0.8%

## Combined Strategy Example

To achieve 2% growth (from current -1.6%), you might combine:

```csv
# Moderate COLA increase
cola_rate,0.035  # (3.5%, up from 2.5%)

# Slight merit boost
merit_base,0.045  # Level 1 (up from 0.035)
merit_base,0.050  # Level 2 (up from 0.040)
# etc.

# New hire adjustment
new_hire_salary_adjustment,1.15  # 15% increase
```

This balanced approach:
- Reduces dilution effect
- Controls budget impact
- Maintains internal equity
- Achieves target growth

## Level-Specific Adjustments

You can also adjust new hire salaries differently by level:
```csv
# Entry levels get smaller increases
default,2025,1,hire,new_hire_salary_adjustment,1.10,1,2025-06-28,analyst
default,2025,2,hire,new_hire_salary_adjustment,1.12,1,2025-06-28,analyst

# Mid/senior levels get larger increases to close gap
default,2025,3,hire,new_hire_salary_adjustment,1.18,1,2025-06-28,analyst
default,2025,4,hire,new_hire_salary_adjustment,1.22,1,2025-06-28,analyst
default,2025,5,hire,new_hire_salary_adjustment,1.25,1,2025-06-28,analyst
```

This targets the compensation gap where it's most pronounced while managing budget impact.
