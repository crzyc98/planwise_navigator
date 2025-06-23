# Claude Code Handoff Prompt - Workforce Simulation Project

## Context for New Session

I'm working on **Epic E011: Workforce Simulation Validation & Correction** for PlanWise Navigator, a workforce simulation platform.

### 🎯 Current Status

**✅ MAJOR SUCCESS:** Stories S035 and S036 are COMPLETE!
- **Problem SOLVED**: Missing `new_hire_active` records (was 0, now 11+ per year)
- **Root Cause FIXED**: Broken randomization logic that terminated 100% of new hires
- **Validation**: New hire termination rate now 21-25% (target: 25%) ✅

**🚨 NEW CRITICAL ISSUE:** Story S037 needs immediate attention
- **Problem**: Workforce declining 7-12% annually instead of growing 3%
- **Impact**: 42-employee shortfall by 2029 (65 actual vs 107 expected)
- **Urgency**: This affects all strategic workforce planning

### 📋 Next Priority: Story S037

**Task**: Fix cumulative growth calculations to achieve 3% annual workforce growth

**Current Results (WRONG):**
```
2025: 95 employees (+0.0%)
2026: 83 employees (-12.6%) ❌
2027: 78 employees (-6.0%) ❌
2028: 70 employees (-10.3%) ❌
2029: 65 employees (-7.1%) ❌
```

**Expected Results:**
```
2025: 97 employees (+3.0%)
2026: 99 employees (+3.0%)
2027: 101 employees (+3.0%)
2028: 104 employees (+3.0%)
2029: 107 employees (+3.0%)
```

### 🔍 Investigation Areas

**Likely Root Causes:**
1. **Growth calculation logic** in `dbt/models/intermediate/events/int_hiring_events.sql`
2. **Termination rate miscalculation** - may be terminating more than 12% annually
3. **Multi-year state propagation** - later years not using correct previous workforce
4. **Baseline confusion** - 2024 shows 3 employees vs baseline 95

**Key Files to Check:**
- `dbt/models/intermediate/events/int_hiring_events.sql` (growth calculation)
- `dbt/models/intermediate/events/int_termination_events.sql` (termination rates)
- `dbt/models/intermediate/int_previous_year_workforce.sql` (year transitions)

### 📚 Reference Documents

**Epic Overview**: `@docs/epic-E011-workforce-simulation-validation.md`
**S037 Detailed Findings**: `@docs/s037-growth-calculation-issues-findings.md`
**S035 Analysis**: `@docs/s035-workforce-simulation-analysis-findings.md`
**Project Backlog**: `@docs/backlog.csv`
**System Config**: `@config/simulation_config.yaml`

### 🛠️ Technical Context

**Database**: DuckDB at `/Users/nicholasamaral/planwise_navigator/simulation.duckdb`
**dbt Models**: `/Users/nicholasamaral/planwise_navigator/dbt/models/`
**Current Data**: Contains S035/S036 fixes - DO NOT BREAK existing new_hire_active functionality

**Configuration**:
- Target growth: 3% annually
- Termination rate: 12% annually
- New hire termination: 25%
- Years: 2025-2029
- Baseline workforce: 95 employees

### 🎯 Success Criteria for S037

1. **Growth Rate**: Each year shows ~3% workforce growth (±0.5% tolerance)
2. **2029 Target**: ~107 active employees (currently 65)
3. **Math Validation**: Hires = departures + (workforce × 3% growth)
4. **Preserve S035/S036**: Keep new_hire_active records working (11+ per year)

### 🚨 Important Notes

- **DO NOT** modify `int_new_hire_termination_events.sql` - it's working correctly now
- **START WITH** diagnostic queries to understand the math failure
- **FOCUS ON** `int_hiring_events.sql` growth calculation logic first
- **TEST INCREMENTALLY** - validate each year before proceeding to next

### 📊 Quick Diagnostic

To verify current state, run:
```sql
-- Check workforce by year
SELECT simulation_year, COUNT(*) as total,
       COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active,
       COUNT(CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 END) as new_hire_active
FROM fct_workforce_snapshot
GROUP BY simulation_year ORDER BY simulation_year;
```

Expected results should show new_hire_active > 0 for most years (S035/S036 success) but declining total workforce (S037 problem).

---

## Recommended Approach

1. **Validate Current State**: Confirm S035/S036 fixes are still working
2. **Run Diagnostics**: Use queries from `s037-growth-calculation-issues-findings.md`
3. **Focus on Growth Math**: Review hiring calculation logic in `int_hiring_events.sql`
4. **Fix Incrementally**: Test one year at a time to avoid regressions
5. **Validate Results**: Ensure 3% annual growth is achieved

Ready to continue with Story S037 to fix the growth calculation issues!
