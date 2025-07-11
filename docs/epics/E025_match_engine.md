# Epic E025: Match Engine with Formula Support

## Epic Overview

### Summary
Create a high-performance vectorized employer match calculation engine supporting complex multi-tier formulas, true-up calculations, and various match types using efficient DataFrame operations for 100K+ employee populations.

### Business Value
- Enables accurate modeling of employer match costs ($5-50M annually)
- Supports optimization of match formulas to maximize participation
- Reduces manual calculations and errors in match processing

### Success Criteria
- ✅ Supports all common match formula types with vectorized processing
- ✅ Calculates matches with 100% accuracy using optimized algorithms
- ✅ Handles true-up and stretch match scenarios with batch processing
- ✅ Processes complex formulas for 100K employees in <30 seconds
- ✅ Provides real-time formula optimization recommendations
- ✅ Supports dynamic formula changes with seamless transitions

---

## User Stories

### Story 1: Vectorized Match Formulas (12 points)
**As a** plan sponsor
**I want** to configure standard match formulas
**So that** I can model different match strategies

**Acceptance Criteria:**
- Vectorized simple percentage match (50% of deferrals) using NumPy operations
- Efficient tiered match (100% on first 3%, 50% on next 2%) with optimized tier processing
- Dollar-for-dollar match up to percentage with dynamic cap calculations
- Discretionary match capability with configurable timing and approval workflows
- Safe harbor match formulas with automatic compliance validation
- Formula versioning and effective dating for mid-year changes
- Performance benchmarking against 100K employee populations

### Story 2: Advanced Stretch Match Implementation (12 points)
**As a** benefits designer
**I want** stretch match formulas
**So that** I can incentivize higher savings rates

**Acceptance Criteria:**
- Vectorized stretch match calculations (25% on first 12%) with performance optimization
- Flexible graduated tier formulas with unlimited tier support
- Dynamic maximum match caps (% of compensation) with real-time limit enforcement
- Seamless vesting schedule integration with automated forfeiture calculations
- Interactive comparison tools for formula impact with side-by-side analytics
- Machine learning recommendations for optimal stretch match parameters
- A/B testing framework for formula effectiveness measurement

### Story 3: Automated True-Up Calculations (18 points)
**As a** payroll manager
**I want** automatic true-up calculations
**So that** employees receive their full match regardless of timing

**Acceptance Criteria:**
- Vectorized annual true-up for employees who max early using batch processing
- Complex variable compensation timing scenarios with payroll calendar integration
- Sophisticated unpaid leave handling with service credit calculations
- Comprehensive termination true-up rules with final pay integration
- Automated true-up payment events with detailed audit trails
- Real-time true-up projections during the plan year
- Integration with payroll systems for seamless payment processing
- Compliance reporting for true-up calculations and payments

### Story 4: Dynamic Vesting Integration (8 points)
**As a** plan administrator
**I want** vesting schedules applied to matches
**So that** we retain employees and reduce costs

**Acceptance Criteria:**
- Vectorized cliff vesting (3-year) with automated milestone tracking
- Flexible graded vesting (2-6 year) with configurable schedules
- Advanced service computation for vesting with break-in-service rules
- Automatic immediate vesting for safe harbor with compliance monitoring
- Real-time forfeiture calculations with redistribution logic
- Vesting schedule changes with grandfathering provisions
- Integration with termination events for accurate forfeiture processing
- Rehire vesting restoration with historical service credit

### Story 5: AI-Powered Match Optimization Analytics (12 points)
**As a** CFO
**I want** to compare different match formulas
**So that** I can optimize cost vs participation

**Acceptance Criteria:**
- Interactive side-by-side formula comparison with real-time updates
- Multi-year cost projections by formula with scenario sensitivity analysis
- Behavioral participation impact modeling using machine learning
- Comprehensive employee outcome analysis with retirement readiness scoring
- Detailed ROI calculations for match spend with optimization recommendations
- Predictive analytics for formula effectiveness over time
- Executive dashboard with key match metrics and trends
- Integration with compensation planning for total rewards optimization

---

## Technical Specifications

### Match Formula Configuration
```yaml
match_formulas:
  standard_match:
    name: "Standard Tiered Match"
    tiers:
      - employee_min: 0.00
        employee_max: 0.03
        match_rate: 1.00  # 100% match
      - employee_min: 0.03
        employee_max: 0.05
        match_rate: 0.50  # 50% match
    max_match_percentage: 0.04  # 4% max match

  stretch_match:
    name: "Stretch Match"
    tiers:
      - employee_min: 0.00
        employee_max: 0.12
        match_rate: 0.25  # 25% match
    max_match_percentage: 0.03  # 3% max match

  safe_harbor_basic:
    name: "Safe Harbor Basic Match"
    tiers:
      - employee_min: 0.00
        employee_max: 0.03
        match_rate: 1.00
      - employee_min: 0.03
        employee_max: 0.05
        match_rate: 0.50
    immediate_vesting: true

  vesting_schedules:
    cliff_3_year:
      type: "cliff"
      years_to_vest: 3

    graded_2_to_6:
      type: "graded"
      schedule:
        - years: 2
          vested_percentage: 0.20
        - years: 3
          vested_percentage: 0.40
        - years: 4
          vested_percentage: 0.60
        - years: 5
          vested_percentage: 0.80
        - years: 6
          vested_percentage: 1.00
```

### Vectorized Match Calculation Engine
```python
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal

@dataclass
class MatchTier:
    employee_min: float
    employee_max: float
    match_rate: float
    tier_order: int

@dataclass
class MatchFormula:
    formula_id: str
    name: str
    tiers: List[MatchTier]
    max_match_percentage: Optional[float] = None
    effective_date: Optional[date] = None
    end_date: Optional[date] = None

class VectorizedMatchEngine:
    def __init__(self, match_formulas: Dict[str, MatchFormula]):
        self.match_formulas = match_formulas
        self.vesting_cache = {}  # Cache for vesting calculations

    def calculate_match_batch(self, employees_df: pd.DataFrame,
                             formula_id: str,
                             as_of_date: date = None) -> pd.DataFrame:
        """Calculate employer match for entire employee population efficiently"""

        formula = self.match_formulas[formula_id]

        # Initialize match calculation columns
        employees_df['employer_match'] = 0.0
        employees_df['match_calculation_details'] = [[] for _ in range(len(employees_df))]

        # Apply tiered match formula using vectorized operations
        employees_df = self._apply_tiered_formula_vectorized(employees_df, formula)

        # Apply maximum match caps
        if formula.max_match_percentage:
            employees_df = self._apply_match_caps_vectorized(employees_df, formula)

        # Apply vesting calculations
        employees_df = self._apply_vesting_vectorized(employees_df, as_of_date)

        return employees_df

    def _apply_tiered_formula_vectorized(self, df: pd.DataFrame,
                                       formula: MatchFormula) -> pd.DataFrame:
        """Apply tiered match formula using efficient vectorized operations"""

        # Sort tiers by order to ensure correct application
        sorted_tiers = sorted(formula.tiers, key=lambda t: t.tier_order)

        for tier in sorted_tiers:
            # Calculate the portion of deferral rate that applies to this tier
            # Use np.clip to efficiently handle tier boundaries
            applicable_rate = np.clip(
                df['deferral_rate'] - tier.employee_min,
                0,
                tier.employee_max - tier.employee_min
            )

            # Calculate match for this tier
            tier_match = applicable_rate * tier.match_rate * df['eligible_compensation']

            # Add to total match
            df['employer_match'] += tier_match

            # Track calculation details for audit trail
            tier_details = {
                'tier': tier.tier_order,
                'employee_rate_range': f"{tier.employee_min:.1%}-{tier.employee_max:.1%}",
                'match_rate': f"{tier.match_rate:.1%}",
                'applicable_employee_rate': applicable_rate,
                'tier_match_amount': tier_match
            }

            # Add details for employees with non-zero tier match
            non_zero_mask = tier_match > 0
            for idx in df[non_zero_mask].index:
                df.at[idx, 'match_calculation_details'].append(tier_details)

        return df

    def _apply_match_caps_vectorized(self, df: pd.DataFrame,
                                   formula: MatchFormula) -> pd.DataFrame:
        """Apply maximum match caps using vectorized operations"""

        # Calculate maximum match amount
        max_match_dollars = df['eligible_compensation'] * formula.max_match_percentage

        # Apply cap where needed
        cap_applied_mask = df['employer_match'] > max_match_dollars
        df.loc[cap_applied_mask, 'employer_match'] = max_match_dollars

        # Track cap applications
        for idx in df[cap_applied_mask].index:
            df.at[idx, 'match_calculation_details'].append({
                'cap_applied': True,
                'cap_percentage': f"{formula.max_match_percentage:.1%}",
                'cap_amount': max_match_dollars[idx]
            })

        return df

    def _apply_vesting_vectorized(self, df: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
        """Apply vesting calculations using cached service computations"""

        # Calculate vesting percentages efficiently
        df['vesting_percentage'] = df.apply(
            lambda row: self._calculate_vesting_percentage(
                row['employee_id'],
                row['service_years'],
                row['vesting_schedule_id'],
                as_of_date
            ), axis=1
        )

        # Apply vesting to match amounts
        df['vested_match'] = df['employer_match'] * df['vesting_percentage']
        df['nonvested_match'] = df['employer_match'] - df['vested_match']

        return df

    def calculate_true_up_batch(self, employees_df: pd.DataFrame,
                               plan_year: int,
                               formula_id: str) -> pd.DataFrame:
        """Calculate year-end true-up amounts for entire population"""

        formula = self.match_formulas[formula_id]

        # Get YTD data efficiently for all employees
        ytd_data = self._get_ytd_data_batch(employees_df['employee_id'].tolist(), plan_year)

        # Merge YTD data with employee data
        employees_df = employees_df.merge(ytd_data, on='employee_id', how='left')

        # Calculate annual deferral rates
        employees_df['annual_deferral_rate'] = (
            employees_df['ytd_deferrals'] / employees_df['ytd_compensation']
        ).fillna(0)

        # Calculate what match should have been based on annual amounts
        temp_df = employees_df.copy()
        temp_df['deferral_rate'] = temp_df['annual_deferral_rate']
        temp_df['eligible_compensation'] = temp_df['ytd_compensation']

        # Calculate correct annual match
        temp_df = self._apply_tiered_formula_vectorized(temp_df, formula)

        # True-up is the difference (positive only)
        employees_df['true_up_amount'] = np.maximum(
            0,
            temp_df['employer_match'] - employees_df['ytd_match_paid']
        )

        return employees_df[employees_df['true_up_amount'] > 0]

    def _get_ytd_data_batch(self, employee_ids: List[str],
                           plan_year: int) -> pd.DataFrame:
        """Efficiently retrieve YTD data for multiple employees"""
        # This would be implemented with optimized database queries
        # Placeholder implementation
        return pd.DataFrame({
            'employee_id': employee_ids,
            'ytd_deferrals': [0.0] * len(employee_ids),
            'ytd_compensation': [50000.0] * len(employee_ids),
            'ytd_match_paid': [0.0] * len(employee_ids)
        })

    def _calculate_vesting_percentage(self, employee_id: str,
                                    service_years: float,
                                    vesting_schedule_id: str,
                                    as_of_date: date) -> float:
        """Calculate vesting percentage with caching for performance"""

        cache_key = f"{employee_id}_{vesting_schedule_id}_{as_of_date}"

        if cache_key in self.vesting_cache:
            return self.vesting_cache[cache_key]

        # Implement vesting schedule logic
        if vesting_schedule_id == 'immediate':
            vesting_pct = 1.0
        elif vesting_schedule_id == 'cliff_3_year':
            vesting_pct = 1.0 if service_years >= 3 else 0.0
        elif vesting_schedule_id == 'graded_2_to_6':
            if service_years < 2:
                vesting_pct = 0.0
            elif service_years < 3:
                vesting_pct = 0.2
            elif service_years < 4:
                vesting_pct = 0.4
            elif service_years < 5:
                vesting_pct = 0.6
            elif service_years < 6:
                vesting_pct = 0.8
            else:
                vesting_pct = 1.0
        else:
            vesting_pct = 0.0  # Default to not vested

        # Cache the result
        self.vesting_cache[cache_key] = vesting_pct

        return vesting_pct

    def compare_match_formulas_vectorized(self, employee_population_df: pd.DataFrame,
                                        formula_ids: List[str],
                                        projection_years: int = 5) -> Dict[str, Dict]:
        """Compare multiple match formulas using vectorized operations"""

        results = {}

        for formula_id in formula_ids:
            formula = self.match_formulas[formula_id]

            # Calculate match for this formula
            temp_df = employee_population_df.copy()
            temp_df = self.calculate_match_batch(temp_df, formula_id)

            # Calculate key metrics
            total_employees = len(temp_df)
            participating_employees = len(temp_df[temp_df['deferral_rate'] > 0])

            results[formula_id] = {
                'formula_name': formula.name,
                'total_annual_cost': temp_df['employer_match'].sum(),
                'projected_5_year_cost': temp_df['employer_match'].sum() * projection_years,
                'participation_rate': participating_employees / total_employees,
                'average_match_rate': (temp_df['employer_match'] / temp_df['eligible_compensation']).mean(),
                'average_deferral_rate': temp_df[temp_df['deferral_rate'] > 0]['deferral_rate'].mean(),
                'cost_per_participant': temp_df['employer_match'].sum() / participating_employees if participating_employees > 0 else 0,
                'employees_at_max_match': len(temp_df[temp_df['employer_match'] >= temp_df['eligible_compensation'] * (formula.max_match_percentage or 1.0)]),
                'total_compensation_base': temp_df['eligible_compensation'].sum()
            }

        return results

# Usage example
def process_employer_match_batch(employees_df: pd.DataFrame,
                                formula_id: str,
                                match_engine: VectorizedMatchEngine,
                                pay_period_end: date) -> pd.DataFrame:
    """Process employer match calculations for payroll"""

    # Calculate matches
    result_df = match_engine.calculate_match_batch(
        employees_df,
        formula_id,
        as_of_date=pay_period_end
    )

    # Generate match events for employees with matches
    employees_with_match = result_df[result_df['employer_match'] > 0]

    if len(employees_with_match) > 0:
        match_events = create_match_events_batch(
            employees_with_match,
            pay_period_end
        )

        # Insert events
        insert_match_events_batch(match_events)

    return result_df
```

### Match Optimization Comparison
```python
def compare_match_formulas(employee_population, formula_list, years=5):
    """Compare impact of different match formulas"""
    results = {}

    for formula in formula_list:
        projection = {
            'total_cost': 0,
            'avg_match_rate': 0,
            'participation_rate': 0,
            'avg_deferral_rate': 0
        }

        for employee in employee_population:
            # Model enrollment probability with this formula
            enrollment_prob = model_enrollment_impact(employee, formula)

            if random.random() < enrollment_prob:
                # Model deferral rate selection
                deferral_rate = model_deferral_selection(employee, formula)

                # Calculate match cost
                match_cost = calculate_match(
                    deferral_rate,
                    employee.projected_compensation,
                    formula
                )

                projection['total_cost'] += match_cost * years
                projection['participation_rate'] += 1
                projection['avg_deferral_rate'] += deferral_rate

        # Calculate averages
        participants = projection['participation_rate']
        projection['participation_rate'] /= len(employee_population)
        projection['avg_deferral_rate'] /= participants if participants > 0 else 1
        projection['avg_match_rate'] = projection['total_cost'] / (
            sum(e.projected_compensation for e in employee_population) * years
        )

        results[formula.name] = projection

    return results
```

---

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Match Calculation | <30 seconds for 100K employees | Vectorized DataFrame operations with NumPy optimization |
| True-Up Processing | <2 minutes for annual true-up batch | Efficient YTD data retrieval with batch processing |
| Formula Comparison | <1 minute for 10 formula scenarios | Parallel processing with cached calculations |
| Vesting Calculations | <10 seconds with service caching | Pre-computed vesting schedules with lookup optimization |
| Memory Usage | <6GB for 100K employee match processing | Efficient data types and streaming operations |

## Dependencies
- E021: DC Plan Data Model (event schema)
- E024: Contribution Calculator (compensation amounts)
- Employee demographic data for modeling
- Pandas/NumPy for vectorized DataFrame operations
- Machine learning libraries for optimization analytics
- Real-time database connectivity for YTD tracking
- Payroll system integration for true-up processing

## Risks
- **Risk**: Complex true-up edge cases
- **Mitigation**: Test with real payroll scenarios
- **Risk**: Formula change mid-year handling
- **Mitigation**: Effective date tracking on all formulas

## Estimated Effort
**Total Story Points**: 62 points
**Estimated Duration**: 4 sprints

---

## Definition of Done
- [ ] All match formula types implemented
- [ ] True-up calculations accurate
- [ ] Vesting schedules integrated
- [ ] Formula comparison tools complete
- [ ] Performance benchmarks met
- [ ] Edge cases documented and tested
- [ ] User documentation with examples
