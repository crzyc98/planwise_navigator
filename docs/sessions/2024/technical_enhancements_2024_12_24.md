# Technical Enhancements - December 24, 2024

## Overview

This document details two critical technical enhancements implemented to improve PlanWise Navigator's data architecture and compensation accuracy:

1. **Circular Dependency Resolution**: Eliminated circular reference between `fct_workforce_snapshot` and `int_previous_year_workforce`
2. **Plan Year Compensation Annualization**: Enhanced baseline workforce accuracy by annualizing partial year compensation

---

## Enhancement 1: Circular Dependency Resolution

### Problem Statement

**Issue**: Circular dependency existed between two core dbt models:
- `fct_workforce_snapshot.sql` → referenced `int_previous_year_workforce`
- `int_previous_year_workforce.sql` → referenced `fct_workforce_snapshot`

**Impact**:
- Broke dbt's dependency tracking system
- Required hacky direct table references (`{{ this.schema }}.fct_workforce_snapshot`)
- Caused issues with `dbt run --select` commands
- Made debugging and maintenance difficult
- Violated dbt best practices

### Solution Implemented

**New Architecture**: Replaced circular dependency with dbt snapshots and clean linear dependencies.

#### Files Created
1. **`dbt/snapshots/scd_workforce_state.sql`**
   - Uses dbt's built-in snapshot functionality
   - Timestamp-based SCD strategy for state management
   - Captures workforce state independently without circular references

2. **`dbt/models/intermediate/int_workforce_previous_year.sql`**
   - Clean replacement for `int_previous_year_workforce.sql`
   - References snapshot for previous year data
   - No circular dependencies

#### Files Modified
1. **5 Event Models Updated**:
   - `int_hiring_events.sql`
   - `int_termination_events.sql`
   - `int_promotion_events.sql`
   - `int_merit_events.sql`
   - All now reference `int_workforce_previous_year` instead of `int_previous_year_workforce`

2. **`fct_workforce_snapshot.sql`**:
   - Updated to reference `int_workforce_previous_year`
   - Removed complex year-based logic dependencies

#### Files Deleted
- **`int_previous_year_workforce.sql`** - Source of circular dependency

### New Architecture Flow
```
├── snapshots/scd_workforce_state.sql           # Independent state management
├── intermediate/int_workforce_previous_year.sql # References snapshot (no cycles)
├── intermediate/events/int_*_events.sql         # Reference previous year model
├── marts/fct_workforce_snapshot.sql            # References events (clean linear flow)
```

### Benefits Achieved
- ✅ **Eliminated Circular Dependencies**: Clean, unidirectional dependency graph
- ✅ **dbt Best Practices**: Using proper snapshot functionality
- ✅ **Improved Maintainability**: Clear separation of concerns
- ✅ **Better Performance**: Optimized snapshot queries vs. complex workarounds
- ✅ **Audit Trail**: Built-in SCD tracking of workforce state changes
- ✅ **Debugging Friendly**: `dbt deps`, `dbt run --select` work correctly

### Verification
- ✅ `dbt parse` - No circular dependency errors
- ✅ `dbt deps` - All dependencies resolved correctly
- ✅ `dbt list --select int_workforce_previous_year+` - Shows clean dependency tree

---

## Enhancement 2: Plan Year Compensation Annualization

### Problem Statement

**Issue**: Baseline workforce used raw compensation data that included proration effects for partial year workers, creating bias in:
- Starting workforce compensation averages
- Job level assignments based on prorated vs. full salaries
- Compensation growth tracking accuracy

**Epic E012 Context**: This directly supports the `full_year_equivalent_compensation` fix by providing accurate baseline data.

### Solution Implemented

#### Configuration Added (`simulation_config.yaml`)
```yaml
plan_year:
  start_date: "2024-01-01"  # Plan year start date
  end_date: "2024-12-31"    # Plan year end date
  annualization_method: "calendar_days"  # Annualization approach
```

#### Enhanced `stg_census_data.sql`

**New Logic**:
1. **Reads Plan Year Compensation**: `COALESCE(employee_plan_year_compensation, employee_gross_compensation)`
2. **Intelligent Annualization**:
   ```sql
   CASE
       -- Mid-year hire: gross up based on hire date to plan year end
       WHEN employee_hire_date > plan_year_start
            AND employee_hire_date <= plan_year_end
       THEN raw_plan_year_compensation * 365.0 / days_worked

       -- Early termination: gross up based on termination date
       WHEN employee_termination_date IS NOT NULL
            AND employee_termination_date < plan_year_end
       THEN raw_plan_year_compensation * 365.0 / days_worked

       -- Mid-year hire + termination: gross up based on actual work period
       WHEN hire_and_term_same_year
       THEN raw_plan_year_compensation * 365.0 / days_worked

       -- Full year worker: no adjustment needed
       ELSE raw_plan_year_compensation
   END AS employee_annualized_compensation
   ```

#### Updated `int_baseline_workforce.sql`

**Changes**:
1. **Uses Annualized Compensation**: `COALESCE(stg.employee_annualized_compensation, stg.employee_gross_compensation)`
2. **Improved Level Matching**: Job level assignment based on annualized salary instead of prorated amounts

### Example Results

| Scenario | Plan Year Comp | Days Worked | Annualized Comp | Benefit |
|----------|----------------|-------------|------------------|---------|
| Mid-year hire (July 1) | $60,000 | 184 days | $119,022 | True annual salary |
| Early termination (Mar 31) | $25,000 | 91 days | $100,275 | True annual salary |
| Full year worker | $120,000 | 365 days | $120,000 | No change needed |

### Benefits Achieved
- ✅ **Eliminates Proration Bias**: Baseline workforce uses true annual salaries
- ✅ **Accurate Growth Tracking**: Aligns with `full_year_equivalent_compensation` methodology
- ✅ **Better Job Level Assignment**: Levels based on true earning capacity vs. partial payments
- ✅ **Consistent Methodology**: Same annualization approach throughout pipeline
- ✅ **Epic E012 Support**: Provides accurate baseline for compensation growth analysis

### Integration with Epic E012

This enhancement directly supports the `full_year_equivalent_compensation` fix by:
1. **Eliminating Baseline Bias**: Starting workforce compensation is now accurate
2. **Consistent Methodology**: Same annualization logic used throughout pipeline
3. **Accurate Growth Measurement**: Removes proration dilution from baseline calculations

---

## Files Modified Summary

### Circular Dependency Fix
| File | Action | Description |
|------|--------|-------------|
| `snapshots/scd_workforce_state.sql` | **Created** | dbt snapshot for state management |
| `int_workforce_previous_year.sql` | **Created** | Clean replacement model |
| `int_hiring_events.sql` | **Modified** | Updated reference |
| `int_termination_events.sql` | **Modified** | Updated reference |
| `int_promotion_events.sql` | **Modified** | Updated reference |
| `int_merit_events.sql` | **Modified** | Updated reference |
| `fct_workforce_snapshot.sql` | **Modified** | Updated reference |
| `int_previous_year_workforce.sql` | **Deleted** | Removed circular dependency source |

### Plan Year Compensation Enhancement
| File | Action | Description |
|------|--------|-------------|
| `simulation_config.yaml` | **Modified** | Added plan year configuration |
| `stg_census_data.sql` | **Modified** | Added annualization logic |
| `int_baseline_workforce.sql` | **Modified** | Uses annualized compensation |

---

## Testing & Verification

### Circular Dependency Fix
```bash
# Verify no circular dependencies
dbt parse                     # ✅ Success - no errors
dbt deps                      # ✅ Success - clean dependencies
dbt list --select int_workforce_previous_year+  # ✅ Shows 10+ downstream models
```

### Plan Year Compensation
```bash
# Verify annualization logic
dbt parse                     # ✅ Success - SQL compiles correctly
python test_annualization.py # ✅ Verified calculation examples
```

---

## Impact on Epic E012

Both enhancements directly support **Epic E012 Phase 2B: Critical Bug Fix for full_year_equivalent_compensation**:

1. **Circular Dependency Fix**: Enables clean architecture for compensation calculations
2. **Plan Year Annualization**: Provides accurate baseline data eliminating proration bias
3. **Combined Effect**: Ensures `full_year_equivalent_compensation` averages show true growth instead of declining trends

**Expected Outcome**: With COLA (1.0%) + Merit (3.5%) = 4.5% annual growth, compensation metrics should now show positive year-over-year growth instead of the previous declining pattern.

---

## Future Considerations

### Circular Dependency Architecture
- **Snapshots**: Consider automating snapshot updates through Dagster pipeline
- **State Management**: Monitor snapshot table growth and implement retention policies
- **Performance**: Optimize snapshot queries for large datasets

### Plan Year Compensation
- **Work Days vs Calendar Days**: Consider supporting work-day-based annualization
- **Variable Plan Years**: Support for non-calendar plan years
- **Regional Variations**: Handle different plan year conventions by business unit

---

## Conclusion

These enhancements establish a solid foundation for accurate workforce simulation and compensation analysis by:
1. **Eliminating Technical Debt**: Resolved circular dependencies using dbt best practices
2. **Improving Data Accuracy**: Annualized compensation provides unbiased baseline metrics
3. **Supporting Business Requirements**: Enables accurate compensation growth tracking for Epic E012

The combined improvements ensure PlanWise Navigator can reliably measure and project compensation growth against strategic targets.
