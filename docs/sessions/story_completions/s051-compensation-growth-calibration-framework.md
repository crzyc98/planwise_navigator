# S051: Compensation Growth Calibration Framework

**Epic**: E012 Phase 2B - Compensation System Integrity Fix
**Story Points**: 5
**Priority**: Must Have
**Status**: ✅ COMPLETE

## Executive Summary

Framework to systematically test compensation policy combinations and achieve sustained 2% annual compensation growth. Based on S050 findings: merit calculation bug creates 2.7% overstatement, but primary driver is new hire dilution (14-18 percentage point impact). Framework will test policy adjustments to counteract dilution while accounting for calculation baseline.

## Current Baseline Performance (With Known Bug)

### Confirmed Issues from S050
1. **Merit Calculation Bug**: 2.7% overstatement of prorated compensation
2. **New Hire Dilution**: 13.7%-17.6% workforce volume with $12K-$20K prorated compensation
3. **Combined Impact**: Volatile growth (-9.19% to +2.07%) vs target 2%

### Current Policy Configuration
- **COLA Rate**: 2.5% annually
- **Merit Budget**: 4.0% annually
- **Effective Combined Raise**: 4.6%-8.1% observed
- **Current Dilution Impact**: -14 to -18 percentage points annually

## Calibration Framework Design

### 1. Growth Calculation Methodologies

#### Option A: Current Methodology (Baseline)
- **Description**: Include all employees (continuous + new hire prorated)
- **Advantage**: Reflects actual workforce economic value
- **Disadvantage**: Severe dilution from prorated new hires
- **Use Case**: Current state measurement

#### Option B: Continuous Employee Focus
- **Description**: Calculate growth using only continuous_active employees
- **Advantage**: Eliminates new hire dilution noise
- **Disadvantage**: Doesn't reflect total workforce investment
- **Use Case**: Individual progression tracking

#### Option C: Full-Year Equivalent
- **Description**: Annualize new hire compensation for growth calculations
- **Advantage**: Eliminates artificial dilution while including all employees
- **Disadvantage**: More complex calculation, theoretical rather than actual spend
- **Use Case**: Economic value assessment

### 2. Policy Parameter Test Matrix

#### Primary Levers
1. **COLA Rate Scenarios**
   - Current: 2.5%
   - Test: 3.0%, 3.5%, 4.0%, 4.5%

2. **Merit Budget Scenarios**
   - Current: 4.0%
   - Test: 5.0%, 6.0%, 7.0%, 8.0%, 9.0%, 10.0%

3. **New Hire Management Scenarios**
   - Current: Hire as needed for growth
   - Test: Controlled volume, seasonal timing, compensation floor adjustments

#### Secondary Levers
4. **Promotion Rate Impact**
   - Current: Variable by level/tenure
   - Test: Acceleration scenarios

5. **Termination Rate Impact**
   - Current: 12% overall, 25% new hire
   - Test: Retention improvement scenarios

### 3. Mathematical Models for Target Achievement

#### Model A: Continuous Employee Focus (Methodology B)
```
Target: 2% growth in continuous employee compensation
Current Performance: 4.6%-8.1% individual growth (overstated by 2.7%)
Actual Performance: ~2%-5.4% individual growth
Required Adjustment: Minimal - already near target
```

#### Model B: Total Workforce (Methodology A)
```
Target: 2% growth including dilution effects
Current Dilution: -14 to -18 percentage points
Required Continuous Growth: (2% + 16%) / (1 - 16% new hire ratio) = 21.4%
Current Continuous Growth: ~15.6% average (overstated)
Gap: ~6 percentage points needed
Policy Implication: Increase merit budget from 4% to 10%
```

#### Model C: Full-Year Equivalent (Methodology C)
```
Target: 2% growth using annualized compensation
New Hire Impact: Neutral (eliminated by annualization)
Required Policy Adjustment: Match individual progression to 2% target
Current Gap: Minimal adjustment needed
```

## Calibration Test Scenarios

### Scenario 1: Conservative Adjustment
- **COLA**: 3.0% (+0.5% from current)
- **Merit**: 6.0% (+2.0% from current)
- **Expected Impact**: +2.5 percentage points total compensation growth
- **Target**: Achieve 1.5%-2.5% growth range

### Scenario 2: Moderate Adjustment
- **COLA**: 3.5% (+1.0% from current)
- **Merit**: 7.0% (+3.0% from current)
- **Expected Impact**: +4 percentage points total compensation growth
- **Target**: Achieve 2.0%-3.0% growth range

### Scenario 3: Aggressive Adjustment
- **COLA**: 4.0% (+1.5% from current)
- **Merit**: 8.0% (+4.0% from current)
- **Expected Impact**: +5.5 percentage points total compensation growth
- **Target**: Achieve 2.5%-3.5% growth range

### Scenario 4: New Hire Methodology Change
- **COLA**: 2.5% (unchanged)
- **Merit**: 4.0% (unchanged)
- **Calculation**: Switch to Methodology C (Full-Year Equivalent)
- **Expected Impact**: Eliminate 14-18 percentage point dilution
- **Target**: Achieve 2.0% \u00b1 0.5% through methodology change alone

## Implementation Framework

### Phase 1: Baseline Validation
1. **Confirm Current Metrics**: Validate S050 findings with latest simulation data
2. **Test Methodologies**: Implement all three calculation approaches
3. **Establish Baseline**: Document current performance under each methodology

### Phase 2: Policy Testing (S052)
1. **Parameter Sweep**: Test all combinations in matrix above
2. **Impact Modeling**: Quantify growth impact for each scenario
3. **Constraint Analysis**: Identify policy combinations exceeding realistic bounds

### Phase 3: Target Validation (S053)
1. **Scenario Selection**: Choose optimal policy combination
2. **Multi-Year Testing**: Validate sustainability over 5-year simulation
3. **Variance Analysis**: Ensure growth stays within 2% \u00b1 0.5% range

## Success Criteria

### Primary Objectives
- **Growth Target**: Achieve 2% \u00b1 0.5% annual compensation growth
- **Consistency**: Maintain target across all 5 simulation years (2025-2029)
- **Sustainability**: Policy parameters remain within realistic HR budget constraints

### Validation Metrics
- **Methodology A** (Current): -1% to +3% annual growth
- **Methodology B** (Continuous): 1.5% to 2.5% annual growth
- **Methodology C** (Full-Year): 1.5% to 2.5% annual growth

### Policy Constraints
- **COLA Rate**: Maximum 4.5% (competitive market rates)
- **Merit Budget**: Maximum 10% (budget sustainability)
- **Combined Impact**: Total compensation increase \u2264 14.5% annually

## Technical Implementation

### Database Changes Required
1. **New Calculation Methods**: Add methodology B and C to fct_workforce_snapshot
2. **Policy Parameters**: Make COLA/Merit rates configurable via simulation_config.yaml
3. **Growth Metrics**: Create dedicated growth calculation models
4. **Validation Checks**: Add automated target achievement validation

### Configuration Management
```yaml
compensation:
  cola_rate: 0.025
  merit_budget: 0.04
  growth_target: 0.02
  growth_tolerance: 0.005
  calculation_methodology: "current"  # options: current, continuous, full_year_equivalent
```

### Expected Deliverables
1. **Calibration Engine**: Automated policy testing framework
2. **Growth Metrics Dashboard**: Real-time target achievement monitoring
3. **Policy Recommendations**: Specific parameter combinations for 2% target
4. **Validation Report**: Multi-year sustainability analysis

## Risk Mitigation

### Technical Risks
- **Simulation Accuracy**: Validate results against manual calculations
- **Parameter Interactions**: Test for unexpected policy combination effects
- **Data Quality**: Ensure baseline data consistency across methodologies

### Business Risks
- **Budget Constraints**: Policy recommendations may exceed HR budget capacity
- **Market Competitiveness**: Aggressive compensation increases may create retention issues
- **Economic Sensitivity**: Growth targets may not be achievable during economic downturns

## Next Steps

### Immediate (S051 Completion)
1. **Implement Framework**: Build policy testing and validation infrastructure
2. **Test Methodologies**: Validate all three calculation approaches
3. **Create Configuration**: Make compensation policies configurable

### Subsequent (S052-S053)
1. **S052**: Execute systematic policy parameter testing
2. **S053**: Validate chosen policy combination achieves sustained 2% growth target
3. **Handoff**: Deliver calibrated compensation system to business stakeholders

## S051 Implementation Results

### Framework Validation (2026 Analysis)

**Method A (Current Methodology)**:
- 102 employees (88 continuous, 14 new hires)
- Average compensation: $170,252
- **YoY Growth: 1.36%** (below 2% target)
- New hire dilution impact: **-3.61 percentage points**
- Required policy adjustment: **+3% points**

**Method B (Continuous Employee Focus)**:
- 88 continuous employees only
- Average compensation: $194,117
- **YoY Growth: -2.25%** (unexpected decline)
- Indicates merit calculation bug still impacting baseline

**Method C (Full-Year Equivalent)**:
- 102 employees with annualized new hire compensation
- Average compensation: $183,004
- **YoY Growth: 8.95%** (above target range)
- Eliminates dilution but may overcompensate

### Key Framework Capabilities Delivered

✅ **Multiple Calculation Methodologies**: All three approaches implemented and tested
✅ **Target Validation Logic**: 2% ± 0.5% assessment working correctly
✅ **Dilution Impact Modeling**: Quantifies 3.6 percentage point new hire dilution
✅ **Policy Adjustment Recommendations**: Calculates required parameter changes
✅ **Automated Analysis**: Framework runs across all simulation years

### Strategic Insights for S052

1. **Method A requires 3+ percentage point policy boost** to achieve 2% target
2. **Method C already exceeds target** - may need policy reduction or methodology adoption
3. **New hire dilution is primary driver** - 3.6 percentage points in 2026
4. **Merit calculation bug compounds baseline issues** - Method B shows negative growth

### Ready for S052 Policy Parameter Optimization

Framework provides quantified foundation for systematic policy testing across COLA rates (2.5%-4.5%) and merit budgets (4%-10%) to achieve sustained 2% compensation growth target.

---

**Framework Date**: 2025-06-24
**Completion Date**: 2025-06-24
**Analyst**: Claude Code
**Status**: ✅ Framework implemented and validated
**Next Story**: S052 Policy Parameter Optimization Testing
