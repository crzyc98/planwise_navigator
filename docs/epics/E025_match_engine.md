# Epic E025: Match Engine with Formula Support

## Epic Overview

### Summary
Create a flexible employer match calculation engine supporting complex multi-tier formulas, true-up calculations, and various match types used in modern 401(k) plans.

### Business Value
- Enables accurate modeling of employer match costs ($5-50M annually)
- Supports optimization of match formulas to maximize participation
- Reduces manual calculations and errors in match processing

### Success Criteria
- ✅ Supports all common match formula types
- ✅ Calculates matches with 100% accuracy
- ✅ Handles true-up and stretch match scenarios
- ✅ Processes complex formulas in <100ms per employee

---

## User Stories

### Story 1: Basic Match Formulas (8 points)
**As a** plan sponsor
**I want** to configure standard match formulas
**So that** I can model different match strategies

**Acceptance Criteria:**
- Simple percentage match (50% of deferrals)
- Tiered match (100% on first 3%, 50% on next 2%)
- Dollar-for-dollar match up to percentage
- Discretionary match capability
- Safe harbor match formulas

### Story 2: Stretch Match Implementation (8 points)
**As a** benefits designer
**I want** stretch match formulas
**So that** I can incentivize higher savings rates

**Acceptance Criteria:**
- Stretch match calculations (25% on first 12%)
- Graduated tier formulas
- Maximum match caps (% of compensation)
- Vesting schedule integration
- Comparison tools for formula impact

### Story 3: True-Up Calculations (13 points)
**As a** payroll manager
**I want** automatic true-up calculations
**So that** employees receive their full match regardless of timing

**Acceptance Criteria:**
- Annual true-up for employees who max early
- Handles variable compensation timing
- Accounts for unpaid leaves
- Termination true-up rules
- Creates true-up payment events

### Story 4: Vesting Integration (5 points)
**As a** plan administrator
**I want** vesting schedules applied to matches
**So that** we retain employees and reduce costs

**Acceptance Criteria:**
- Cliff vesting (3-year)
- Graded vesting (2-6 year)
- Service computation for vesting
- Immediate vesting for safe harbor
- Forfeiture calculations

### Story 5: Match Optimization Analytics (8 points)
**As a** CFO
**I want** to compare different match formulas
**So that** I can optimize cost vs participation

**Acceptance Criteria:**
- Side-by-side formula comparison
- Cost projections by formula
- Participation impact modeling
- Employee outcome analysis
- ROI calculations for match spend

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

### Match Calculation Engine
```python
def calculate_match(employee_deferral_rate, compensation, match_formula):
    """Calculate employer match based on formula configuration"""
    total_match = 0
    remaining_deferral = employee_deferral_rate

    for tier in match_formula.tiers:
        # Calculate contribution within this tier
        tier_width = tier.employee_max - tier.employee_min
        tier_contribution = min(remaining_deferral - tier.employee_min, tier_width)

        if tier_contribution > 0:
            # Apply match rate for this tier
            tier_match = tier_contribution * tier.match_rate
            total_match += tier_match
            remaining_deferral -= tier_contribution

        if remaining_deferral <= tier.employee_min:
            break

    # Apply maximum match cap
    if match_formula.max_match_percentage:
        total_match = min(total_match, match_formula.max_match_percentage)

    # Convert to dollar amount
    match_dollars = total_match * compensation

    return match_dollars

def calculate_true_up(employee, plan_year, match_formula):
    """Calculate year-end true-up amount"""
    # Get actual YTD contributions
    ytd_deferrals = get_ytd_deferrals(employee, plan_year)
    ytd_compensation = get_ytd_compensation(employee, plan_year)
    ytd_match_paid = get_ytd_match(employee, plan_year)

    # Calculate what match should have been
    annual_deferral_rate = ytd_deferrals / ytd_compensation
    calculated_match = calculate_match(
        annual_deferral_rate,
        ytd_compensation,
        match_formula
    )

    # True-up is the difference
    true_up_amount = calculated_match - ytd_match_paid

    return max(0, true_up_amount)  # No negative true-ups
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

## Dependencies
- E021: DC Plan Data Model (event schema)
- E024: Contribution Calculator (compensation amounts)
- Employee demographic data for modeling

## Risks
- **Risk**: Complex true-up edge cases
- **Mitigation**: Test with real payroll scenarios
- **Risk**: Formula change mid-year handling
- **Mitigation**: Effective date tracking on all formulas

## Estimated Effort
**Total Story Points**: 42 points
**Estimated Duration**: 3 sprints

---

## Definition of Done
- [ ] All match formula types implemented
- [ ] True-up calculations accurate
- [ ] Vesting schedules integrated
- [ ] Formula comparison tools complete
- [ ] Performance benchmarks met
- [ ] Edge cases documented and tested
- [ ] User documentation with examples
