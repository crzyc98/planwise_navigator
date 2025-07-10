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
- ✅ Processes daily eligibility updates in <5 minutes
- ✅ Generates clear audit trail for eligibility determinations

---

## User Stories

### Story 1: Core Eligibility Calculator (13 points)
**As a** benefits administrator
**I want** automated eligibility determination based on plan rules
**So that** employees are enrolled at the right time without manual tracking

**Acceptance Criteria:**
- Evaluates age (18, 21, or no minimum)
- Evaluates service (immediate, 6 months, 12 months)
- Evaluates hours worked (500, 1000, or no minimum)
- Handles entry dates (immediate, monthly, quarterly, semi-annual)
- Creates ELIGIBILITY_START events

### Story 2: Employee Classification Rules (8 points)
**As a** plan sponsor
**I want** different eligibility rules by employee class
**So that** I can exclude certain groups (e.g., interns, contractors)

**Acceptance Criteria:**
- Supports inclusion/exclusion by job level, location, division
- Handles union vs non-union employees
- Applies statutory exclusions (non-resident aliens)
- Configurable via YAML without code changes

### Story 3: Service Computation Methods (8 points)
**As a** compliance officer
**I want** accurate service calculations under multiple methods
**So that** we meet ERISA requirements for different plan types

**Acceptance Criteria:**
- Elapsed time method for service calculation
- Hours counting method with 1000-hour threshold
- Handles breaks in service and rehires
- Supports "Rule of Parity" for vesting

### Story 4: Entry Date Processing (5 points)
**As a** payroll administrator
**I want** automatic entry date calculations
**So that** eligible employees start on the correct date

**Acceptance Criteria:**
- Calculates next entry date based on plan rules
- Handles immediate, monthly, quarterly, semi-annual entry
- Creates advance notifications (30/60/90 days)
- Supports dual entry dates for 401(k) vs match

### Story 5: Eligibility Change Events (5 points)
**As an** audit manager
**I want** complete tracking of eligibility changes
**So that** I can explain why someone became eligible or lost eligibility

**Acceptance Criteria:**
- Tracks all eligibility status changes
- Records reason for change (age, service, hours, class)
- Supports eligibility loss scenarios
- Provides point-in-time eligibility queries

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

### Eligibility Engine Algorithm
```python
def determine_eligibility(employee, plan_rules, as_of_date):
    # Check exclusions first
    if is_excluded_class(employee, plan_rules):
        return EligibilityStatus.EXCLUDED

    # Check age requirement
    age = calculate_age(employee.birth_date, as_of_date)
    if age < plan_rules.minimum_age:
        return EligibilityStatus.PENDING_AGE

    # Check service requirement
    service_months = calculate_service(employee, plan_rules.service_method)
    if service_months < plan_rules.minimum_service_months:
        return EligibilityStatus.PENDING_SERVICE

    # Check hours requirement
    if plan_rules.minimum_hours > 0:
        hours = calculate_hours_worked(employee, as_of_date)
        if hours < plan_rules.minimum_hours:
            return EligibilityStatus.PENDING_HOURS

    # Calculate entry date
    entry_date = calculate_entry_date(as_of_date, plan_rules.entry_dates)

    return EligibilityStatus.ELIGIBLE, entry_date
```

---

## Dependencies
- E021: DC Plan Data Model (must be complete)
- Employee demographic data from workforce simulation
- Employment history including hire/term/rehire dates

## Risks
- **Risk**: Complex service calculation rules for rehires
- **Mitigation**: Implement comprehensive test scenarios
- **Risk**: Performance with daily eligibility checks for 100K+ employees
- **Mitigation**: Incremental processing of changed employees only

## Estimated Effort
**Total Story Points**: 39 points
**Estimated Duration**: 2-3 sprints

---

## Definition of Done
- [ ] All eligibility rules implemented and tested
- [ ] Performance benchmarks met (<5 min for 100K employees)
- [ ] Comprehensive test coverage including edge cases
- [ ] Integration with event stream complete
- [ ] Configuration documentation with examples
- [ ] Compliance review completed
