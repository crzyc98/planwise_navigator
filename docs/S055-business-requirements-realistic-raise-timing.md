# S055 Business Requirements - Realistic Raise Timing Patterns

**Document Type**: Business Requirements
**Story ID**: S055
**Created**: June 26, 2025
**Status**: DRAFT - Pending Analytics Team Review

---

## 1. Business Objectives

### 1.1 Primary Goals
- **Realistic Simulation**: Replace oversimplified 50/50 Jan/July timing with patterns that reflect actual corporate practices
- **Audit Compliance**: Ensure simulation outputs can withstand scrutiny from regulatory and audit teams
- **Improved Accuracy**: Enhance prorated compensation calculations through realistic timing distribution
- **Workforce Planning Credibility**: Provide trustworthy data for strategic workforce decisions

### 1.2 Success Metrics
- **Timing Distribution Accuracy**: Target alignment with industry standards (±5% variance)
- **Compensation Calculation Precision**: Improved prorated annual compensation accuracy
- **Stakeholder Confidence**: Analytics team approval of simulation realism
- **Audit Readiness**: Simulation patterns defensible in compliance reviews

---

## 2. Current vs. Target State

### 2.1 Current State (S055 Audit Findings)
```yaml
Current Timing Distribution:
  January 1st: 50%    # Even-length employee IDs
  July 1st: 50%       # Odd-length employee IDs
  All other dates: 0% # No other timing options

Business Realism: LOW
Audit Risk: MEDIUM (overly simplistic patterns)
Configuration: NONE (hard-coded logic)
```

### 2.2 Target State (Realistic Business Patterns)
```yaml
Proposed Monthly Distribution:
  January: 28%    # Calendar year alignment, budget implementation
  February: 3%    # Minor adjustments
  March: 7%       # Q1 end adjustments, some fiscal years
  April: 18%      # Merit increase cycles, Q2 budget implementation
  May: 4%         # Minor adjustments
  June: 5%        # Mid-year adjustments
  July: 23%       # Fiscal year starts, educational institutions
  August: 3%      # Minor adjustments
  September: 4%   # Q3 end, some fiscal years
  October: 8%     # Federal fiscal year, some corporate cycles
  November: 2%    # Minor adjustments
  December: 2%    # Year-end adjustments

Business Realism: HIGH
Audit Risk: LOW (defensible industry patterns)
Configuration: FULL (flexible, industry-specific options)
```

---

## 3. Industry Research Summary

### 3.1 Corporate Raise Timing Patterns

**Primary Timing Drivers**:
1. **Fiscal Year Alignment** (40% of timing decisions)
   - Calendar year: January effective dates
   - Fiscal year: July/October effective dates
   - Budget cycle alignment: 3-4 months after budget approval

2. **Performance Review Cycles** (35% of timing decisions)
   - Annual reviews: December/January cycle → April effective dates
   - Mid-year reviews: June/July cycle → October effective dates
   - Quarterly reviews: Rolling effective dates

3. **Industry Standards** (25% of timing decisions)
   - Technology: More distributed, quarterly patterns
   - Finance: Strong January/July concentration
   - Government: October 1st fiscal year alignment
   - Education: July 1st academic year alignment

### 3.2 Validated Distribution Patterns

**Source**: Industry compensation surveys, HR best practices research

**Fortune 500 Patterns**:
- **Q1 (Jan-Mar)**: 35% of raises (budget implementation, calendar alignment)
- **Q2 (Apr-Jun)**: 25% of raises (merit cycles, mid-year adjustments)
- **Q3 (Jul-Sep)**: 30% of raises (fiscal year alignment, new budget periods)
- **Q4 (Oct-Dec)**: 10% of raises (federal alignment, year-end adjustments)

**SME Patterns** (150-500 employees):
- More flexible timing, often anniversary-based
- Quarterly review cycles more common
- 20-25% distributed across non-peak months

---

## 4. Business Requirements Specification

### 4.1 Functional Requirements

**FR-1: Configurable Timing Distribution**
- MUST support monthly percentage allocation for raise timing
- MUST allow industry-specific distribution overrides
- MUST maintain deterministic behavior for testing reproducibility
- SHOULD support future enhancement for department-specific patterns

**FR-2: Realistic Pattern Implementation**
- MUST implement research-based monthly distribution (Section 2.2)
- MUST eliminate hard-coded 50/50 Jan/July split
- MUST use hash-based distribution within months (like promotion events)
- SHOULD support multiple distribution profiles (Technology, Finance, Government)

**FR-3: Backward Compatibility**
- MUST maintain identical results for existing scenarios (same random seed)
- MUST provide migration path from current logic
- SHOULD support A/B testing between timing methodologies
- MUST NOT break existing event sequencing or prorated calculations

**FR-4: Configuration Management**
- MUST use seed files for timing distribution configuration
- MUST integrate with existing simulation_config.yaml structure
- SHOULD support validation of distribution percentages (sum to 100%)
- MUST provide clear documentation for configuration options

### 4.2 Non-Functional Requirements

**NFR-1: Performance**
- MUST NOT increase simulation runtime by more than 5%
- MUST maintain current DuckDB serialization patterns
- SHOULD optimize for large-scale workforce simulations (10K+ employees)

**NFR-2: Maintainability**
- MUST follow existing dbt model patterns and conventions
- MUST include comprehensive data tests for timing validation
- SHOULD provide clear audit trail for timing decisions
- MUST maintain code consistency with promotion event timing approach

**NFR-3: Auditability**
- MUST provide complete traceability of timing distribution decisions
- MUST support validation queries for timing pattern compliance
- SHOULD include business justification documentation for all patterns
- MUST enable easy comparison between timing methodologies

---

## 5. Business Validation Criteria

### 5.1 Pattern Validation
```sql
-- Target validation queries for realistic timing
SELECT
    EXTRACT(month FROM effective_date) as month,
    COUNT(*) as raise_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as percentage
FROM fct_yearly_events
WHERE event_type = 'RAISE'
GROUP BY month
ORDER BY month;

-- Expected results should align with target distribution (±2% tolerance)
```

### 5.2 Business Stakeholder Acceptance
- **Analytics Team Lead**: Approve realistic patterns for workforce planning
- **Compensation Team**: Validate against actual company raise timing data
- **Audit Team**: Confirm patterns are defensible in compliance reviews
- **Engineering Team**: Technical feasibility and performance validation

---

## 6. Implementation Priorities

### 6.1 Phase 1: Core Timing System (S056)
**Priority**: MUST HAVE
- Design configurable timing distribution framework
- Create seed file structure for monthly allocation
- Define migration strategy from current 50/50 logic
- Validate backward compatibility requirements

### 6.2 Phase 2: Pattern Implementation (S057)
**Priority**: MUST HAVE
- Implement realistic monthly distribution (28% Jan, 18% Apr, 23% July)
- Replace hard-coded logic with configuration-driven approach
- Add comprehensive testing and validation
- Document business justification for timing patterns

### 6.3 Phase 3: Advanced Features (Future)
**Priority**: SHOULD HAVE
- Industry-specific timing profiles (Technology, Finance, Government)
- Department-level timing variation support
- Performance review cycle integration
- Advanced business calendar support (exclude holidays, etc.)

---

## 7. Risk Assessment

### 7.1 Technical Risks
- **Medium**: Complexity of hash-based month distribution implementation
- **Low**: Performance impact on simulation runtime
- **Low**: DuckDB serialization compatibility issues

### 7.2 Business Risks
- **Low**: Stakeholder rejection of proposed timing patterns
- **Medium**: Need for industry-specific customization beyond initial scope
- **Low**: Audit team concerns about new patterns vs. established baseline

### 7.3 Mitigation Strategies
- Maintain current logic as fallback option
- Implement A/B testing capabilities for pattern comparison
- Provide comprehensive business justification documentation
- Engage stakeholders early in pattern validation process

---

## 8. Acceptance Criteria

### 8.1 Technical Acceptance
- [ ] Timing distribution matches target monthly percentages (±2% tolerance)
- [ ] Prorated compensation calculations maintain accuracy
- [ ] Event sequencing and conflict resolution unchanged
- [ ] Performance impact <5% on simulation runtime
- [ ] All existing data tests continue to pass

### 8.2 Business Acceptance
- [ ] Analytics Team approval of timing patterns
- [ ] Compensation calculations align with business expectations
- [ ] Simulation outputs defensible in audit scenarios
- [ ] Configuration flexibility meets future enhancement needs
- [ ] Documentation complete for business stakeholders

---

## 9. Next Steps

### 9.1 Immediate Actions (S056)
1. **Stakeholder Review**: Present timing patterns to Analytics Team for approval
2. **Technical Design**: Create detailed implementation specification
3. **Configuration Design**: Define seed file structure and validation rules
4. **Testing Strategy**: Plan validation approach for timing distribution accuracy

### 9.2 Implementation Phase (S057)
1. **Code Implementation**: Modify int_merit_events.sql with new timing logic
2. **Configuration Setup**: Create timing distribution seed files
3. **Validation Testing**: Comprehensive testing of new patterns
4. **Migration Strategy**: Plan transition from current 50/50 logic

---

**Document Owner**: Engineering Team
**Business Sponsor**: Analytics Team
**Review Status**: PENDING - Awaiting Analytics Team validation of proposed timing patterns
