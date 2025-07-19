# Session 2025-07-18: Fixing Promotion Events in MVP Orchestrator

## Problem Statement

The MVP orchestrator was generating 0 promotion events despite having 3,506 eligible employees with promotion probabilities ranging from 2-12%. Debug output showed:

```
🔍 DEBUG: Found 3506 employees eligible for promotion
📊 Promotion eligibility by level:
   Level 1.0: 1922 employees, 12.0% probability
   Level 2.0: 1170 employees, 8.0% probability
   Level 3.0: 192 employees, 5.0% probability
   Level 4.0: 222 employees, 2.0% probability
🔍 DEBUG: Promotion decisions made for 3506 employees
   Total promoted: 0
```

## Root Cause Analysis

Research into the legacy dbt pipeline revealed several critical differences between the MVP implementation and the working legacy system:

### 1. **Fundamental Probability Calculation Difference**
- **Legacy dbt**: Uses sophisticated hazard-based model with age/tenure multipliers
- **MVP Python**: Used simple fixed probabilities from job levels table
- **Impact**: MVP ignored hazard table calculations entirely

### 2. **Random Value Generation Mismatch**
- **Legacy dbt**: `(ABS(HASH(w.employee_id)) % 1000) / 1000.0`
- **MVP Python**: `((id_hash * 17 + simulation_year * 7) % 1000) / 1000.0`
- **Impact**: Different random distributions affected probability outcomes

### 3. **Missing Hazard Table Integration**
- **Legacy**: Joins with `dim_hazard_table` for calculated promotion_rate
- **MVP**: Directly used `promotion_probability` from job levels (12%, 8%, 5%, 2%, 1%)
- **Impact**: Missing crucial age/tenure-based probability adjustments

### 4. **Workforce Source Difference**
- **Legacy**: Uses `int_workforce_previous_year` (proper dependency handling)
- **MVP**: Used `int_baseline_workforce` directly
- **Impact**: May not handle multi-year progression correctly

## Solution Implementation

### Legacy Hazard Formula
The legacy system calculates actual promotion rates using:
```sql
base_rate * tenure_mult * age_mult * GREATEST(0, 1 - level_dampener_factor * (level_id - 1))
```

Where:
- `base_rate`: 0.1 (10% base promotion rate)
- `level_dampener_factor`: 0.15 (15% reduction per level)
- `tenure_mult`: Varies by tenure band (0.8 to 1.2)
- `age_mult`: Varies by age band (0.5 to 1.2)

### Implementation Changes

1. **Created `_load_promotion_hazard_config()` function**:
   ```python
   def _load_promotion_hazard_config(conn) -> Dict[str, Any]:
       # Load base configuration from config_promotion_hazard_base
       # Load age multipliers from config_promotion_hazard_age_multipliers
       # Load tenure multipliers from config_promotion_hazard_tenure_multipliers
   ```

2. **Created `_calculate_promotion_probability()` function**:
   ```python
   def _calculate_promotion_probability(level_id, age_band, tenure_band, hazard_config):
       base_rate = hazard_config['base_rate']
       level_dampener_factor = hazard_config['level_dampener_factor']
       age_mult = age_multipliers.get(age_band, 1.0)
       tenure_mult = tenure_multipliers.get(tenure_band, 1.0)

       level_dampener = max(0, 1 - level_dampener_factor * (level_id - 1))
       promotion_rate = base_rate * tenure_mult * age_mult * level_dampener

       return min(promotion_rate, 0.5)  # Cap at 50%
   ```

3. **Fixed workforce query** to use `int_workforce_previous_year`:
   ```sql
   SELECT
       employee_id, employee_ssn, employee_birth_date, employee_hire_date,
       employee_gross_compensation, current_age, current_tenure, level_id
   FROM int_workforce_previous_year
   WHERE employment_status = 'active'
   AND current_tenure >= 1 AND level_id < 5 AND current_age < 65
   ```

4. **Fixed random value generation** to match legacy:
   ```python
   employee_id_str = str(employee['employee_id'])
   id_hash = abs(hash(employee_id_str)) % 1000
   random_value = id_hash / 1000.0
   ```

5. **Updated run_mvp.py** to load required seeds:
   ```python
   run_dbt_seed("config_promotion_hazard_base")
   run_dbt_seed("config_promotion_hazard_age_multipliers")
   run_dbt_seed("config_promotion_hazard_tenure_multipliers")
   run_dbt_model("int_workforce_previous_year")
   ```

6. **Enhanced debug output** to show calculated promotion rates and random value distributions:
   ```python
   print("📊 Promotion results by level:")
   for level_id in level_summary.index:
       total = level_summary.loc[level_id, ('promoted', 'count')]
       promoted = level_summary.loc[level_id, ('promoted', 'sum')]
       prob = level_summary.loc[level_id, ('promotion_rate', 'first')]
       print(f"   Level {level_id}: {promoted}/{total} promoted ({actual_rate:.1%} actual vs {prob:.1%} expected)")
       print(f"     Random values: min={min_rand:.3f}, max={max_rand:.3f}, mean={mean_rand:.3f}")
   ```

## Expected Outcome

The hazard-based promotion calculation should produce much lower but more realistic promotion rates:

- **Level 1**: ~6-8% (base 10% * age/tenure multipliers * 1.0 level factor)
- **Level 2**: ~5-7% (base 10% * age/tenure multipliers * 0.85 level factor)
- **Level 3**: ~4-6% (base 10% * age/tenure multipliers * 0.70 level factor)
- **Level 4**: ~3-4% (base 10% * age/tenure multipliers * 0.55 level factor)

This should generate realistic promotion events that match the legacy pipeline behavior, replacing the previous static rates that were too high and not properly implemented.

## Key Files Modified

1. **`orchestrator_mvp/core/event_emitter.py`**:
   - Completely rewrote `generate_promotion_events()` function
   - Added `_load_promotion_hazard_config()` helper
   - Added `_calculate_promotion_probability()` helper
   - Fixed random value generation algorithm
   - Enhanced debug logging

2. **`orchestrator_mvp/run_mvp.py`**:
   - Added loading of promotion hazard seed files
   - Added `int_workforce_previous_year` model execution step

## Technical Debt Addressed

- Removed dependency on incorrect static promotion probabilities
- Aligned random number generation with legacy pipeline
- Proper workforce source for multi-year compatibility
- Comprehensive hazard-based probability calculation
- Enhanced debugging for future troubleshooting

## Validation Plan

1. Run the MVP orchestrator and verify promotion events are generated
2. Compare promotion rates by level with expected hazard-based calculations
3. Verify random value distribution spreads across 0.0-1.0 range
4. Confirm promotion events have proper event structure and database storage
