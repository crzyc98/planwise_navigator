# Compensation Tuning Cheat Sheet

## 🎯 Quick Steps to Tune Compensation

### 1️⃣ Edit Parameters
```bash
# Open the file
code dbt/seeds/comp_levers.csv

# Change COLA example (2.5% → 4.0%):
# FROM: default,2025,1,RAISE,cola_rate,0.025,1,2025-06-27,system
# TO:   default,2025,1,RAISE,cola_rate,0.040,1,2025-06-28,yourname

# Increase new hire salaries by 15%:
# FROM: default,2025,1,hire,new_hire_salary_adjustment,1.00,1,2025-06-28,system
# TO:   default,2025,1,hire,new_hire_salary_adjustment,1.15,1,2025-06-28,yourname
```

### 2️⃣ Load Changes
```bash
cd /Users/nicholasamaral/planalign_engine
source venv/bin/activate
cd dbt
dbt seed --select comp_levers
dbt run --select stg_comp_levers int_effective_parameters
cd ..
```

### 3️⃣ Run Simulation
```bash
# Open browser to http://localhost:3000
# Jobs → multi_year_simulation → Materialize
# Wait ~2-3 minutes
```

### 4️⃣ Check Results
```bash
python scripts/analyze_compensation_growth.py
```

## 📊 Parameter Impact Guide

| Change | Approximate Impact on Growth |
|--------|------------------------------|
| +1% COLA | +1.0% growth |
| +1% Merit (all levels) | +0.8% growth |
| -100 new hires | +0.5% growth |
| +10% new hire salary | +0.3% growth |
| +15% new hire adjustment | +0.5% growth |

## 🎨 Common Scenarios

### "I need 2% growth" (currently at -1.6%)
```csv
# Option A: Increase COLA to 5.5%
cola_rate,0.055

# Option B: Add +2% to all merit rates
merit_base,0.065  # (was 0.045 for level 1)

# Option C: Increase new hire salaries by 20%
new_hire_salary_adjustment,1.20  # (was 1.00)
```

### "Budget is tight"
```csv
# Target high levels only
# Keep level 1-2 merit same
# Increase level 3-5 merit by +2%
```

### "Focus on retention"
```csv
# Increase promotion raises
promotion_raise,0.15  # (was 0.12)
```

## ⚠️ Common Mistakes

1. **Forgetting to run dbt seed** → Changes won't apply
2. **Wrong decimal format** → Use 0.025 not 2.5
3. **Not running all years** → Use multi_year_simulation
4. **Editing wrong year** → Check fiscal_year column

## 🔍 Debug Commands

```sql
-- Check if parameters loaded
SELECT * FROM main.stg_comp_levers WHERE fiscal_year = 2025;

-- See actual growth
SELECT simulation_year, AVG(current_compensation)
FROM main.fct_workforce_snapshot
WHERE employment_status = 'active'
GROUP BY 1;
```

## 📞 Need Help?

1. Run the analysis script first
2. Check `/docs/reminders/` for recent calibration results
3. Review `/docs/analysis/S050_compensation_dilution_analysis.md`

Remember: **New hire dilution** is the biggest challenge - even good raises can be overwhelmed by high-volume, lower-paid new hires!
