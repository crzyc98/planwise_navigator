# Product Requirements Document: Defined Contribution Plan Modeling

**Version:** 2.0
**Date:** January 10, 2025
**Author:** Nicholas Amaral
**Status:** Ready for Epic Development

---

## 1. Executive Summary

### Product Vision
Transform PlanWise Navigator into a comprehensive Total Rewards planning platform by adding sophisticated Defined Contribution (DC) retirement plan modeling capabilities. This extension will enable plan sponsors to instantly model the financial and participation impact of plan design changes through configuration-driven scenario analysis.

### Strategic Value
- **Unified Platform**: Single source of truth for workforce costs AND retirement benefits
- **Design Optimization**: Data-driven plan design decisions worth millions annually
- **Competitive Advantage**: Replace expensive actuarial consulting with real-time modeling

### Target Market
- Fortune 500 HR/Finance teams managing 401(k) plans
- Benefits consultants modeling client plan changes
- Mid-market companies optimizing retirement benefits

---

## 2. Problem Statement

### Current State Pain Points
1. **Siloed Analysis**: Workforce planning and retirement modeling use separate tools
2. **Static Projections**: Plan design changes require weeks of actuarial analysis
3. **Limited Scenarios**: Cost constraints limit testing to 2-3 alternatives
4. **Opaque Assumptions**: Black-box models prevent understanding of drivers

### Business Impact
- $10-50M annual employer match costs decided with limited analysis
- 20-30% of employees under-saving due to suboptimal plan design
- 4-8 week delays for plan design change modeling

### Solution Requirements
- Real-time scenario modeling (<5 minutes per scenario)
- Configuration-driven plan rules (no code changes)
- Transparent, auditable calculations
- Integration with existing workforce data

---

## 3. Functional Requirements

### 3.1 Core Capabilities

#### Eligibility Engine
- **Requirement**: Model complex eligibility rules (age, service, hours, employee class)
- **Configuration**: YAML-based rule definitions
- **Output**: Daily eligibility status events for each employee

#### Enrollment Engine
- **Requirement**: Simulate enrollment behavior including auto-enrollment, opt-out rates
- **Configuration**: Participation curves by demographic segments
- **Output**: Enrollment events with deferral elections

#### Contribution Calculator
- **Requirement**: Calculate employee deferrals and employer contributions
- **Constraints**: IRS limits (402(g), 415(c), ADP/ACP testing)
- **Output**: Biweekly contribution events with detailed breakdowns

#### Match Engine
- **Requirement**: Support complex match formulas (tiered, true-up, stretch)
- **Configuration**: Formula templates with parameter substitution
- **Output**: Match calculation events with audit trail

### 3.2 Scenario Framework

#### Plan Design Configuration
```yaml
plan_design:
  eligibility:
    minimum_age: 21
    minimum_service_months: 12
    entry_dates: [quarterly]  # immediate, monthly, quarterly, semi-annual
    hours_requirement: 1000

  auto_enrollment:
    enabled: true
    default_rate: 0.06
    annual_increase: 0.01
    maximum_rate: 0.10
    opt_out_window_days: 90

  employer_contributions:
    match_formula:
      - tier: 1
        employee_max: 0.03
        match_rate: 1.00
      - tier: 2
        employee_max: 0.05
        match_rate: 0.50

    safe_harbor:
      type: basic  # basic, enhanced, qaca
      vesting: immediate

    profit_sharing:
      enabled: false
      formula: pro_rata  # pro_rata, new_comparability, age_weighted
```

#### Scenario Comparison
- **Baseline**: Current plan design configuration
- **Alternatives**: Up to 10 concurrent scenarios
- **Outputs**: Side-by-side comparison of key metrics
- **Time Horizon**: 1-10 year projections

### 3.3 Reporting & Analytics

#### Standard Reports
1. **Participation Analysis**
   - Rates by age, tenure, salary band
   - Enrollment timing distributions
   - Opt-out analysis

2. **Cost Projections**
   - Employer contribution forecasts
   - Employee deferral projections
   - Cash flow timing

3. **Plan Health Metrics**
   - Average deferral rates
   - Retirement readiness scores
   - Demographic utilization

#### Scenario Comparison Dashboard
- Multi-year cost differentials
- Participation rate changes
- Employee outcome improvements
- ROI analysis

---

## 4. Technical Architecture

### 4.1 Integration with PlanWise Navigator

#### Event Schema Extension
```python
# New event types for DC plan modeling
class RetirementPlanEvent(BaseEvent):
    employee_id: str
    event_type: Literal[
        "ELIGIBILITY_START",
        "ENROLLMENT",
        "DEFERRAL_CHANGE",
        "CONTRIBUTION",
        "MATCH_CALCULATION",
        "DISTRIBUTION",
        "LOAN"
    ]
    effective_date: date
    plan_year: int
    details: Dict[str, Any]
```

#### Data Pipeline Integration
- **Staging Layer**: New staging models for plan configuration
- **Intermediate Layer**: Eligibility and enrollment logic models
- **Mart Layer**: Contribution projections and analytics

### 4.2 Performance Requirements

| Metric | Requirement | Rationale |
|--------|-------------|-----------|
| Single Scenario Runtime | <2 minutes | Interactive analysis |
| 10-Year Projection | <5 minutes | Planning horizon |
| 100K Employee Scale | <10 minutes | Enterprise support |
| Concurrent Scenarios | 10 parallel | Comparison analysis |

### 4.3 Data Requirements

#### Input Data
- Employee census (from existing workforce data)
- Current plan participation (if available)
- Historical participation rates (for calibration)
- Plan design documents

#### Configuration Data
- Plan rules (YAML format)
- IRS limits (annual updates)
- Demographic assumptions
- Behavioral parameters

---

## 5. Success Metrics

### Business Metrics
- **Adoption**: 80% of plan sponsors using scenario modeling within 6 months
- **Decision Impact**: 20% improvement in plan design efficiency
- **Cost Optimization**: 5-10% reduction in unnecessary employer contributions
- **Employee Outcomes**: 15% increase in average deferral rates

### Technical Metrics
- **Performance**: 95% of scenarios complete within SLA
- **Accuracy**: <0.1% variance from actuarial projections
- **Reliability**: 99.9% uptime for scenario engine
- **Scalability**: Support 1M employee simulations

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)
- Epic E021: DC Plan Data Model & Events
- Epic E022: Eligibility Engine
- Epic E023: Basic Enrollment Logic

### Phase 2: Core Features (Weeks 5-8)
- Epic E024: Contribution Calculator with IRS Limits
- Epic E025: Match Engine with Formula Support
- Epic E026: Scenario Configuration Framework

### Phase 3: Analytics (Weeks 9-12)
- Epic E027: Reporting & Dashboards
- Epic E028: Scenario Comparison Engine
- Epic E029: Performance Optimization

### Phase 4: Advanced Features (Weeks 13-16)
- Epic E030: Behavioral Modeling & ML
- Epic E031: Compliance Testing (ADP/ACP)
- Epic E032: Real-time What-If Analysis

---

## 7. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| IRS regulation complexity | High | Medium | Partner with benefits counsel |
| Behavioral modeling accuracy | Medium | High | Use industry benchmarks |
| Performance at scale | Medium | Medium | Implement caching layer |
| Data quality issues | High | Medium | Validation framework |

---

## 8. Open Questions

1. **Vesting Schedules**: How complex should vesting modeling be?
2. **Loan Modeling**: Include 401(k) loan behavior in v1?
3. **Catch-up Contributions**: Model age 50+ catch-up limits?
4. **Multi-Plan Support**: Single plan initially or multiple?
5. **Historical Calibration**: How much historical data needed?

---

## 9. Appendix

### A. Glossary
- **ADP/ACP**: Actual Deferral/Contribution Percentage testing
- **QACA**: Qualified Automatic Contribution Arrangement
- **Safe Harbor**: Plan design that automatically passes testing
- **True-Up**: Year-end match reconciliation

### B. Sample Calculations
```python
# Match calculation example
employee_deferral_rate = 0.08  # 8%
employee_salary = 100000

# Tiered match: 100% on first 3%, 50% on next 2%
tier1_match = min(0.03, employee_deferral_rate) * 1.00 * employee_salary
tier2_match = max(0, min(0.02, employee_deferral_rate - 0.03)) * 0.50 * employee_salary
total_match = tier1_match + tier2_match  # $4,000
```

### C. Competitive Analysis
- **Aon PathForward**: $100K+ annual license
- **Mercer CAP**: Consultant-driven, 4-6 week turnaround
- **Internal Models**: Excel-based, error-prone, not scalable

---

## Next Steps

1. **Review & Approval**: Stakeholder sign-off on requirements
2. **Epic Creation**: Develop detailed epics E021-E032
3. **Story Breakdown**: Create implementation stories
4. **Technical Spike**: Prototype scenario engine
5. **Pilot Partner**: Identify beta test plan sponsor
