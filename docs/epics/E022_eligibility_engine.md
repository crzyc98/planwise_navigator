# Epic E022: Eligibility Engine

## Epic Overview

### Summary
Build a sophisticated eligibility determination engine that evaluates employee eligibility for DC plan participation based on configurable rules including age, service, hours worked, and employee classification.

### Business Value
- Automates complex eligibility calculations reducing manual HR work by 80%
- Ensures 100% compliance with plan document requirements
- Enables modeling of eligibility rule changes to assess participation impact

### Success Criteria
- ✅ Accurately determines eligibility for 100% of employees
- ✅ Supports all common eligibility rule patterns
- ✅ Processes daily eligibility updates for 100K employees in <30 seconds
- ✅ Generates clear audit trail for eligibility determinations
- ✅ Achieves <100ms response time for point-in-time eligibility queries
- ✅ Supports incremental processing with 95% cache hit rate for unchanged employees

---

## User Stories

### Story 1: Vectorized Eligibility Calculator (18 points)
**As a** benefits administrator
**I want** automated eligibility determination based on plan rules
**So that** employees are enrolled at the right time without manual tracking

**Acceptance Criteria:**
- Vectorized eligibility evaluation for 100K+ employees in <30 seconds
- Evaluates age (18, 21, or no minimum) using DataFrame operations
- Evaluates service (immediate, 6 months, 12 months) with efficient date arithmetic
- Evaluates hours worked (500, 1000, or no minimum) with aggregation caching
- Handles entry dates (immediate, monthly, quarterly, semi-annual) using vectorized logic
- Creates batch ELIGIBILITY_START events with UUID correlation
- Supports incremental processing for changed employees only

### Story 2: Employee Classification Rules (10 points)
**As a** plan sponsor
**I want** different eligibility rules by employee class
**So that** I can exclude certain groups (e.g., interns, contractors)

**Acceptance Criteria:**
- Supports inclusion/exclusion by job level, location, division using boolean masking
- Handles union vs non-union employees with optimized lookups
- Applies statutory exclusions (non-resident aliens) via configuration
- Configurable via Pydantic-validated YAML without code changes
- Pre-computed classification segments for performance optimization
- Dynamic rule application with effective dating support

### Story 3: Service Computation Methods (12 points)
**As a** compliance officer
**I want** accurate service calculations under multiple methods
**So that** we meet ERISA requirements for different plan types

**Acceptance Criteria:**
- Elapsed time method for service calculation using vectorized date arithmetic
- Hours counting method with 1000-hour threshold and YTD tracking
- Handles breaks in service and rehires with complex rehire credit logic
- Supports "Rule of Parity" for vesting with automated break period calculations
- Caching of service computations for employees with unchanged employment history
- Support for multiple concurrent service calculations (eligibility vs vesting)
- Integration with workforce simulation termination and rehire events

### Story 4: Entry Date Processing (8 points)
**As a** payroll administrator
**I want** automatic entry date calculations
**So that** eligible employees start on the correct date

**Acceptance Criteria:**
- Calculates next entry date based on plan rules using efficient date logic
- Handles immediate, monthly, quarterly, semi-annual entry with vectorized operations
- Creates advance notifications (30/60/90 days) with batch processing
- Supports dual entry dates for 401(k) vs match with separate eligibility tracks
- Calendar-aware entry date calculation (business day adjustments)
- Integration with payroll calendar for realistic entry timing
- Bulk entry date processing for mass eligibility changes

### Story 5: Eligibility Change Events (8 points)
**As an** audit manager
**I want** complete tracking of eligibility changes
**So that** I can explain why someone became eligible or lost eligibility

**Acceptance Criteria:**
- Tracks all eligibility status changes with complete audit trail
- Records reason for change (age, service, hours, class) with structured metadata
- Supports eligibility loss scenarios (termination, reclassification, plan changes)
- Provides sub-second point-in-time eligibility queries using optimized snapshots
- Event correlation with workforce simulation changes
- Automated compliance reporting for eligibility patterns
- Performance monitoring for eligibility processing SLAs

---

## Technical Specifications

### Eligibility Configuration
```yaml
eligibility_rules:
  standard:
    minimum_age: 21
    minimum_service_months: 12
    service_computation: elapsed_time
    minimum_hours: 1000
    entry_dates:
      - type: quarterly
        dates: ["01-01", "04-01", "07-01", "10-01"]

  excluded_classes:
    - employee_type: intern
    - employee_type: contractor
    - union_code: LOCAL_123

  special_rules:
    immediate_401k:
      applies_to: ["401k_deferral"]
      minimum_age: 18
      minimum_service_months: 0
      entry_dates:
        - type: immediate
```

### Vectorized Eligibility Engine
```python
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List

class VectorizedEligibilityEngine:
    def __init__(self, plan_rules: EligibilityRules):
        self.plan_rules = plan_rules
        self.service_cache = {}  # Cache for unchanged employees

    def determine_eligibility_batch(self, employees_df: pd.DataFrame, as_of_date: datetime) -> pd.DataFrame:
        """Process eligibility for entire employee population efficiently"""

        # Initialize eligibility columns
        employees_df['is_eligible'] = False
        employees_df['eligibility_reason'] = 'pending'
        employees_df['entry_date'] = pd.NaT

        # 1. Vectorized exclusion check
        exclusion_mask = self._check_exclusions_vectorized(employees_df)
        employees_df.loc[exclusion_mask, 'eligibility_reason'] = 'excluded'

        # 2. Vectorized age check
        age_eligible_mask = self._check_age_vectorized(employees_df, as_of_date)
        age_failed = ~age_eligible_mask & ~exclusion_mask
        employees_df.loc[age_failed, 'eligibility_reason'] = 'pending_age'

        # 3. Vectorized service check
        service_eligible_mask = self._check_service_vectorized(employees_df, as_of_date)
        service_failed = ~service_eligible_mask & age_eligible_mask & ~exclusion_mask
        employees_df.loc[service_failed, 'eligibility_reason'] = 'pending_service'

        # 4. Vectorized hours check (if required)
        if self.plan_rules.minimum_hours > 0:
            hours_eligible_mask = self._check_hours_vectorized(employees_df, as_of_date)
            hours_failed = ~hours_eligible_mask & age_eligible_mask & service_eligible_mask & ~exclusion_mask
            employees_df.loc[hours_failed, 'eligibility_reason'] = 'pending_hours'
        else:
            hours_eligible_mask = True

        # 5. Calculate final eligibility
        final_eligible_mask = (
            age_eligible_mask &
            service_eligible_mask &
            hours_eligible_mask &
            ~exclusion_mask
        )

        employees_df.loc[final_eligible_mask, 'is_eligible'] = True
        employees_df.loc[final_eligible_mask, 'eligibility_reason'] = 'eligible'

        # 6. Vectorized entry date calculation
        employees_df.loc[final_eligible_mask, 'entry_date'] = self._calculate_entry_dates_vectorized(
            employees_df.loc[final_eligible_mask], as_of_date
        )

        return employees_df

    def _check_exclusions_vectorized(self, employees_df: pd.DataFrame) -> pd.Series:
        """Check employee class exclusions using boolean masking"""
        exclusion_mask = pd.Series(False, index=employees_df.index)

        for exclusion in self.plan_rules.excluded_classes:
            if 'employee_type' in exclusion:
                exclusion_mask |= employees_df['employee_type'] == exclusion['employee_type']
            if 'union_code' in exclusion:
                exclusion_mask |= employees_df['union_code'] == exclusion['union_code']

        return exclusion_mask

    def _check_age_vectorized(self, employees_df: pd.DataFrame, as_of_date: datetime) -> pd.Series:
        """Calculate ages and check minimum age requirement"""
        # Vectorized age calculation
        birth_dates = pd.to_datetime(employees_df['birth_date'])
        ages = (as_of_date - birth_dates).dt.days / 365.25

        return ages >= self.plan_rules.minimum_age

    def _check_service_vectorized(self, employees_df: pd.DataFrame, as_of_date: datetime) -> pd.Series:
        """Calculate service and check minimum service requirement with caching"""
        # Use cached service for unchanged employees
        new_employees = employees_df[~employees_df['employee_id'].isin(self.service_cache)]

        if len(new_employees) > 0:
            # Vectorized service calculation for new/changed employees
            hire_dates = pd.to_datetime(new_employees['hire_date'])
            service_months = ((as_of_date - hire_dates).dt.days / 30.44).round()

            # Update cache
            service_dict = dict(zip(new_employees['employee_id'], service_months))
            self.service_cache.update(service_dict)

        # Apply cached service values
        employees_df['calculated_service_months'] = employees_df['employee_id'].map(self.service_cache)

        return employees_df['calculated_service_months'] >= self.plan_rules.minimum_service_months

    def _calculate_entry_dates_vectorized(self, eligible_df: pd.DataFrame, as_of_date: datetime) -> pd.Series:
        """Calculate entry dates using vectorized operations"""
        if self.plan_rules.entry_dates.type == 'immediate':
            return pd.Series(as_of_date, index=eligible_df.index)

        elif self.plan_rules.entry_dates.type == 'quarterly':
            # Find next quarterly entry date for each employee
            quarter_dates = pd.to_datetime([
                f"{as_of_date.year}-{date}" for date in self.plan_rules.entry_dates.dates
            ])

            # Vectorized next quarter calculation
            next_quarters = []
            for _ in eligible_df.index:
                future_quarters = quarter_dates[quarter_dates > as_of_date]
                if len(future_quarters) > 0:
                    next_quarters.append(future_quarters[0])
                else:
                    # Next year's first quarter
                    next_year_first = pd.to_datetime(f"{as_of_date.year + 1}-{self.plan_rules.entry_dates.dates[0]}")
                    next_quarters.append(next_year_first)

            return pd.Series(next_quarters, index=eligible_df.index)

        # Add other entry date types as needed
        return pd.Series(as_of_date, index=eligible_df.index)

# Usage example
def process_daily_eligibility(duckdb_conn, plan_rules, as_of_date):
    # Load employee data efficiently
    employees_df = duckdb_conn.execute("""
        SELECT employee_id, birth_date, hire_date, employee_type, union_code
        FROM dim_employees
        WHERE active_flag = true
    """).df()

    # Process eligibility
    engine = VectorizedEligibilityEngine(plan_rules)
    result_df = engine.determine_eligibility_batch(employees_df, as_of_date)

    # Generate events for newly eligible employees
    newly_eligible = result_df[
        (result_df['is_eligible'] == True) &
        (result_df['employee_id'].isin(get_previously_ineligible_employees()))
    ]

    # Bulk insert eligibility events
    if len(newly_eligible) > 0:
        eligibility_events = create_eligibility_events_batch(newly_eligible, as_of_date)
        insert_events_batch(duckdb_conn, eligibility_events)

    return result_df
```

---

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Daily Processing | <30 seconds for 100K employees | Vectorized DataFrame operations with Pandas/Polars |
| Point-in-Time Queries | <100ms response time | Optimized eligibility snapshots with indexed lookups |
| Cache Hit Rate | 95% for unchanged employees | Service computation caching with employment history tracking |
| Memory Usage | <4GB for 100K employee dataset | Efficient data types and incremental processing |
| Concurrent Scenarios | <2 minutes for 10 parallel scenarios | Process-based parallelism with isolated DataFrames |

## Dependencies
- E021: DC Plan Data Model (must be complete)
- Employee demographic data from workforce simulation
- Employment history including hire/term/rehire dates
- Pandas/Polars for vectorized DataFrame operations
- NumPy for efficient numerical computations
- Pydantic for configuration validation
- DuckDB for optimized analytical queries

## Risks
- **Risk**: Complex service calculation rules for rehires
- **Mitigation**: Implement comprehensive test scenarios
- **Risk**: Performance with daily eligibility checks for 100K+ employees
- **Mitigation**: Incremental processing of changed employees only

## Estimated Effort
**Total Story Points**: 56 points
**Estimated Duration**: 3-4 sprints

---

## Definition of Done
- [ ] All eligibility rules implemented and tested
- [ ] Performance benchmarks met (<5 min for 100K employees)
- [ ] Comprehensive test coverage including edge cases
- [ ] Integration with event stream complete
- [ ] Configuration documentation with examples
- [ ] Compliance review completed
