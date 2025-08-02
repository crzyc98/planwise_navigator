# DBT Workforce Needs Integration Failure

**Date**: 2025-08-02
**Priority**: High
**Status**: Open
**Reporter**: Claude Code

## Issue Summary

The dbt workforce needs integration MVP appears to be failing catastrophically, producing extremely inflated hiring and termination numbers that are 5-10x higher than expected. The multi-year simulation is generating:

- 5,907 hires vs baseline of 4,368 employees (135% hiring rate)
- 1,832 terminations
- 103% growth in one year
- System flags: "HIGH HIRE COUNT" and "HIGH TERMINATION COUNT"

## Expected vs Actual Results

**Expected for 3% growth scenario:**
- ~130 hires (4,368 * 0.03 / (1 - 0.25) ≈ 175 hires accounting for new hire turnover)
- ~524 experienced terminations (4,368 * 0.12)
- Net growth: ~131 employees (3%)

**Actual Results:**
- 5,907 hires (34x too high)
- 1,832 terminations (3.5x too high)
- Net growth: +4,511 employees (103%)

## Root Cause Analysis

### Suspected Issues

1. **dbt Models Not Executing**: Initial investigation shows `int_workforce_needs` table doesn't exist in the database
   ```bash
   duckdb.duckdb.CatalogException: Table with name int_workforce_needs does not exist!
   ```

2. **Fallback to Mathematical Calculation**: The system likely fell back to the original mathematical calculations, but something is wrong with the parameters being passed

3. **Parameter Multiplication**: There may be a parameter multiplication issue where growth rates or termination rates are being applied incorrectly

4. **Database Schema Mismatch**: The models may be writing to a different schema or database than expected

## Investigation Steps Taken

1. ✅ Confirmed dbt models compile and run successfully:
   ```bash
   dbt run --select int_workforce_needs --vars "simulation_year: 2025"
   # Result: OK created sql table model main.int_workforce_needs
   ```

2. ❌ Models not accessible from simulation:
   ```
   Table with name int_workforce_needs does not exist!
   ```

3. ✅ Integration code implementation completed:
   - `DbtWorkforceNeedsInterface` class created
   - `WorkforceCalculator` updated to use dbt models
   - `BatchEventGenerator` enhanced with level breakdown
   - `YearProcessor` updated to coordinate dbt execution

## Technical Details

### Code Changes Made
- **File**: `orchestrator_dbt/core/workforce_needs_interface.py` - New interface class
- **File**: `orchestrator_dbt/simulation/workforce_calculator.py` - Enhanced with dbt integration
- **File**: `orchestrator_dbt/simulation/event_generator.py` - Added dbt-driven event generation
- **File**: `orchestrator_dbt/multi_year/year_processor.py` - Updated to coordinate dbt models

### Data Flow Expected
```
1. YearProcessor calls WorkforceCalculator
2. WorkforceCalculator executes dbt workforce needs models
3. WorkforceCalculator queries dbt model results
4. BatchEventGenerator uses dbt level breakdown
5. Events generated according to dbt planning
```

### Data Flow Actual
```
1. YearProcessor calls WorkforceCalculator
2. dbt model execution fails or writes to wrong location
3. System falls back to mathematical calculation
4. Mathematical calculation produces inflated numbers
5. Events generated with wrong parameters
```

## Potential Solutions

### Immediate (High Priority)
1. **Database Schema Investigation**: Check if models are writing to correct database/schema
2. **Connection String Validation**: Ensure dbt and orchestrator use same database
3. **Model Materialization Check**: Verify models are actually materializing as tables
4. **Fallback Parameter Validation**: Check mathematical fallback parameters

### Short Term
1. **Add Debugging Logging**: Enhanced logging to trace data flow
2. **Integration Test Suite**: Comprehensive testing of each integration point
3. **Manual Model Execution**: Test dbt models independently
4. **Database State Validation**: Verify database state before/after dbt runs

### Long Term
1. **Robust Error Handling**: Better error detection and reporting
2. **Data Validation Framework**: Sanity checks on workforce requirements
3. **Integration Monitoring**: Real-time validation of dbt model outputs

## Workaround

Until fixed, recommend:
1. **Disable dbt Integration**: Temporarily revert to mathematical calculations
2. **Parameter Audit**: Validate all growth/termination rate parameters
3. **Manual Validation**: Run single-year simulation with known parameters

## Next Steps

1. **Investigate Database Schema** - Determine where dbt models are actually writing
2. **Test dbt Model Output** - Query models directly to verify data
3. **Debug Integration Points** - Add logging to trace parameter flow
4. **Create Minimal Repro** - Isolate the specific failure point

## Impact Assessment

- **Severity**: Critical - Simulation results are completely unusable
- **Scope**: All workforce simulations using orchestrator_dbt
- **Business Impact**: Cannot produce reliable workforce planning outputs
- **Timeline**: Immediate fix required for system usability

## Related Files

- `orchestrator_dbt/core/workforce_needs_interface.py`
- `orchestrator_dbt/simulation/workforce_calculator.py`
- `orchestrator_dbt/simulation/event_generator.py`
- `orchestrator_dbt/multi_year/year_processor.py`
- `dbt/models/intermediate/int_workforce_needs.sql`
- `dbt/models/intermediate/int_workforce_needs_by_level.sql`

## Test Command Used

```bash
python run_multi_year.py
```

**Result**: Catastrophic inflation of hiring/termination numbers
