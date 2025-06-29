# Compensation Growth Calibration Results - June 28, 2025

## Executive Summary

After implementing the S050 calibration recommendations, we achieved a **-1.62% compensation growth** vs the **+2.0% target**, missing by 3.62 percentage points. While this is an improvement from the baseline -3.7% growth, additional measures are needed.

## Calibration Applied

Based on S050 analysis recommendations:
- **COLA Rate**: Increased from 2.5% to 4.0% (+1.5%)
- **Merit Rates**: Increased by +1.0% across all levels
  - Level 1: 3.5% → 4.5%
  - Level 2: 4.0% → 5.0%
  - Level 3: 4.5% → 5.5%
  - Level 4: 5.0% → 6.0%
  - Level 5: 5.5% → 6.5%

## Results Analysis

### Year-over-Year Growth Rates
- 2025 Average Salary: $161,395
- 2026 Average Salary: $158,780
- **Growth Rate: -1.62%** (Target: +2.0%)

### Root Cause: New Hire Dilution Persists
- **Existing Employees (2026)**: 4,032 employees at $166,478 average
- **New Hires (2026)**: 607 employees at $107,644 average
- **Compensation Gap**: $58,834 (35% differential)
- **Hiring Volume**: 809 new hires (17% of workforce)

### Impact Breakdown
- Calibration Improvement: +2.08% (from -3.7% to -1.62%)
- Remaining Gap to Target: -3.62%

## Recommendations for Achieving 2% Target

### Option 1: Further Increase Compensation Policies
To counteract the dilution and achieve 2% growth, consider:
- **COLA**: Increase to 5.5% (+1.5% additional)
- **Merit**: Add another +1.5% across all levels
- **Total Policy Impact**: ~+3.0% additional growth

### Option 2: Address New Hire Compensation Gap
- Increase starting salaries for new hires by 15-20%
- Implement market-based hiring bands
- Reduce compensation gap from 35% to 20%

### Option 3: Moderate Hiring Growth
- Reduce new hire volume from 809 to ~600 annually
- Focus on retention to reduce replacement hiring
- Improve promotion-from-within programs

### Option 4: Targeted Compensation Strategy
- Larger increases for high-tenure employees
- Retention bonuses for critical roles
- Performance-based differentiation

## Technical Implementation Notes

### Parameter System Working Correctly
- Dynamic parameter lookup via `get_parameter_value()` macro
- Parameters properly loaded from `comp_levers.csv`
- Audit trail maintained in `fct_yearly_events`

### How to Apply Further Calibration
1. Update `dbt/seeds/comp_levers.csv` with new rates
2. Run `dbt seed --select comp_levers`
3. Run `dbt run --select stg_comp_levers int_effective_parameters`
4. Execute `multi_year_simulation` job in Dagster

## Next Steps

1. **Business Decision Required**: Which option(s) to pursue for closing the 3.62% gap
2. **Sensitivity Analysis**: Test combinations of policy changes
3. **Budget Impact**: Calculate cost implications of each option
4. **Implementation Timeline**: Phase in changes over 2-3 years if needed

## Conclusion

The parameter tuning system is working as designed. The calibration improved growth by 2.08%, but the new hire dilution effect (-5.7% impact) requires more aggressive intervention to achieve the 2% target. The system is ready for additional parameter adjustments once business decisions are made.
