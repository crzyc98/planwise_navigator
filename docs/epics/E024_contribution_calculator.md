# Epic E024: Contribution Calculator with IRS Limits

## Epic Overview

### Summary
Build a high-performance vectorized contribution calculation engine that computes employee deferrals and employer contributions for 100K+ employees while enforcing all applicable IRS limits and plan-specific rules using optimized DataFrame operations.

### Business Value
- Ensures 100% compliance with IRS contribution limits avoiding penalties
- Accurately projects employer costs for budgeting ($10-50M annually)
- Prevents excess contributions that require costly corrections

### Success Criteria
- ✅ Calculates contributions with 100% accuracy using vectorized operations
- ✅ Enforces all IRS limits (402(g), 415(c), highly compensated) with batch processing
- ✅ Handles complex timing scenarios (bonuses, raises, terminations) efficiently
- ✅ Processes 100K employees in <30 seconds per pay period using DataFrame operations
- ✅ Maintains real-time YTD tracking with sub-second query performance
- ✅ Supports concurrent scenario processing with isolated limit tracking

---

## User Stories

### Story 1: Vectorized Contribution Calculations (12 points)
**As a** payroll administrator
**I want** accurate contribution calculations each pay period
**So that** the correct amounts are deducted and matched

**Acceptance Criteria:**
- Vectorized calculation of employee deferrals for entire payroll population
- Handles both percentage and dollar amount elections using conditional DataFrame operations
- Supports bi-weekly, semi-monthly, monthly pay frequencies with optimized pay calendar logic
- Creates batch CONTRIBUTION events with UUID correlation and performance tracking
- Handles mid-year rate changes with historical effective dating
- Real-time validation of calculation accuracy with automated variance detection
- Support for complex compensation scenarios including bonuses and irregular pay

### Story 2: Vectorized IRS Limit Enforcement (18 points)
**As a** compliance officer
**I want** automatic enforcement of all IRS limits
**So that** we avoid excess contributions and penalties

**Acceptance Criteria:**
- Vectorized 402(g) elective deferral limit enforcement ($23,000 for 2025) using DataFrame masking
- Vectorized 415(c) annual additions limit ($70,000 for 2025) with hierarchical limit application
- Age 50+ catch-up contributions ($7,500 for 2025) using efficient age-based filtering
- Highly compensated employee limits with dynamic threshold calculations
- Real-time limit status tracking with automatic contribution suspension
- Vectorized year-end true-up calculations with batch correction processing
- Multi-year limit tracking for rollover scenarios and plan changes
- Compliance reporting with automated exception detection and resolution recommendations

### Story 3: Dynamic Compensation Definitions (10 points)
**As a** plan administrator
**I want** flexible compensation definitions
**So that** different pay types are handled correctly

**Acceptance Criteria:**
- Configurable W-2 compensation baseline with multiple definition support
- Dynamic include/exclude rules for bonuses, commissions, overtime using boolean logic
- Pre/post severance compensation rules with timing-sensitive calculations
- Multiple safe harbor compensation definitions with automatic selection
- Vectorized handling of compensation over IRS limit ($360,000 for 2025)
- Support for multiple compensation streams with complex aggregation rules
- Integration with payroll systems for real-time compensation updates
- Historical compensation tracking for plan year changes and corrections

### Story 4: Enhanced Roth Contribution Support (8 points)
**As an** employee
**I want** to split contributions between traditional and Roth
**So that** I can optimize my tax strategy

**Acceptance Criteria:**
- Vectorized separate tracking of traditional vs Roth with optimized data structures
- Flexible split percentage configuration with dynamic allocation logic
- Combined limit enforcement using unified constraint solving
- Roth in-plan conversions with automated eligibility checking and tax implications
- Separate employer match treatment with configurable allocation rules
- Support for Roth catch-up contributions with age-based automation
- After-tax contribution support with mega backdoor Roth capabilities
- Tax optimization recommendations based on contribution patterns

### Story 5: Advanced Timing & Proration Logic (12 points)
**As a** finance manager
**I want** accurate handling of partial periods
**So that** contributions are correct for new hires and terminations

**Acceptance Criteria:**
- Vectorized pro-ration for partial pay periods using calendar-aware calculations
- Complex hire date timing scenarios with eligibility integration
- Sophisticated termination date contribution rules with final pay handling
- Leave of absence suspension and resumption with accurate service credit tracking
- Rehire contribution resumption with historical contribution election restoration
- Mid-year plan changes with seamless contribution transitions
- Acquisition and merger scenarios with plan consolidation support
- Payroll calendar integration with holiday and business day adjustments

---

## Technical Specifications

### Contribution Configuration
```yaml
contribution_rules:
  compensation_definition:
    base_type: "w2_wages"
    inclusions:
      - regular_pay
      - overtime
      - commissions
      - bonuses
    exclusions:
      - severance
      - fringe_benefits
      - expense_reimbursements

  pay_frequencies:
    - code: "BW"
      periods_per_year: 26
    - code: "SM"
      periods_per_year: 24
    - code: "MO"
      periods_per_year: 12

  irs_limits_2024:
    elective_deferral: 23000
    catch_up: 7500
    annual_additions: 69000
    compensation: 345000

  timing_rules:
    contributions_through_termination: true
    bonus_deferral_allowed: true
    true_up_frequency: "annual"
```

### Vectorized Contribution Calculation Engine
```python
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, date
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class ContributionLimits:
    elective_deferral_2025: int = 23500
    catch_up_2025: int = 7500
    annual_additions_2025: int = 70000
    compensation_2025: int = 360000

@dataclass
class ContributionResult:
    employee_id: str
    pay_period_end: date
    gross_compensation: Decimal
    eligible_compensation: Decimal
    employee_pre_tax_deferral: Decimal
    employee_roth_deferral: Decimal
    employer_match: Decimal
    employer_nonelective: Decimal
    total_contributions: Decimal
    limits_applied: List[str]
    ytd_deferrals: Decimal
    ytd_additions: Decimal

class VectorizedContributionCalculator:
    def __init__(self, plan_config: PlanConfig, limits: ContributionLimits):
        self.plan_config = plan_config
        self.limits = limits
        self.ytd_cache = {}  # Cache for YTD calculations

    def calculate_contributions_batch(self,
                                    payroll_df: pd.DataFrame,
                                    pay_period_end: date) -> pd.DataFrame:
        """Calculate contributions for entire payroll population efficiently"""

        # Initialize result columns
        payroll_df = self._initialize_contribution_columns(payroll_df)

        # Step 1: Calculate eligible compensation (vectorized)
        payroll_df = self._calculate_eligible_compensation_vectorized(payroll_df)

        # Step 2: Apply IRS compensation limits
        payroll_df = self._apply_compensation_limits_vectorized(payroll_df)

        # Step 3: Calculate employee deferrals
        payroll_df = self._calculate_employee_deferrals_vectorized(payroll_df)

        # Step 4: Apply 402(g) limits
        payroll_df = self._apply_402g_limits_vectorized(payroll_df)

        # Step 5: Calculate employer contributions
        payroll_df = self._calculate_employer_contributions_vectorized(payroll_df)

        # Step 6: Apply 415(c) limits
        payroll_df = self._apply_415c_limits_vectorized(payroll_df)

        # Step 7: Update YTD tracking
        self._update_ytd_tracking_batch(payroll_df, pay_period_end)

        return payroll_df

    def _initialize_contribution_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Initialize all contribution calculation columns"""

        df['gross_compensation'] = 0.0
        df['eligible_compensation'] = 0.0
        df['employee_pre_tax_deferral'] = 0.0
        df['employee_roth_deferral'] = 0.0
        df['employer_match'] = 0.0
        df['employer_nonelective'] = 0.0
        df['total_contributions'] = 0.0
        df['limits_applied'] = [[] for _ in range(len(df))]
        df['ytd_deferrals'] = 0.0
        df['ytd_additions'] = 0.0

        return df

    def _calculate_eligible_compensation_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate eligible compensation using vectorized operations"""

        # Base compensation calculation
        df['gross_compensation'] = df['regular_pay'] + df['overtime_pay']

        # Apply inclusion/exclusion rules
        comp_def = self.plan_config.compensation_definition

        # Include bonuses if specified
        if 'bonuses' in comp_def.inclusions:
            df['gross_compensation'] += df['bonus_pay'].fillna(0)

        # Include commissions if specified
        if 'commissions' in comp_def.inclusions:
            df['gross_compensation'] += df['commission_pay'].fillna(0)

        # Exclude severance if specified
        if 'severance' in comp_def.exclusions:
            df['gross_compensation'] -= df['severance_pay'].fillna(0)

        # Set eligible compensation (can be modified later by limits)
        df['eligible_compensation'] = df['gross_compensation']

        return df

    def _apply_compensation_limits_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply IRS compensation limits using vectorized operations"""

        # Load YTD compensation efficiently
        ytd_comp = self._get_ytd_compensation_batch(df['employee_id'].tolist())
        df['ytd_compensation'] = df['employee_id'].map(ytd_comp)

        # Calculate remaining compensation room
        remaining_comp_room = self.limits.compensation_2025 - df['ytd_compensation']

        # Apply limit where needed
        comp_limit_mask = df['eligible_compensation'] > remaining_comp_room
        df.loc[comp_limit_mask, 'eligible_compensation'] = remaining_comp_room

        # Track limit applications
        df.loc[comp_limit_mask, 'limits_applied'] = df.loc[comp_limit_mask, 'limits_applied'].apply(
            lambda x: x + ['compensation_limit']
        )

        return df

    def _calculate_employee_deferrals_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate employee deferrals using vectorized operations"""

        # Handle percentage-based deferrals
        percentage_mask = df['deferral_type'] == 'percentage'
        df.loc[percentage_mask, 'total_deferral_requested'] = (
            df.loc[percentage_mask, 'eligible_compensation'] *
            df.loc[percentage_mask, 'deferral_rate']
        )

        # Handle dollar-based deferrals
        dollar_mask = df['deferral_type'] == 'dollar'
        df.loc[dollar_mask, 'total_deferral_requested'] = np.minimum(
            df.loc[dollar_mask, 'deferral_amount'],
            df.loc[dollar_mask, 'eligible_compensation']
        )

        # Split between traditional and Roth based on election
        df['employee_pre_tax_deferral'] = (
            df['total_deferral_requested'] *
            df['traditional_percentage'].fillna(1.0)
        )

        df['employee_roth_deferral'] = (
            df['total_deferral_requested'] *
            df['roth_percentage'].fillna(0.0)
        )

        return df

    def _apply_402g_limits_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply 402(g) elective deferral limits using vectorized operations"""

        # Load YTD deferrals efficiently
        ytd_deferrals = self._get_ytd_deferrals_batch(df['employee_id'].tolist())
        df['ytd_deferrals'] = df['employee_id'].map(ytd_deferrals)

        # Calculate applicable limits (with catch-up for 50+)
        df['applicable_402g_limit'] = self.limits.elective_deferral_2025
        catch_up_mask = df['age'] >= 50
        df.loc[catch_up_mask, 'applicable_402g_limit'] += self.limits.catch_up_2025

        # Calculate remaining deferral room
        df['remaining_deferral_room'] = df['applicable_402g_limit'] - df['ytd_deferrals']

        # Apply limit to total requested deferral
        total_requested = df['employee_pre_tax_deferral'] + df['employee_roth_deferral']
        limited_total = np.minimum(total_requested, df['remaining_deferral_room'])

        # Proportionally reduce pre-tax and Roth if limit applied
        limit_applied_mask = limited_total < total_requested

        if limit_applied_mask.any():
            # Calculate reduction factor
            reduction_factor = limited_total / total_requested
            reduction_factor = reduction_factor.fillna(0)  # Handle division by zero

            # Apply reduction proportionally
            df.loc[limit_applied_mask, 'employee_pre_tax_deferral'] *= reduction_factor
            df.loc[limit_applied_mask, 'employee_roth_deferral'] *= reduction_factor

            # Track limit applications
            df.loc[limit_applied_mask, 'limits_applied'] = df.loc[limit_applied_mask, 'limits_applied'].apply(
                lambda x: x + ['402g_limit']
            )

        return df

    def _calculate_employer_contributions_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate employer contributions using vectorized operations"""

        # Calculate total employee deferral for match calculation
        df['total_employee_deferral'] = (
            df['employee_pre_tax_deferral'] + df['employee_roth_deferral']
        )

        # Calculate deferral rate for match formula
        df['effective_deferral_rate'] = (
            df['total_employee_deferral'] / df['eligible_compensation']
        ).fillna(0)

        # Apply tiered match formula using vectorized operations
        match_formula = self.plan_config.match_formula
        df['employer_match'] = 0.0

        for tier in match_formula.tiers:
            # Determine the portion of deferral rate that applies to this tier
            tier_rate = np.maximum(0,
                np.minimum(tier.employee_max, df['effective_deferral_rate']) -
                sum(t.employee_max for t in match_formula.tiers if t.employee_max < tier.employee_max)
            )

            # Calculate match for this tier
            tier_match = tier_rate * tier.match_rate * df['eligible_compensation']
            df['employer_match'] += tier_match

        # Add any employer non-elective contributions
        if hasattr(self.plan_config, 'nonelective_contribution_rate'):
            df['employer_nonelective'] = (
                df['eligible_compensation'] *
                self.plan_config.nonelective_contribution_rate
            )

        return df

    def _apply_415c_limits_vectorized(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply 415(c) annual additions limits using vectorized operations"""

        # Load YTD annual additions
        ytd_additions = self._get_ytd_annual_additions_batch(df['employee_id'].tolist())
        df['ytd_additions'] = df['employee_id'].map(ytd_additions)

        # Calculate total proposed additions for this period
        df['proposed_additions'] = (
            df['employee_pre_tax_deferral'] +
            df['employee_roth_deferral'] +
            df['employer_match'] +
            df['employer_nonelective']
        )

        # Calculate remaining 415(c) room
        df['remaining_415c_room'] = self.limits.annual_additions_2025 - df['ytd_additions']

        # Apply limit where needed
        limit_needed_mask = df['proposed_additions'] > df['remaining_415c_room']

        if limit_needed_mask.any():
            # Calculate excess amount
            excess_amount = df['proposed_additions'] - df['remaining_415c_room']

            # Apply reduction hierarchy: non-elective, then match, then deferrals
            # Reduce non-elective first
            nonelective_reduction = np.minimum(excess_amount, df['employer_nonelective'])
            df.loc[limit_needed_mask, 'employer_nonelective'] -= nonelective_reduction
            excess_amount -= nonelective_reduction

            # Reduce match second
            match_reduction = np.minimum(excess_amount, df['employer_match'])
            df.loc[limit_needed_mask, 'employer_match'] -= match_reduction
            excess_amount -= match_reduction

            # Reduce deferrals last (proportionally between pre-tax and Roth)
            total_deferrals = df['employee_pre_tax_deferral'] + df['employee_roth_deferral']
            deferral_reduction = np.minimum(excess_amount, total_deferrals)

            # Apply proportional reduction to deferrals
            deferral_reduction_factor = 1 - (deferral_reduction / total_deferrals).fillna(0)
            df.loc[limit_needed_mask, 'employee_pre_tax_deferral'] *= deferral_reduction_factor
            df.loc[limit_needed_mask, 'employee_roth_deferral'] *= deferral_reduction_factor

            # Track limit applications
            df.loc[limit_needed_mask, 'limits_applied'] = df.loc[limit_needed_mask, 'limits_applied'].apply(
                lambda x: x + ['415c_limit']
            )

        # Calculate final total contributions
        df['total_contributions'] = (
            df['employee_pre_tax_deferral'] +
            df['employee_roth_deferral'] +
            df['employer_match'] +
            df['employer_nonelective']
        )

        return df

    def _get_ytd_deferrals_batch(self, employee_ids: List[str]) -> Dict[str, float]:
        """Efficiently retrieve YTD deferrals for multiple employees"""
        # Implementation would query the YTD tracking table efficiently
        # This is a placeholder for the actual database query
        return {emp_id: 0.0 for emp_id in employee_ids}  # Placeholder

    def _get_ytd_compensation_batch(self, employee_ids: List[str]) -> Dict[str, float]:
        """Efficiently retrieve YTD compensation for multiple employees"""
        # Implementation would query the YTD tracking efficiently
        return {emp_id: 0.0 for emp_id in employee_ids}  # Placeholder

    def _get_ytd_annual_additions_batch(self, employee_ids: List[str]) -> Dict[str, float]:
        """Efficiently retrieve YTD annual additions for multiple employees"""
        # Implementation would query the YTD tracking efficiently
        return {emp_id: 0.0 for emp_id in employee_ids}  # Placeholder

    def _update_ytd_tracking_batch(self, df: pd.DataFrame, pay_period_end: date):
        """Update YTD tracking for all employees in batch"""
        # Implementation would efficiently update the YTD tracking table
        pass  # Placeholder

# Usage example
def process_payroll_contributions(payroll_df: pd.DataFrame,
                                 plan_config: PlanConfig,
                                 pay_period_end: date) -> pd.DataFrame:
    """Process contributions for entire payroll"""

    calculator = VectorizedContributionCalculator(plan_config, ContributionLimits())
    result_df = calculator.calculate_contributions_batch(payroll_df, pay_period_end)

    # Generate contribution events for successful calculations
    contribution_events = create_contribution_events_batch(result_df, pay_period_end)

    # Insert events and update YTD tracking
    insert_contribution_events_batch(contribution_events)

    return result_df
```

### Limit Tracking Schema
```sql
CREATE TABLE contribution_limit_tracking (
    employee_id VARCHAR,
    plan_year INTEGER,
    contribution_type VARCHAR,
    ytd_amount DECIMAL(10,2),
    limit_amount DECIMAL(10,2),
    last_updated TIMESTAMP,
    PRIMARY KEY (employee_id, plan_year, contribution_type)
);
```

---

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Payroll Processing | <30 seconds for 100K employees per pay period | Vectorized DataFrame operations with efficient YTD lookups |
| YTD Limit Queries | <100ms for real-time limit checking | Optimized database indexes with materialized YTD views |
| Contribution Validation | <50ms for single employee validation | In-memory YTD caching with event-driven updates |
| Memory Usage | <8GB for 100K employee payroll processing | Efficient data types and streaming operations |
| Limit Accuracy | 100% accuracy with IRS compliance | Comprehensive test suite with regulatory validation |

## Dependencies
- E021: DC Plan Data Model (event schema)
- E023: Enrollment Engine (deferral elections)
- Payroll integration for compensation data
- Annual IRS limit updates (automated where possible)
- Pandas/Polars for vectorized DataFrame operations
- NumPy for efficient numerical computations
- Database optimization for YTD tracking queries
- Real-time data validation frameworks

## Risks
- **Risk**: Complex limit interaction scenarios
- **Mitigation**: Comprehensive test scenarios from actual cases
- **Risk**: Performance with real-time calculations
- **Mitigation**: Implement caching for YTD values

## Estimated Effort
**Total Story Points**: 60 points
**Estimated Duration**: 4 sprints

---

## Definition of Done
- [ ] All contribution types calculated correctly
- [ ] IRS limits enforced with proper ordering
- [ ] Compensation definitions flexible and accurate
- [ ] Roth/traditional split working
- [ ] Timing scenarios handled properly
- [ ] Performance benchmarks met
- [ ] Compliance testing complete
- [ ] Documentation includes calculation examples
