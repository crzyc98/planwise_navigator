# Epic E024: Contribution Calculator with IRS Limits

## Epic Overview

### Summary
Build a comprehensive contribution calculation engine that computes employee deferrals and employer contributions while enforcing all applicable IRS limits and plan-specific rules.

### Business Value
- Ensures 100% compliance with IRS contribution limits avoiding penalties
- Accurately projects employer costs for budgeting ($10-50M annually)
- Prevents excess contributions that require costly corrections

### Success Criteria
- ✅ Calculates contributions with 100% accuracy
- ✅ Enforces all IRS limits (402(g), 415(c), highly compensated)
- ✅ Handles complex timing scenarios (bonuses, raises, terminations)
- ✅ Processes 100K employees in <2 minutes per pay period

---

## User Stories

### Story 1: Basic Contribution Calculations (8 points)
**As a** payroll administrator
**I want** accurate contribution calculations each pay period
**So that** the correct amounts are deducted and matched

**Acceptance Criteria:**
- Calculates employee deferrals based on elected percentage
- Handles both percentage and dollar amount elections
- Supports bi-weekly, semi-monthly, monthly pay frequencies
- Creates CONTRIBUTION events for each calculation
- Handles mid-year rate changes

### Story 2: IRS Limit Enforcement (13 points)
**As a** compliance officer
**I want** automatic enforcement of all IRS limits
**So that** we avoid excess contributions and penalties

**Acceptance Criteria:**
- 402(g) elective deferral limit ($23,000 for 2024)
- 415(c) annual additions limit ($69,000 for 2024)
- Age 50+ catch-up contributions ($7,500 for 2024)
- Highly compensated employee limits
- Automatic stop when limits reached
- Year-end true-up calculations

### Story 3: Compensation Definitions (8 points)
**As a** plan administrator
**I want** flexible compensation definitions
**So that** different pay types are handled correctly

**Acceptance Criteria:**
- W-2 compensation baseline
- Include/exclude bonuses, commissions, overtime
- Pre/post severance compensation rules
- Safe harbor compensation definitions
- Handles compensation over IRS limit ($345,000)

### Story 4: Roth Contribution Support (5 points)
**As an** employee
**I want** to split contributions between traditional and Roth
**So that** I can optimize my tax strategy

**Acceptance Criteria:**
- Separate tracking of traditional vs Roth
- Split percentage configuration
- Combined limit enforcement
- Roth in-plan conversions
- Separate employer match treatment

### Story 5: Timing & Proration Logic (8 points)
**As a** finance manager
**I want** accurate handling of partial periods
**So that** contributions are correct for new hires and terminations

**Acceptance Criteria:**
- Pro-rates contributions for partial pay periods
- Handles hire date timing
- Termination date contribution rules
- Leave of absence suspension
- Rehire contribution resumption

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

### Contribution Calculation Engine
```python
def calculate_contribution(employee, pay_period, plan_config):
    # Get eligible compensation
    compensation = calculate_eligible_compensation(
        employee.gross_pay,
        plan_config.compensation_definition
    )

    # Apply IRS compensation limit
    ytd_compensation = get_ytd_compensation(employee)
    if ytd_compensation + compensation > plan_config.irs_limits.compensation:
        compensation = plan_config.irs_limits.compensation - ytd_compensation

    # Calculate employee deferral
    if employee.deferral_type == "percentage":
        deferral = compensation * employee.deferral_rate
    else:
        deferral = min(employee.deferral_amount, compensation)

    # Check 402(g) limit
    ytd_deferrals = get_ytd_deferrals(employee)
    limit = plan_config.irs_limits.elective_deferral
    if employee.age >= 50:
        limit += plan_config.irs_limits.catch_up

    if ytd_deferrals + deferral > limit:
        deferral = limit - ytd_deferrals

    # Calculate employer match
    match = calculate_match(deferral, compensation, plan_config.match_formula)

    # Check 415(c) limit
    ytd_additions = get_ytd_annual_additions(employee)
    total_additions = deferral + match
    if ytd_additions + total_additions > plan_config.irs_limits.annual_additions:
        # Reduce match first, then deferral
        excess = (ytd_additions + total_additions) - plan_config.irs_limits.annual_additions
        match = max(0, match - excess)
        if match == 0:
            deferral = deferral - (excess - original_match)

    return ContributionResult(
        employee_deferral=deferral,
        employer_match=match,
        compensation_used=compensation,
        limits_applied=limits_applied
    )
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

## Dependencies
- E021: DC Plan Data Model (event schema)
- E023: Enrollment Engine (deferral elections)
- Payroll integration for compensation data
- Annual IRS limit updates

## Risks
- **Risk**: Complex limit interaction scenarios
- **Mitigation**: Comprehensive test scenarios from actual cases
- **Risk**: Performance with real-time calculations
- **Mitigation**: Implement caching for YTD values

## Estimated Effort
**Total Story Points**: 42 points
**Estimated Duration**: 3 sprints

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
