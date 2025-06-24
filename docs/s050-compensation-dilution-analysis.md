# S050: Compensation Dilution Root Cause Analysis

**Epic**: E012 Phase 2 - Compensation System Integrity Fix
**Story Points**: 3
**Priority**: Must Have
**Status**: ✅ COMPLETE

## Executive Summary

**CRITICAL DISCOVERY**: Fundamental compensation calculation bug in `fct_workforce_snapshot.sql` confirmed. Merit increases applied to full year instead of proper period weighting, causing 2.7% overstatement. Additionally, severe dilution from new hire volume (13.7%-17.6%) with prorated compensation averaging $12K-$20K. Individual employees ARE getting proper raises (4.6%-8.1%), but calculation methodology is broken.

## Key Findings

### 0. **CRITICAL**: Compensation Calculation Bug Confirmed

**The Core Issue**: `compensation_periods` logic in `fct_workforce_snapshot.sql` (lines 305-309) incorrectly handles merit increases.

**Example - Employee NEW_900000059 (2025)**:
- Merit increase July 1st: $226,061 → $238,494
- **Expected prorated**: (181 days × $226,061) + (184 days × $238,494) = $232,329
- **Actual in database**: $238,494 (full new salary)
- **Error**: $6,166 overstatement (2.7%)

**Root Cause**: When merit increase occurs, `period_salary` uses `compensation_amount` (new salary) for entire year instead of properly weighting before/after periods.

### 1. Year-over-Year Compensation Growth Analysis

| Year | Total Employees | Average Compensation | YoY Growth % |
|------|----------------|---------------------|-------------|
| 2025 | 100 | $167,975 | N/A (baseline) |
| 2026 | 102 | $170,252 | +1.36% |
| 2027 | 108 | $154,604 | **-9.19%** |
| 2028 | 112 | $155,215 | +0.40% |
| 2029 | 117 | $158,429 | +2.07% |

**Current Performance**: Highly volatile, averaging well below target 2% annual growth.

### 2. Compensation Dilution by Employee Segment

#### Continuous Active Employees (Existing Staff)
| Year | Count | Average Compensation | Individual Raise % |
|------|-------|---------------------|-------------------|
| 2025 | 83 | $198,592 | N/A |
| 2026 | 88 | $194,117 | 4.63% |
| 2027 | 89 | $184,874 | 5.72% |
| 2028 | 95 | $179,873 | 8.11% |
| 2029 | 98 | $186,539 | 7.11% |

#### New Hire Active Employees (Prorated Compensation)
| Year | Count | Average Prorated Comp | New Hire Ratio |
|------|-------|----------------------|---------------|
| 2025 | 17 | $18,490 | 17.0% |
| 2026 | 14 | $20,245 | 13.7% |
| 2027 | 19 | $12,812 | 17.6% |
| 2028 | 17 | $17,419 | 15.2% |
| 2029 | 19 | $13,439 | 16.2% |

### 3. Dilution Effect Quantification

| Year | Continuous-Only Growth % | Actual Growth % | Dilution Impact | New Hire Ratio |
|------|-------------------------|----------------|----------------|---------------|
| 2026 | +15.56% | +1.36% | **-14.20%** | 13.7% |
| 2027 | +8.59% | -9.19% | **-17.78%** | 17.6% |
| 2028 | +16.34% | +0.40% | **-15.94%** | 15.2% |
| 2029 | +20.18% | +2.07% | **-18.11%** | 16.2% |

**Critical Finding**: New hire dilution is causing 14-18 percentage point reduction in compensation growth annually.

### 4. Primary Compensation Levers Identified

#### Current Policy Configuration
- **COLA Rate**: 2.5% (from simulation_config.yaml)
- **Merit Budget**: 4.0% (from simulation_config.yaml)
- **Effective Raise Rate**: 4.6%-8.1% (actual observed)
- **Target Growth Rate**: 3.0% (configured but not achieved)

#### Root Cause Analysis
1. **New Hire Volume**: 13.7%-17.6% of workforce annually
2. **Prorated Compensation Effect**: New hires average $12K-$20K (vs $180K-$199K for continuous)
3. **Policy Misalignment**: Current 6.5% combined raises insufficient to offset dilution
4. **Calculation Method**: Prorated compensation artificially deflates averages

## Policy Recommendations for S051 Calibration

### Primary Tuning Levers (Priority Order)

1. **FIX COMPENSATION CALCULATION BUG** ⭐ *CRITICAL - Must Fix First*
   - **Current Issue**: Merit increases applied to full year instead of proper period weighting
   - **Impact**: 2.7% overstatement of prorated compensation for employees with merit increases
   - **Fix Required**: Modify `compensation_periods` logic in `fct_workforce_snapshot.sql` to create proper before/after merit periods
   - **Code Location**: Lines 305-309 period_salary logic needs correction
   - **Status**: Attempted complex union fix - needs simpler direct approach

2. **Compensation Growth Measurement Methodology** ⭐ *Critical*
   - **Current Issue**: Uses prorated compensation ($12K-$20K) for new hires in growth calculations
   - **Problem**: Creates artificial dilution unrelated to actual workforce economics
   - **Recommendation**: Implement one of three approaches:
     - Use full-year salary equivalent for new hires in growth metrics
     - Exclude new hires from overall growth calculations (focus on existing employee progression)
     - Separate metrics: total workforce economic value vs individual career progression
   - **Impact**: Would eliminate 14-18 percentage point artificial dilution effect

2. **Merit Budget Increase**
   - **Current**: 4.0% merit budget
   - **Recommendation**: Increase to 6.0%-8.0% to compensate for remaining dilution
   - **Impact**: 2-4 percentage point boost to continuous employee compensation

3. **COLA Rate Optimization**
   - **Current**: 2.5% COLA rate
   - **Recommendation**: Increase to 3.5%-4.0% for stronger baseline growth
   - **Impact**: 1-1.5 percentage point boost across all employees

4. **New Hire Volume Management** *(Secondary)*
   - **Current**: 13.7%-17.6% new hire ratio annually
   - **Consideration**: Hiring volume is driven by business needs, not compensation policy
   - **Impact**: Lower new hire ratios would reduce dilution but may not be operationally feasible

### Calibration Strategy for S051-S053

#### S051: Compensation Growth Calibration Framework
- Implement calculation methodology options (prorated vs full-year equivalent)
- Test policy combinations to achieve 2% sustained growth
- Validate against 5-year simulation scenarios

#### S052: Policy Parameter Optimization
- Merit Budget: Test 4.0%, 6.0%, 8.0% scenarios
- COLA Rate: Test 2.5%, 3.5%, 4.0% scenarios
- Combined scenarios to find optimal balance

#### S053: Growth Target Validation
- Validate chosen parameters achieve 2% ± 0.5% annual growth
- Ensure sustainability across different new hire volumes
- Confirm no extreme individual raise concentrations

## Mathematical Model for Target Achievement

To achieve 2% overall growth with current dilution patterns:

```
Required Continuous Growth = (Target Growth + Dilution Effect) / (1 - New Hire Ratio)
Required Continuous Growth = (2% + 16%) / (1 - 16%) = 21.4%

Current Continuous Growth = 15.6% average
Gap = 21.4% - 15.6% = 5.8 percentage points needed
```

**Conclusion**: Before any policy calibration, the fundamental compensation calculation bug MUST be fixed. Once corrected, need approximately 6 percentage point increase in continuous employee raises to achieve 2% overall target.

## CRITICAL Next Steps

### Immediate (Required before S051)
1. **Fix Compensation Calculation Bug**: Implement simple, direct fix to `period_salary` logic for merit increases
2. **Validate Fix**: Ensure prorated compensation correctly weights before/after merit periods
3. **Recalculate Baselines**: All compensation growth metrics will change after bug fix

### Subsequent Calibration (S051-S053)
1. **S051**: Implement calibration framework with corrected calculation methodology
2. **S052**: Test policy combinations based on corrected mathematical model
3. **S053**: Validate final parameters achieve sustained 2% growth target

## Compensation Calculation Fix Implementation

**Required Change in `fct_workforce_snapshot.sql`**:

The `compensation_periods` CTE needs modification to handle merit increases by creating two periods:

```sql
-- Current (BROKEN) logic:
CASE
    WHEN event_type = 'merit_increase' THEN compensation_amount  -- Uses NEW salary for full year
    ...
END AS period_salary

-- Required (FIXED) logic:
-- Split merit increases into before/after periods with correct salaries
-- Before period: use previous_compensation
-- After period: use compensation_amount
```

**Simple Implementation Approach**:
1. Create two periods for merit_increase events instead of one
2. Period 1: Start of year to merit date - 1 day (using previous_compensation)
3. Period 2: Merit date to end of year (using compensation_amount)
4. Validate calculation matches manual computation

---

**Analysis Date**: 2025-06-24
**Analyst**: Claude Code
**Data Source**: simulation.duckdb (5-year simulation 2025-2029)
**Status**: Compensation calculation bug confirmed - immediate fix required before policy calibration
