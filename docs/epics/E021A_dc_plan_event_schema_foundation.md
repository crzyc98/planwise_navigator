# Epic E021-A: DC Plan Event Schema Foundation

**Parent Epic**: E021 - DC Plan Data Model & Events
**Epic Points**: 32
**Priority**: High
**Duration**: 3 Sprints

## Epic Story

**As a** platform architect
**I want** a comprehensive, enterprise-grade event-sourced architecture for DC plan operations
**So that** we can track every participant interaction with complete audit trail, regulatory compliance, and high-performance data processing

## Business Context

This epic establishes the foundational event schema for Defined Contribution retirement plan modeling within PlanWise Navigator's event-sourced architecture. It creates a unified, enterprise-grade event system that supports comprehensive retirement plan transactions while maintaining backward compatibility with workforce events and meeting ERISA compliance requirements.

The epic transforms workforce simulation from a simple employee lifecycle system into a comprehensive retirement plan administration platform capable of handling complex regulatory scenarios, compliance testing, and participant lifecycle management.

## Epic Acceptance Criteria

### Technical Foundation
- [ ] **Unified event architecture** using Pydantic v2 discriminated unions for all 18 event types
- [ ] **Complete payload coverage** for workforce integration, core DC plan operations, loans, investments, and compliance
- [ ] **Performance targets met**: ≥100K events/sec ingest, ≤5s history reconstruction
- [ ] **Enterprise validation framework** with comprehensive testing and golden dataset validation

### Regulatory Compliance
- [ ] **ERISA SME approval** with signed compliance checklist
- [ ] **IRS regulation coverage** including 402(g), 415(c), ADP/ACP, HCE determination
- [ ] **Complete audit trail** with immutable event logging and correlation tracking
- [ ] **Data classification** implemented (SSN=RESTRICTED, compensation=CONFIDENTIAL)

### Integration & Performance
- [ ] **Backward compatibility** maintained with existing workforce events
- [ ] **Snapshot strategy** implemented for query optimization
- [ ] **CI validation** achieving ≥99% JSON schema validation success rate
- [ ] **Documentation complete** with payload reference and downstream process mapping

## Story Breakdown

| Story | Title | Points | Owner | Sprint | Dependencies |
|-------|-------|--------|-------|---------|--------------|
| **S072-01** | Core Event Model & Pydantic v2 Architecture | 5 | Platform | 1 | None |
| **S072-02** | Workforce Event Integration | 3 | Platform | 1 | S072-01 |
| **S072-03** | Core DC Plan Events | 5 | DC Plan | 2 | S072-01 |
| **S072-04** | Plan Administration Events | 5 | DC Plan | 2 | S072-01 |
| **S072-05** | Loan & Investment Events | 3 | DC Plan | 2 | S072-01 |
| **S072-06** | Performance & Validation Framework | 8 | Platform | 3 | S072-01,02,03,04,05 |
| **S072-07** | ERISA Compliance Review & Documentation | 3 | Compliance | 3 | S072-06 |

## Technical Architecture

### Core Design Principles
1. **Single Event Model**: Unified `SimulationEvent` with discriminated union payloads
2. **Required Context**: `scenario_id` and `plan_design_id` mandatory for isolation
3. **Type Safety**: Full Pydantic v2 validation with no untyped dictionaries
4. **Decimal Precision**: `Decimal(18,6)` for all monetary amounts
5. **Immutable Audit**: Complete event trail with UUID and timestamp

### Event Categories
- **Workforce Events (4)**: hire, promotion, termination, merit
- **Core DC Events (5)**: eligibility, enrollment, contribution, distribution, vesting
- **Administrative Events (4)**: forfeiture, loan_initiated, loan_repayment, rollover
- **Compliance Events (5)**: investment_election, hce_status, compliance, plan_compliance_test, loan_default, rmd_determination

## Success Metrics

### Functional Requirements
- [ ] **Event completeness**: All 18 DC plan event types implemented
- [ ] **Type safety**: Zero runtime type errors with Pydantic v2
- [ ] **Scenario isolation**: Zero data leakage between scenarios
- [ ] **Golden dataset validation**: 100% match with benchmark calculations

### Performance Requirements
- [ ] **Event ingest**: ≥100K events/sec (16-core M2, 32GB)
- [ ] **History reconstruction**: ≤5s for 5-year window (MacBook Pro M3, 16GB)
- [ ] **Schema validation**: <10ms per event validation
- [ ] **Memory efficiency**: <8GB for 100K employee simulation

### Compliance Requirements
- [ ] **JSON schema validation**: ≥99% success rate in CI
- [ ] **ERISA compliance**: Signed SME checklist
- [ ] **IRS regulation coverage**: Unit tests for all major compliance scenarios
- [ ] **Data classification**: All PII fields properly classified

## Risk Mitigation

### Technical Risks
- **Pydantic v2 complexity**: Mitigated by foundational story S072-01 with comprehensive testing
- **Performance impact**: Mitigated by dedicated performance story S072-06
- **Integration complexity**: Mitigated by separate workforce integration story S072-02

### Business Risks
- **Regulatory compliance gaps**: Mitigated by dedicated compliance story S072-07
- **Incomplete event coverage**: Mitigated by systematic payload development in S072-03,04,05

## Definition of Done

- [ ] **All 7 stories completed** with individual acceptance criteria met
- [ ] **Integration testing passed** across all event types
- [ ] **Performance benchmarks verified** on specified hardware
- [ ] **ERISA SME sign-off** with compliance documentation
- [ ] **Documentation complete** with payload reference and implementation guide
- [ ] **CI pipeline validated** with ≥99% schema validation success
- [ ] **Golden dataset validation** with zero variance tolerance

## Related Epics

- **E021**: DC Plan Data Model & Events (parent)
- **E022**: Eligibility Engine (consumes event schema)
- **E023**: Enrollment Engine (consumes event schema)
- **E024**: Contribution Calculator (consumes event schema)
- **E025**: Match Engine (consumes event schema)
