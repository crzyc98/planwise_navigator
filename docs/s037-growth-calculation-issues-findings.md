# S037: Growth Calculation Issues - Critical Findings Report

**Story**: S037 - Validate cumulative growth calculations
**Date**: 2024-06-23
**Status**: 🚨 CRITICAL ISSUE IDENTIFIED
**Previous Stories**: S035 ✅ S036 ✅ (new hire active issue SOLVED)

## Executive Summary

**CRITICAL ISSUE**: While S035/S036 successfully fixed the missing `new_hire_active` records, the multi-year simulation reveals a **fundamental growth calculation problem**. The workforce is **declining** by 7-12% annually instead of growing by the target 3%.

### Impact Assessment
- **Gap by 2029**: -42 employees (65 actual vs 107 expected)
- **Business Risk**: HIGH - Workforce projections are completely wrong
- **Urgency**: CRITICAL - This affects all strategic planning decisions

## Detailed Analysis

### Expected vs Actual Results

**Target Growth Pattern (3% annually from 95 baseline):**
```
2025: 97 employees (+3.0%)
2026: 99 employees (+3.0%)
2027: 101 employees (+3.0%)
2028: 104 employees (+3.0%)
2029: 107 employees (+3.0%)
```

**Actual Results:**
```
2025: 95 employees (+0.0% vs baseline)
2026: 83 employees (-12.6% vs 2025) ❌
2027: 78 employees (-6.0% vs 2026) ❌
2028: 70 employees (-10.3% vs 2027) ❌
2029: 65 employees (-7.1% vs 2028) ❌
```

**Cumulative Gap**: 65 actual vs 107 expected = **-39% shortfall**

### Hiring vs Termination Analysis

**Hiring Patterns by Year:**
```
2025: 14 hires, 3 new hire terminations, 79% retention
2026: 14 hires, 5 new hire terminations, 64% retention
2027: 12 hires, 3 new hire terminations, 75% retention
2028: 10 hires, 2 new hire terminations, 80% retention
2029: 10 hires, 3 new hire terminations, 70% retention
```

**Observable Issues:**
1. **Hiring counts are declining** (14 → 10) instead of increasing with workforce size
2. **Net hiring is insufficient** to replace departures + achieve growth
3. **Multi-year calculations** don't properly compound growth

### Root Cause Hypotheses

#### 1. Baseline Workforce Issue
- **Problem**: 2024 shows only 3 employees vs baseline 95 employees
- **Impact**: First year calculation may be using wrong baseline
- **Evidence**: Massive jump from 3 to 95 in 2025 suggests baseline confusion

#### 2. Termination Rate Miscalculation
- **Target**: 12% of workforce should terminate annually
- **Reality**: May be terminating more than expected
- **Evidence**: Declining workforce suggests terminations > hires

#### 3. Growth Calculation Logic Error
- **Expected Math**: hires = departures + (workforce × 3% growth)
- **Suspected Issue**: Growth calculation not accounting for proper workforce size
- **Evidence**: Hiring counts declining when they should increase

#### 4. Multi-Year State Propagation
- **Problem**: Later years may not properly inherit previous year's workforce
- **Evidence**: Each year seems to restart from incorrect baseline
- **Impact**: Cumulative growth impossible if state isn't carried forward

## Technical Investigation Areas

### Files to Investigate

1. **`int_hiring_events.sql`** (lines 16-50):
   - Previous year workforce count calculation
   - Growth target application
   - Total hires needed calculation

2. **`int_termination_events.sql`**:
   - Termination rate application
   - Workforce base for termination calculation

3. **`orchestrator/simulator_pipeline.py`** (lines 770-934):
   - Multi-year state management
   - Previous year data propagation

4. **`int_previous_year_workforce.sql`**:
   - Year-to-year workforce transition logic

### Diagnostic Queries for Next Session

```sql
-- Check baseline vs 2024 workforce
SELECT 'baseline' as source, COUNT(*) as count
FROM int_baseline_workforce WHERE employment_status = 'active'
UNION ALL
SELECT '2024' as source, COUNT(*) as count
FROM fct_workforce_snapshot WHERE simulation_year = 2024 AND employment_status = 'active';

-- Analyze termination rates by year
SELECT
    simulation_year,
    COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as terminations,
    LAG(COUNT(CASE WHEN ws.employment_status = 'active' THEN 1 END)) OVER (ORDER BY simulation_year) as prev_workforce,
    COUNT(CASE WHEN event_type = 'termination' THEN 1 END) * 1.0 /
    LAG(COUNT(CASE WHEN ws.employment_status = 'active' THEN 1 END)) OVER (ORDER BY simulation_year) as actual_term_rate
FROM fct_yearly_events ye
LEFT JOIN fct_workforce_snapshot ws ON ye.simulation_year = ws.simulation_year - 1
GROUP BY simulation_year;

-- Check hiring calculation logic
SELECT
    simulation_year,
    COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as actual_hires,
    -- Expected hires = terminations + growth
    COUNT(CASE WHEN event_type = 'termination' THEN 1 END) +
    ROUND(LAG(active_count) OVER (ORDER BY simulation_year) * 0.03) as expected_hires
FROM (
    SELECT simulation_year, COUNT(*) as active_count
    FROM fct_workforce_snapshot
    WHERE employment_status = 'active'
    GROUP BY simulation_year
) ws
JOIN fct_yearly_events ye USING (simulation_year)
GROUP BY simulation_year, active_count;
```

## Recommended Fix Strategy

### Phase 1: Baseline Correction
1. **Investigate baseline source**: Determine if 95 or 3 is correct starting point
2. **Fix 2024 vs baseline confusion**: Ensure consistent starting workforce
3. **Validate first year calculation**: 2025 should start from correct baseline

### Phase 2: Growth Math Audit
1. **Review `int_hiring_events.sql`**: Verify growth calculation logic
2. **Check termination rate application**: Ensure 12% rate is correctly applied
3. **Validate net growth formula**: hires - terminations = target growth

### Phase 3: Multi-Year State Fix
1. **Review `int_previous_year_workforce.sql`**: Ensure proper state propagation
2. **Fix Dagster pipeline**: Verify year-to-year data flow
3. **Test cumulative growth**: Validate 5-year progression

### Phase 4: Validation
1. **Mathematical verification**: Expected vs actual at each step
2. **End-to-end testing**: Full 5-year simulation validation
3. **Regression testing**: Ensure S035/S036 fixes remain intact

## Success Criteria

**Primary Goals:**
- [ ] Each year shows +3% growth (±0.5% tolerance)
- [ ] 2029 workforce ≈ 107 employees (not 65)
- [ ] Hiring counts increase with workforce size
- [ ] Termination rates stay around 12% annually

**Validation Metrics:**
- [ ] Cumulative 5-year growth ≈ 15.9% (95 → 107)
- [ ] Net hiring = departures + growth each year
- [ ] Multi-year state properly propagates
- [ ] All previous fixes (S035/S036) remain working

## Files Modified in Previous Stories

**S035/S036 Fixes (DO NOT BREAK):**
- ✅ `int_new_hire_termination_events.sql` - Fixed randomization logic
- ✅ `int_hiring_events.sql` - Fixed compensation and date logic

**Files to Modify in S037:**
- 🎯 `int_hiring_events.sql` - Growth calculation logic
- 🎯 `int_termination_events.sql` - Termination rate application
- 🎯 `int_previous_year_workforce.sql` - Multi-year state management
- 🎯 Review Dagster pipeline configuration

## Next Session Priority

1. **Start with diagnostic queries** to understand exact math failure
2. **Focus on `int_hiring_events.sql`** - likely source of growth calculation error
3. **Validate baseline workforce** - resolve 2024 vs baseline confusion
4. **Test incrementally** - fix one year at a time to avoid breaking S035/S036

---

**Session Status**: Ready for S037 implementation
**Prerequisites**: Database contains working S035/S036 fixes
**Key Files**: Located in `/Users/nicholasamaral/planwise_navigator/dbt/models/intermediate/events/`
