# Epic E026: Advanced Eligibility Features

## Epic Overview

### Summary
Build advanced eligibility determination features including employee classification rules, entry date processing, age/hours requirements, and complex service calculations. This epic contains all the sophisticated eligibility features that were deferred from the E022 MVP.

### Business Value
- Supports complex plan designs with multiple eligibility rules
- Handles edge cases and regulatory requirements
- Provides complete audit trail for all eligibility determinations
- Enables sophisticated plan modeling and analysis

### Success Criteria
- ✅ Supports all common eligibility rule patterns
- ✅ Handles employee classification exclusions
- ✅ Processes entry dates (immediate, monthly, quarterly)
- ✅ Manages age and hours-based requirements
- ✅ Achieves <100ms response time for point-in-time eligibility queries
- ✅ Supports incremental processing with 95% cache hit rate

### Dependencies
- **Epic E022**: Simple Eligibility Engine (must be completed first)
- Employee demographic data from workforce simulation
- Employment history including hire/term/rehire dates

---

## User Stories

### Story S022-02: Basic Employee Classification (5 points) 📅
**Status**: Post-MVP from Epic E022
**As a** plan sponsor
**I want** simple employee type exclusions
**So that** I can exclude interns and contractors from the plan

**Acceptance Criteria:**
- Exclude employees by employee_type field (intern, contractor, seasonal)
- Use SQL boolean logic for maximum performance
- Configuration via dbt variables
- Specific exclusion reason tracking (excluded:intern, excluded:contractor)
- Data quality checks for missing/invalid employee types
- Process exclusions in single pass with other eligibility checks
- Generate exclusion events for comprehensive audit trail

**Implementation**: See `/docs/stories/S022-02-basic-employee-classification.md`

### Story S022-03: Entry Date Processing (4 points) 📅
**Status**: Post-MVP from Epic E022
**As a** payroll administrator
**I want** automatic entry date calculations
**So that** eligible employees start on the correct date

**Acceptance Criteria:**
- Calculate immediate entry (same day as eligibility)
- Calculate quarterly entry dates (1/1, 4/1, 7/1, 10/1)
- Calculate monthly entry dates (1st of each month)
- SQL-based implementation for maximum performance
- Configuration via dbt variables
- Handle year boundaries correctly
- Generate entry date events for newly eligible employees

**Implementation**: See `/docs/stories/S022-03-entry-date-processing.md`

### Future Stories (To Be Defined)

#### Story S026-01: Age-Based Eligibility Requirements (6 points) 📅
**As a** compliance officer
**I want** age-based eligibility rules
**So that** we meet plan document requirements

**Future Acceptance Criteria:**
- Support minimum age requirements (18, 21, etc.)
- Vectorized age calculations
- Integration with existing eligibility logic

#### Story S026-02: Hours-Based Eligibility (8 points) 📅
**As a** benefits administrator
**I want** hours-based eligibility tracking
**So that** part-time employees are properly evaluated

**Future Acceptance Criteria:**
- 1000-hour annual requirements
- YTD hours tracking
- Integration with payroll systems

#### Story S026-03: Complex Service Computation (12 points) 📅
**As a** compliance officer
**I want** complex service calculations with breaks and rehires
**So that** we meet ERISA requirements for all edge cases

**Future Acceptance Criteria:**
- Hours counting method with 1000-hour threshold and YTD tracking
- Handles breaks in service and rehires with complex rehire credit logic
- Supports "Rule of Parity" for vesting
- Multiple concurrent service calculations (eligibility vs vesting)

#### Story S026-04: Advanced Classification Rules (8 points) 📅
**As a** plan sponsor
**I want** complex classification rules by multiple attributes
**So that** I have full control over plan participation

**Future Acceptance Criteria:**
- Inclusion/exclusion by location, division, union status
- Statutory exclusions (non-resident aliens)
- Pre-computed classification segments for performance
- Dynamic rule application with effective dating

#### Story S026-05: Eligibility Change Tracking (8 points) 📅
**As an** audit manager
**I want** complete tracking of eligibility changes
**So that** I can explain any eligibility determination

**Future Acceptance Criteria:**
- Point-in-time eligibility queries with <100ms response
- Eligibility loss scenarios (termination, reclassification)
- Automated compliance reporting
- Event correlation with workforce changes

---

## Technical Specifications

### Advanced Configuration Schema
```yaml
# config/advanced_eligibility_rules.yaml
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

---

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Daily Processing | <30 seconds for 100K employees | Vectorized DataFrame operations with Pandas/Polars |
| Point-in-Time Queries | <100ms response time | Optimized eligibility snapshots with indexed lookups |
| Cache Hit Rate | 95% for unchanged employees | Service computation caching with employment history tracking |
| Memory Usage | <4GB for 100K employee dataset | Efficient data types and incremental processing |
| Concurrent Scenarios | <2 minutes for 10 parallel scenarios | Process-based parallelism with isolated DataFrames |

---

## Estimated Effort

### Current Stories (From E022)
**Total Story Points**: 9 points (S022-02: 5, S022-03: 4)
**Estimated Duration**: 1 week

### Future Stories
**Total Story Points**: 42 points (S026-01: 6, S026-02: 8, S026-03: 12, S026-04: 8, S026-05: 8)
**Estimated Duration**: 4-5 sprints

### Total Epic
**Total Story Points**: 51 points
**Estimated Duration**: 5-6 weeks total

---

## Definition of Done

### Phase 1 (Moved from E022)
- [ ] Employee classification exclusions working
- [ ] Entry date processing for immediate, monthly, and quarterly patterns
- [ ] Integration with Epic E022 eligibility engine
- [ ] 95% test coverage for classification and entry date features

### Phase 2 (Future)
- [ ] All advanced eligibility rules implemented and tested
- [ ] Performance benchmarks met (<5 min for 100K employees)
- [ ] Comprehensive test coverage including edge cases
- [ ] Integration with event stream complete
- [ ] Configuration documentation with examples
- [ ] Compliance review completed

---

## Relationship to Epic E022

This epic builds upon the simple days-based eligibility engine from Epic E022. The E022 MVP provides the foundation with:
- Basic eligibility determination based on waiting period
- ELIGIBILITY event generation
- Simple configuration via `eligibility_waiting_days`

Epic E026 adds the sophisticated features that most enterprise plans require:
- Employee classification and exclusions
- Entry date processing and scheduling
- Age and hours-based requirements
- Complex service calculations and break handling
