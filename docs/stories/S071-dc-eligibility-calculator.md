# Story S071: Core Eligibility Calculator

**Epic**: E022 - Eligibility Engine
**Story Points**: 13
**Priority**: High
**Status**: Ready for Development

## User Story
**As a** benefits administrator
**I want** automated eligibility determination based on plan rules
**So that** employees are enrolled at the right time without manual tracking

## Context
This story implements the core eligibility calculation logic that determines when employees become eligible for plan participation based on age, service, hours, and entry date requirements.

## Acceptance Criteria
1. **Age Evaluation**
   - Support minimum age requirements: 18, 21, or none
   - Calculate age based on birth date
   - Handle leap year birthdays correctly

2. **Service Evaluation**
   - Support service requirements: immediate, 6 months, 12 months
   - Use elapsed time method by default
   - Handle breaks in service correctly

3. **Hours Evaluation**
   - Support hour requirements: 500, 1000, or none
   - Look back 12 months for hour calculation
   - Include all compensated hours

4. **Entry Date Calculation**
   - Support immediate, monthly, quarterly, semi-annual entry
   - Calculate next available entry date
   - Handle employees meeting requirements between entry dates

5. **Event Generation**
   - Create ELIGIBILITY_START events
   - Include eligibility details in event
   - Generate events for daily processing

## Technical Details

### Implementation Approach
```python
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional, Tuple

class EligibilityCalculator:
    def __init__(self, plan_rules: PlanEligibilityRules):
        self.rules = plan_rules

    def check_eligibility(self, employee: Employee, as_of_date: date) -> Tuple[bool, Optional[date], str]:
        """
        Check if employee is eligible and return entry date if eligible
        Returns: (is_eligible, entry_date, reason)
        """
        # Check exclusions first
        if self._is_excluded_class(employee):
            return False, None, "excluded_employee_class"

        # Check age requirement
        if not self._meets_age_requirement(employee, as_of_date):
            return False, None, "pending_age_requirement"

        # Check service requirement
        if not self._meets_service_requirement(employee, as_of_date):
            return False, None, "pending_service_requirement"

        # Check hours requirement
        if not self._meets_hours_requirement(employee, as_of_date):
            return False, None, "pending_hours_requirement"

        # Calculate entry date
        entry_date = self._calculate_entry_date(as_of_date)

        return True, entry_date, "all_requirements_met"

    def _meets_age_requirement(self, employee: Employee, as_of_date: date) -> bool:
        if self.rules.minimum_age is None:
            return True

        age = self._calculate_age(employee.birth_date, as_of_date)
        return age >= self.rules.minimum_age

    def _calculate_age(self, birth_date: date, as_of_date: date) -> int:
        # Handle leap year birthdays
        try:
            birthday_this_year = birth_date.replace(year=as_of_date.year)
        except ValueError:  # Feb 29 in non-leap year
            birthday_this_year = birth_date.replace(year=as_of_date.year, day=28)

        if birthday_this_year <= as_of_date:
            return as_of_date.year - birth_date.year
        else:
            return as_of_date.year - birth_date.year - 1

    def _meets_service_requirement(self, employee: Employee, as_of_date: date) -> bool:
        if self.rules.minimum_service_months == 0:
            return True

        # Calculate service using elapsed time method
        service_months = self._calculate_elapsed_service(employee, as_of_date)
        return service_months >= self.rules.minimum_service_months

    def _calculate_elapsed_service(self, employee: Employee, as_of_date: date) -> int:
        # Handle breaks in service
        total_service = 0
        for period in employee.service_periods:
            start = period.start_date
            end = period.end_date or as_of_date

            if end > as_of_date:
                end = as_of_date

            months = (end.year - start.year) * 12 + (end.month - start.month)
            total_service += months

        return total_service

    def _calculate_entry_date(self, eligibility_date: date) -> date:
        if self.rules.entry_dates.type == "immediate":
            return eligibility_date

        elif self.rules.entry_dates.type == "monthly":
            # First of next month
            if eligibility_date.day == 1:
                return eligibility_date
            else:
                return (eligibility_date + relativedelta(months=1)).replace(day=1)

        elif self.rules.entry_dates.type == "quarterly":
            # Next quarterly entry date
            quarterly_dates = [date(eligibility_date.year, m, 1) for m in [1, 4, 7, 10]]
            future_dates = [d for d in quarterly_dates if d >= eligibility_date]

            if future_dates:
                return future_dates[0]
            else:
                return date(eligibility_date.year + 1, 1, 1)

        elif self.rules.entry_dates.type == "semi_annual":
            # January 1 or July 1
            if eligibility_date <= date(eligibility_date.year, 7, 1):
                return date(eligibility_date.year, 7, 1)
            else:
                return date(eligibility_date.year + 1, 1, 1)
```

### Daily Processing Logic
```python
def process_daily_eligibility(as_of_date: date):
    """Process eligibility for all employees"""
    calculator = EligibilityCalculator(load_plan_rules())
    events = []

    # Get employees not yet eligible
    pending_employees = get_pending_eligibility_employees()

    for employee in pending_employees:
        is_eligible, entry_date, reason = calculator.check_eligibility(employee, as_of_date)

        if is_eligible and entry_date == as_of_date:
            # Create eligibility start event
            event = RetirementPlanEvent(
                event_id=generate_uuid(),
                employee_id=employee.id,
                event_type=RetirementEventType.ELIGIBILITY_START,
                effective_date=entry_date,
                plan_year=entry_date.year,
                details={
                    "age_at_eligibility": calculator._calculate_age(employee.birth_date, entry_date),
                    "service_months": calculator._calculate_elapsed_service(employee, entry_date),
                    "eligibility_reason": reason,
                    "plan_rules_version": calculator.rules.version
                }
            )
            events.append(event)

    # Publish events
    publish_events(events)

    return len(events)
```

## Testing Requirements
1. **Eligibility Scenarios**
   - Test all combinations of age/service/hours requirements
   - Verify entry date calculations for all types
   - Test edge cases (leap years, month boundaries)

2. **Service Calculation Tests**
   - Single continuous service period
   - Multiple service periods (rehires)
   - Breaks in service handling

3. **Performance Tests**
   - Process 10K employees in <30 seconds
   - Daily incremental processing efficiency

## Implementation Notes
- Use elapsed time method as default (most common)
- Consider caching eligibility checks for performance
- Entry dates should align with payroll periods
- Generate advance notifications for HR

## Dependencies
- Employee demographic and service data
- Plan rules configuration (from E021)
- Event publishing infrastructure

## Definition of Done
- [ ] Calculator handles all requirement types
- [ ] Entry date logic verified for all patterns
- [ ] Event generation working correctly
- [ ] Unit tests cover all scenarios (>95% coverage)
- [ ] Performance benchmarks met
- [ ] Integration with daily processing tested
- [ ] Documentation includes examples
