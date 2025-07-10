# Epic E023: Basic Enrollment Engine

## Epic Overview

### Summary
Develop an enrollment simulation engine that models participant enrollment behavior including auto-enrollment, opt-out rates, and voluntary enrollment patterns based on demographic characteristics.

### Business Value
- Enables accurate participation rate projections for plan design decisions
- Models the financial impact of auto-enrollment features saving $1-5M annually
- Provides insights into employee savings behavior by demographic segments

### Success Criteria
- ✅ Models enrollment with 95% accuracy vs historical data
- ✅ Supports auto-enrollment with configurable default rates
- ✅ Simulates realistic opt-out and escalation behavior
- ✅ Generates detailed enrollment analytics by segment

---

## User Stories

### Story 1: Auto-Enrollment Logic (13 points)
**As a** plan sponsor
**I want** to model auto-enrollment impact
**So that** I can predict participation rates and costs

**Acceptance Criteria:**
- Configurable auto-enrollment default rate (3%, 6%, etc.)
- Opt-out window modeling (30, 60, 90 days)
- Different defaults by employee class
- Creates ENROLLMENT events with source = "auto"
- Tracks opt-out events and reasons

### Story 2: Voluntary Enrollment Modeling (8 points)
**As a** workforce analyst
**I want** realistic voluntary enrollment rates
**So that** my projections match actual behavior

**Acceptance Criteria:**
- Enrollment probability curves by age/salary/tenure
- Time-to-enrollment distributions
- Deferral rate selection patterns
- Calibration against historical data
- Supports re-enrollment campaigns

### Story 3: Deferral Rate Selection (8 points)
**As a** benefits consultant
**I want** to model initial deferral elections
**So that** I can project employee and employer contributions

**Acceptance Criteria:**
- Distribution of deferral rates by demographic
- Common clustering (3%, 6%, 10%, max)
- Impact of match formula on elections
- Roth vs traditional split modeling
- Behavioral anchoring effects

### Story 4: Auto-Escalation Implementation (5 points)
**As a** retirement plan committee member
**I want** to model automatic increase programs
**So that** I can assess long-term savings improvements

**Acceptance Criteria:**
- Annual increase amount (1%, 2%)
- Maximum escalation cap (10%, 15%)
- Opt-out rates for increases
- Timing of increases (anniversary, Jan 1)
- Impact on average deferral rates

### Story 5: Enrollment Analytics & Reporting (5 points)
**As a** CFO
**I want** clear enrollment projections
**So that** I can budget for retirement contributions

**Acceptance Criteria:**
- Participation rate by year
- Average deferral rate trends
- Opt-out analysis by segment
- New hire vs existing employee patterns
- Scenario comparison reports

---

## Technical Specifications

### Enrollment Configuration
```yaml
enrollment_config:
  auto_enrollment:
    enabled: true
    default_deferral_rate: 0.06
    opt_out_window_days: 90

    # Opt-out rates by demographic
    opt_out_rates:
      by_age:
        - {min: 18, max: 25, rate: 0.35}
        - {min: 26, max: 35, rate: 0.20}
        - {min: 36, max: 50, rate: 0.15}
        - {min: 51, max: 99, rate: 0.10}

      by_salary:
        - {min: 0, max: 30000, rate: 0.40}
        - {min: 30001, max: 50000, rate: 0.25}
        - {min: 50001, max: 100000, rate: 0.15}
        - {min: 100001, max: 999999, rate: 0.05}

  voluntary_enrollment:
    # Probability of enrolling within first year
    enrollment_curves:
      baseline: 0.60
      age_factor: 0.01  # +1% per year over 25
      tenure_factor: 0.05  # +5% per year of service

  deferral_distributions:
    # Common deferral rate selections
    rates:
      - {rate: 0.03, probability: 0.25}  # Match threshold
      - {rate: 0.06, probability: 0.35}  # Common default
      - {rate: 0.10, probability: 0.20}  # Round number
      - {rate: 0.15, probability: 0.10}  # High savers
      - {rate: "max", probability: 0.10} # Max contributors
```

### Enrollment Simulation Logic
```python
def simulate_enrollment(employee, eligibility_date, config):
    if config.auto_enrollment.enabled:
        # Auto-enroll on eligibility date
        enrollment_date = eligibility_date
        deferral_rate = config.auto_enrollment.default_deferral_rate

        # Check for opt-out
        opt_out_prob = get_opt_out_probability(employee, config)
        if random.random() < opt_out_prob:
            opt_out_date = enrollment_date + timedelta(
                days=random.randint(1, config.opt_out_window_days)
            )
            return create_opt_out_event(employee, opt_out_date)

        return create_enrollment_event(
            employee, enrollment_date, deferral_rate, "auto"
        )

    else:
        # Model voluntary enrollment
        enroll_prob = calculate_enrollment_probability(employee, config)
        if random.random() < enroll_prob:
            # Time to enrollment
            days_to_enroll = sample_enrollment_timing(employee)
            enrollment_date = eligibility_date + timedelta(days=days_to_enroll)

            # Select deferral rate
            deferral_rate = sample_deferral_rate(employee, config)

            return create_enrollment_event(
                employee, enrollment_date, deferral_rate, "voluntary"
            )
```

---

## Dependencies
- E021: DC Plan Data Model (event schema)
- E022: Eligibility Engine (eligible population)
- Historical enrollment data for calibration

## Risks
- **Risk**: Behavioral modeling accuracy
- **Mitigation**: Calibrate against 3+ years of actual data
- **Risk**: Auto-enrollment legal compliance
- **Mitigation**: Include all required notices and timing

## Estimated Effort
**Total Story Points**: 39 points
**Estimated Duration**: 2-3 sprints

---

## Definition of Done
- [ ] Auto-enrollment logic fully implemented
- [ ] Voluntary enrollment modeling calibrated
- [ ] Deferral rate distributions validated
- [ ] Auto-escalation features complete
- [ ] Analytics reports designed and tested
- [ ] Performance targets met
- [ ] User documentation complete
