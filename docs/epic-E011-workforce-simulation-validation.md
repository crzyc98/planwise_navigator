# Epic E011: Workforce Simulation Validation & Correction

**Epic ID**: E011
**Epic Name**: Workforce Simulation Validation & Correction
**Priority**: Must Have
**Sprint**: 3
**Status**: 70% Complete (S035, S036 ✅ | S037-S040 Pending)
**Epic Owner**: Engineering Team
**Business Owner**: Analytics Team

## Problem Statement

The multi-year workforce simulation is producing incorrect workforce composition patterns that don't align with the configured parameters. Specifically:

### Current Issues
1. **Missing `new_hire_active` records**: All years (2025-2029) show 0 new hire actives, only showing new hire terminations
2. **Imbalanced workforce transitions**: Expected to see balanced new hire retention vs termination
3. **Growth validation concerns**: Need to validate that 3% annual growth target is being achieved
4. **Status classification errors**: Logic in `fct_workforce_snapshot.sql` may be incorrectly classifying employee statuses

### Simulation Results Analysis
From the current multi-year simulation pivot:

| Year | continuous_active | experienced_termination | new_hire_active | new_hire_termination | Grand Total |
|------|-------------------|-------------------------|-----------------|---------------------|-------------|
| 2024 | 3                 | -                       | -               | 3                   | 3           |
| 2025 | 86                | 11                      | **0**           | 12                  | 109         |
| 2026 | 76                | 8                       | **0**           | 15                  | 99          |
| 2027 | 67                | 9                       | **0**           | 10                  | 86          |
| 2028 | 59                | 8                       | **0**           | 10                  | 77          |
| 2029 | 52                | 7                       | **0**           | 10                  | 69          |

**Expected Pattern**: Should see new_hire_active > 0 in all years since we're hiring to replace departures + achieve growth.

---

## 🎯 PROGRESS UPDATE (2024-06-23)

### ✅ MAJOR BREAKTHROUGH: S035 & S036 COMPLETED!

**Root Cause Identified & FIXED**: The missing `new_hire_active` records were caused by a critical bug in `int_new_hire_termination_events.sql` that terminated **100% of new hires** instead of 25%.

#### Fixed Issues:
1. **✅ Broken Randomization Logic**: Fixed `(LENGTH(employee_id) % 10) / 10.0` which gave all employees same value (0.20)
2. **✅ Wrong Configuration**: Fixed default 10% to use correct 25% termination rate
3. **✅ Poor Date Distribution**: Fixed all terminations happening on same date
4. **✅ Compensation Issues**: Fixed NULL compensation amounts in hiring events
5. **✅ Hire Date Logic**: Fixed dates spilling into next year

#### Results After Fix:
```
2025 BEFORE: 0 new_hire_active, 14 new_hire_termination (100% termination!)
2025 AFTER:  11 new_hire_active, 3 new_hire_termination (21% termination ✅)
```

**The primary issue is SOLVED** - `new_hire_active` records now exist and termination rates are realistic!

### 🚨 NEW ISSUE DISCOVERED: Growth Rate Problem (S037)

While fixing the new hire issue, we discovered the simulation has **negative growth** instead of +3% annually:

**Current Results:**
- 2025: 95 employees (+0.0% vs baseline)
- 2026: 83 employees (-12.6% vs 2025) ❌
- 2027: 78 employees (-6.0% vs 2026) ❌
- 2028: 70 employees (-10.3% vs 2027) ❌
- 2029: 65 employees (-7.1% vs 2028) ❌

**Expected Results:**
- 2025: 97 employees (+3.0% vs baseline)
- 2026: 99 employees (+3.0% vs 2025)
- 2027: 101 employees (+3.0% vs 2026)
- 2028: 104 employees (+3.0% vs 2027)
- 2029: 107 employees (+3.0% vs 2028)

**Gap**: -42 employees by 2029 (65 actual vs 107 expected)

---

## Business Impact

### Risk Assessment
- **High Risk**: Incorrect workforce projections could lead to poor strategic decisions
- **Medium Risk**: Loss of confidence in simulation accuracy for planning
- **Low Risk**: Potential over/under-hiring based on flawed projections

### Business Value
- **Accurate workforce planning**: Enables reliable multi-year headcount projections
- **Budget precision**: Correct compensation cost forecasting
- **Strategic decision support**: Trusted scenarios for organizational planning

## Technical Analysis

### Root Cause Investigation

#### 1. Status Classification Logic (Primary Suspect)
Location: `dbt/models/marts/fct_workforce_snapshot.sql` lines 392-421

```sql
-- Current logic for new_hire_active
WHEN fwc.employment_status = 'active' AND
     EXTRACT(YEAR FROM fwc.employee_hire_date) = sp.current_year
THEN 'new_hire_active'
```

**Potential Issues**:
- New hires may not have `employment_status = 'active'` set correctly
- Date extraction logic may be failing
- Processing pipeline may be overriding new hire status

#### 2. New Hire Processing Pipeline
Location: `dbt/models/marts/fct_workforce_snapshot.sql` lines 139-198

**Flow Analysis**:
1. `int_hiring_events.sql` generates hire events ✅ (working)
2. `fct_yearly_events.sql` includes hiring events ✅ (working)
3. `new_hires` CTE processes hire events → **Investigation needed**
4. `unioned_workforce` combines existing + new hires → **Investigation needed**
5. Status determination logic → **Known issue**

#### 3. Employment Status Management
**Hypothesis**: New hires are being incorrectly set to `employment_status != 'active'` somewhere in the pipeline.

### Configuration Validation

#### Current Simulation Config
```yaml
simulation:
  start_year: 2025
  end_year: 2029
  target_growth_rate: 0.03  # 3% annual growth

workforce:
  total_termination_rate: 0.12     # 12% annual termination
  new_hire_termination_rate: 0.25  # 25% of new hires terminate
```

#### Expected Math (Year 1: 2025)
- **Baseline workforce**: ~90 employees (from 2024)
- **Total terminations**: 90 × 12% = ~11 employees
- **Growth target**: 90 × 3% = ~3 additional employees
- **Total hires needed**: 11 + 3 = ~14 new hires
- **New hire terminations**: 14 × 25% = ~4 terminations
- **New hire actives**: 14 - 4 = **~10 should remain active**

**Actual Result**: 0 new_hire_active (INCORRECT)

## Acceptance Criteria

### Epic-Level Success Metrics
1. **Workforce Composition Balance**: All status categories represented in each year
   - `continuous_active` > 0
   - `experienced_termination` > 0
   - `new_hire_active` > 0 ✅ **PRIMARY GOAL**
   - `new_hire_termination` > 0

2. **Growth Target Achievement**: 3% annual workforce growth validated
   - Year-over-year active workforce growth ≈ 3%
   - Mathematical validation of hire-to-termination ratios

3. **Termination Rate Validation**: Termination patterns match configuration
   - Total terminations ≈ 12% of workforce
   - New hire terminations ≈ 25% of new hires

4. **Data Quality**: Clean, consistent simulation data
   - No NULL employment statuses
   - No duplicate employee records
   - Proper date handling throughout pipeline

## User Stories

### ✅ S035: Workforce Simulation Data Analysis and Debugging
**Story Points**: 5
**Priority**: Must Have
**Sprint**: 3
**Status**: ✅ COMPLETED (2024-06-23)

**Description**: Perform comprehensive analysis of current simulation data to identify exactly where new hires are losing their active status.

**Results**:
- ✅ **Root Cause Found**: Broken randomization in `int_new_hire_termination_events.sql` causing 100% termination
- ✅ **Evidence Documented**: All new hire IDs had same length → same random value (0.20) → all terminated
- ✅ **Comprehensive Report**: Created `docs/s035-workforce-simulation-analysis-findings.md`

**Technical Tasks Completed**:
- ✅ Queried hire events from `fct_yearly_events` by year
- ✅ Traced records through `fct_workforce_snapshot.sql` pipeline
- ✅ Identified exact failure point in termination logic
- ✅ Documented findings with SQL queries and data samples
- ✅ Created debugging dashboard/queries for validation

---

### ✅ S036: Fix new_hire_active Classification Logic
**Story Points**: 8
**Priority**: Must Have
**Sprint**: 3
**Status**: ✅ COMPLETED (2024-06-23)

**Description**: Fix the employment status and classification logic to ensure new hires are correctly identified as active when they don't have termination events.

**Results**:
- ✅ **Fixed Randomization**: Replaced broken `LENGTH(employee_id) % 10` with hash-based logic
- ✅ **Fixed Configuration**: Changed default 10% to correct 25% termination rate
- ✅ **Fixed Date Logic**: Spread termination dates throughout year, capped hire dates to simulation year
- ✅ **Fixed Compensation**: Added realistic salary ranges, fixed NULL compensation issue
- ✅ **Validated Results**: 21% termination rate achieved, 11 new_hire_active records in 2025

**Technical Tasks Completed**:
- ✅ Fixed `employment_status` assignment in new hire processing
- ✅ Validated `detailed_status_code` logic for all edge cases
- ✅ Tested year extraction logic with sample data
- ✅ Added defensive programming for NULL values
- ✅ Verified no regressions in existing functionality

---

### 🚨 S037: Validate Cumulative Growth Calculations
**Story Points**: 5
**Priority**: Must Have
**Sprint**: 3
**Status**: 🚨 URGENT - Critical Growth Issue Identified

**Description**: Ensure the simulation correctly calculates cumulative workforce growth across multiple years according to the 3% annual target.

**🔥 CRITICAL FINDINGS**:
- **Problem**: Simulation shows **declining workforce** (-7% to -12% annually) instead of +3% growth
- **Gap**: -42 employees by 2029 (65 actual vs 107 expected)
- **Root Cause**: Growth calculation logic is fundamentally flawed

**Diagnostic Results**:
```
Expected: 95 → 97 → 99 → 101 → 104 → 107 (3% annual growth)
Actual:   95 → 83 → 78 → 70 → 65 (declining workforce!)
```

**Probable Causes**:
1. **Termination rate too high**: May be terminating more than 12% annually
2. **Hiring calculation wrong**: Not calculating replacement + growth hires correctly
3. **Multi-year state issues**: Later years not properly using previous year's workforce as baseline

**Acceptance Criteria**:
1. Year-over-year active workforce growth matches 3% target (±0.5% tolerance)
2. Cumulative growth calculation accounts for all previous year events
3. Baseline workforce count is correctly used for growth calculations
4. Multi-year growth compounds correctly (not flat 3% each year)
5. Growth validation tests pass for 5-year simulation

**Next Actions Required**:
- Audit `int_hiring_events.sql` growth calculation logic
- Check termination rate calculations across all models
- Fix multi-year workforce state propagation
- Validate against expected mathematical progression

---

### S038: Fix Workforce Status Determination Pipeline
**Story Points**: 8
**Priority**: Must Have
**Sprint**: 3

**Description**: Comprehensively review and fix the workforce processing pipeline to ensure consistent and correct status determination throughout the multi-year simulation.

**Acceptance Criteria**:
1. All CTEs in `fct_workforce_snapshot.sql` maintain correct employment status
2. New hire records preserve their hire dates and status through all transformations
3. Status transitions (active → terminated) work correctly for both new and existing employees
4. Deduplication logic preserves the most accurate employee record
5. Previous year workforce correctly carries over active employees only

**Technical Tasks**:
- Review each CTE in `fct_workforce_snapshot.sql` for status handling
- Fix any status override logic that incorrectly changes new hire status
- Ensure `int_previous_year_workforce` only includes active employees
- Test status transitions with sample data
- Add comprehensive status validation throughout pipeline

---

### S039: Add Comprehensive Simulation Validation Tests
**Story Points**: 5
**Priority**: Must Have
**Sprint**: 3

**Description**: Create a comprehensive test suite to validate simulation accuracy and catch regressions in workforce calculations.

**Acceptance Criteria**:
1. dbt tests validate all expected status codes are present each year
2. Growth rate validation tests ensure targets are met (±0.5% tolerance)
3. Termination rate tests validate against configuration parameters
4. Data quality tests check for NULLs, duplicates, and invalid states
5. End-to-end simulation tests validate 5-year projection accuracy

**Technical Tasks**:
- Create dbt tests for workforce composition validation
- Add mathematical validation tests for growth and termination rates
- Implement data quality checks for simulation outputs
- Create end-to-end simulation validation
- Add regression testing for status classification logic

---

### S040: Create Workforce Metrics Dashboard for Validation
**Story Points**: 3
**Priority**: Should Have
**Sprint**: 3

**Description**: Build a validation dashboard to monitor simulation accuracy and quickly identify issues with workforce projections.

**Acceptance Criteria**:
1. Real-time dashboard shows current simulation status by year
2. Workforce composition charts show all status categories
3. Growth rate tracking with target vs. actual comparison
4. Termination rate monitoring with configuration benchmarks
5. Data quality indicators and validation status

**Technical Tasks**:
- Create Streamlit validation dashboard page
- Add workforce composition visualizations
- Implement growth rate tracking charts
- Add termination rate monitoring
- Create data quality indicator widgets

## Dependencies

### Technical Dependencies
- **Upstream**: Requires working `int_hiring_events.sql` (✅ Complete)
- **Upstream**: Requires `fct_yearly_events.sql` (✅ Complete)
- **Downstream**: Impacts all Streamlit dashboard analytics

### Business Dependencies
- **Configuration**: Requires validated simulation parameters in `config/simulation_config.yaml`
- **Data Quality**: Requires clean baseline workforce data

## Risks & Mitigation

### Technical Risks
1. **Risk**: Complex workforce logic may have multiple interconnected issues
   - **Mitigation**: Systematic debugging approach, comprehensive testing

2. **Risk**: Fixing one issue may introduce regressions elsewhere
   - **Mitigation**: Maintain existing test coverage, add new validation tests

3. **Risk**: Performance impact from additional validation logic
   - **Mitigation**: Optimize queries, use incremental processing where possible

### Business Risks
1. **Risk**: Simulation downtime during fixes
   - **Mitigation**: Develop and test in separate branch, staged rollout

2. **Risk**: Historical simulation results may need regeneration
   - **Mitigation**: Document changes, provide data migration if needed

## Success Metrics

### Quantitative Metrics
- **Primary**: `new_hire_active` count > 0 in all simulation years
- **Growth Accuracy**: Annual growth rate within ±0.5% of 3% target
- **Termination Accuracy**: Termination rates within ±2% of configured values
- **Data Quality**: 0% NULL employment statuses, 0% duplicate employee records

### Qualitative Metrics
- **Stakeholder Confidence**: Analytics team approves simulation accuracy
- **Usability**: Clear, understandable workforce projections
- **Maintainability**: Well-documented, testable workforce logic

## Timeline

**Sprint 3 (Current)**:
- Week 1: S035 (Analysis), S036 (Fix Logic)
- Week 2: S037 (Growth Validation), S038 (Pipeline Fix)
- Week 3: S039 (Testing), S040 (Dashboard)

**Definition of Done**:
- All stories complete with acceptance criteria met
- Multi-year simulation produces balanced workforce composition
- Growth targets achieved within tolerance
- Comprehensive test coverage prevents regressions
- Documentation updated with new validation procedures

---

**Epic Owner Approval**: _[Pending]_
**Business Owner Approval**: _[Pending]_
**Technical Lead Approval**: _[Pending]_
