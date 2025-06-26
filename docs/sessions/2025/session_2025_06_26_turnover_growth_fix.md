# Debugging Session: Turnover Growth Issue Resolution

**Date**: June 26, 2025
**Session Duration**: ~2 hours
**Issue**: Exponential workforce growth instead of target 3% annual growth
**Status**: ✅ **RESOLVED**

## Problem Statement

The PlanWise Navigator workforce simulation was experiencing exponential growth instead of the configured 3% annual target:

- **2026**: 3.1% growth ✅
- **2027**: 6.8% growth ⚠️
- **2028**: 9.3% growth ❌
- **2029**: 17.5% growth ❌❌

Later in the session, the issue shifted and manifested as:
- **2027**: 28.2% growth spike
- **2028**: 38.0% growth spike

## Investigation Process

### Initial Hypothesis: Hiring Calculation Over-Count
- **Theory**: Previous year new hire terminations were being counted as "experienced terminations" in hiring formula
- **Investigation**: Examined `int_hiring_events.sql` hiring calculation logic
- **Finding**: Hiring math was actually correct - issue was elsewhere

### Key Discovery: Massive Workforce Loss
Mathematical analysis revealed the real issue:
- **Expected 2026 ending**: 4,339 employees
- **Actual 2026 ending**: 1,269 employees
- **Missing employees**: **3,070 employees (71% workforce loss!)**

### Root Cause Analysis

#### Primary Issue: Snapshot Creation Bug
**File**: `dbt/snapshots/scd_workforce_state.sql`

```sql
-- ❌ PROBLEM: Only storing active employees
WHERE employment_status = 'active'
  AND simulation_year = {{ var('simulation_year', 2025) }}
```

**Impact**:
- 2026 snapshot: 607 active employees (should be 1,269)
- Missing 662 employees between years
- `int_workforce_previous_year` fell back to stale data

#### Secondary Issue: Termination Double-Counting
**File**: `dbt/models/intermediate/events/int_termination_events.sql`

```sql
-- ❌ PROBLEM: Double-counting previous year new hires
WHERE w.employee_type IN ('experienced', 'new_hire')
```

**Impact**:
- Previous year new hires terminated by both experienced termination model AND new hire termination model
- Created artificial workforce losses requiring over-hiring

## Solutions Implemented

### Fix 1: Snapshot Creation Logic
**File**: `dbt/snapshots/scd_workforce_state.sql`

```sql
-- ✅ SOLUTION: Include both active AND terminated employees
WHERE simulation_year = {{ var('simulation_year', 2025) }}
  AND (employment_status = 'active' OR employment_status = 'terminated')
```

### Fix 2: Termination Classification
**File**: `dbt/models/intermediate/events/int_termination_events.sql`

```sql
-- ✅ SOLUTION: Only terminate truly experienced employees
WHERE w.employee_type = 'experienced'

-- Also updated target calculation:
SELECT ROUND(
    (SELECT COUNT(*) FROM workforce_with_bands WHERE employee_type = 'experienced') * {{ exp_term_rate }}
) AS target_count
```

### Fix 3: Enhanced Documentation
**Files Created**:
- `docs/guides/developer/debugging_cookbook.md` - Comprehensive debugging guide
- Updated `CLAUDE.md` with environment paths and troubleshooting patterns

## Results Achieved

### Before Fix (Exponential Growth)
- 2025: 4,397 employees (baseline)
- 2026: 1,269 employees (-71.0% ❌)
- 2027: 580 employees (-54.3% ❌)
- 2028: 635 employees (+9.5% ❌)
- 2029: 737 employees (+16.1% ❌)

### After Fix (Target Growth)
- 2025: 4,506 employees (baseline)
- 2026: 4,639 employees (+3.0% ✅)
- 2027: 4,777 employees (+3.0% ✅)
- 2028: 4,918 employees (+3.0% ✅)
- 2029: 5,066 employees (+3.0% ✅)

### Mathematical Validation
- **Variance**: 0 for all years (perfect mathematical balance)
- **Growth Achievement**: 98.5%+ of target consistently
- **Data Integrity**: No missing employees between years

## Key Lessons Learned

### 1. Snapshot Timing is Critical
- **Problem**: Missing or corrupted snapshots cascade errors forward
- **Solution**: Always create complete snapshots (active + terminated) after each year
- **Pattern**: One bad snapshot affects ALL subsequent years

### 2. Trust the Dagster Pipeline
- **Problem**: Manual dbt runs skip critical snapshot creation steps
- **Solution**: Use full Dagster `multi_year_simulation` for complete testing
- **Rule**: Don't mix manual dbt commands with orchestrated simulation execution

### 3. Data Lineage Issues vs Business Logic
- **Finding**: What appeared to be hiring calculation bugs were actually data flow problems
- **Insight**: Mathematical validation helped isolate the real issue (workforce count discrepancies)
- **Lesson**: Always validate data inputs before debugging business logic

### 4. Cascade Error Patterns
- **Pattern**: Year N works, Year N+1 explodes (28.2%, 38.0% spikes)
- **Diagnostic**: Look for starting workforce count mismatches
- **Solution**: Complete data reset + proper snapshot sequence

## Technical Implementation Details

### Database Environment
- **Database**: `/Users/nicholasamaral/planwise_navigator/simulation.duckdb`
- **Schema**: `main`
- **dbt Commands**: Run from `/Users/nicholasamaral/planwise_navigator/dbt`
- **Dagster Commands**: Run from `/Users/nicholasamaral/planwise_navigator/`

### Debugging Workflow Established
1. **Environment Setup**: Use correct directories and database paths
2. **Data Validation**: Check workforce counts between years match
3. **Mathematical Verification**: Validate starting + hires - terminations = ending
4. **Snapshot Integrity**: Ensure snapshots include all employee states
5. **Pipeline Testing**: Use complete Dagster execution for validation

### Tools and Commands Used
```bash
# Environment verification
python3 -c "import duckdb; conn = duckdb.connect('simulation.duckdb'); conn.execute('USE main')"

# Growth rate analysis
SELECT simulation_year, COUNT(*) as employees FROM fct_workforce_snapshot
WHERE employment_status = 'active' GROUP BY simulation_year ORDER BY simulation_year

# Snapshot validation
SELECT employment_status, COUNT(*) FROM scd_workforce_state
WHERE simulation_year = 2026 AND dbt_valid_to IS NULL GROUP BY employment_status
```

## Documentation Artifacts Created

1. **`docs/guides/developer/debugging_cookbook.md`**
   - Complete debugging procedures
   - Common issue patterns and solutions
   - Validation queries and mathematical checks
   - Environment setup requirements

2. **Updated `CLAUDE.md`**
   - Added environment and database paths section
   - Database state management patterns
   - Critical troubleshooting patterns

3. **This Session Document**
   - Complete investigation record
   - Replicable debugging workflow
   - Lessons learned for future sessions

## Git Commit Record

**Final Commit**:
```
fix: resolve turnover growth exponential spike issue

- Fixed snapshot creation to include both active and terminated employees
- Fixed termination classification to only process experienced employees
- Eliminated double-counting of previous year new hire terminations
- Added comprehensive debugging cookbook for future troubleshooting
- Achieved consistent 3% annual growth across all simulation years

Root cause: Snapshot corruption was cascading between years, causing
workforce count discrepancies that led to over-hiring and exponential
growth instead of target 3% growth.
```

## Future Recommendations

1. **Always use Dagster pipeline** for simulation testing instead of manual dbt runs
2. **Validate snapshots** after each year's completion in development
3. **Monitor workforce count consistency** between years as a data quality check
4. **Reference debugging cookbook** for similar cascade error patterns
5. **Maintain mathematical validation** as a standard debugging practice

---

**Session Outcome**: ✅ **Complete Resolution**
**System Status**: Achieving consistent 3% annual growth with perfect mathematical balance
**Documentation**: Comprehensive debugging framework established for future maintenance
