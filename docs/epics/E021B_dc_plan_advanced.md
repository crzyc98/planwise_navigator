# Epic E021-B: Advanced DC Plan Features

## Epic Overview

### Summary
Advanced Defined Contribution retirement plan features building upon the E021 MVP foundation. This epic includes enterprise-grade compliance, security, and performance optimizations for large-scale DC plan modeling.

### Prerequisites
- **Epic E021 (DC Plan MVP)** must be completed first
- **Epic E020 (Polars Integration)** recommended for performance optimization
- **Epic E022 (Eligibility Engine)** for advanced eligibility rules

### Business Value
- Enterprise-grade ERISA compliance and audit capabilities
- Advanced plan administration and participant services
- High-performance processing for large employee populations
- Comprehensive data security and PII protection

---

## User Stories

### Story S073-01: ERISA Compliance Review & Documentation (8 points)
**As a** compliance officer
**I want** comprehensive ERISA compliance validation and documentation
**So that** our DC plan modeling meets all regulatory requirements

**Acceptance Criteria:**
- Complete ERISA fiduciary responsibility documentation
- DOL audit trail requirements implementation
- Form 5500 data validation and reporting
- Plan document compliance checking
- Legal review and certification process

### Story S073-02: True-Up Calculation Engine (13 points)
**As a** plan administrator
**I want** automated employer match true-up calculations
**So that** participants receive correct matching contributions

**Acceptance Criteria:**
- Support for complex matching formulas (tiered, stretch, safe harbor)
- Year-end true-up calculations with $5 threshold
- Integration with payroll systems for mid-year corrections
- Golden dataset validation with zero variance tolerance
- Audit trail for all true-up calculations

**Complex Matching Formulas:**
```python
class MatchingFormula(BaseModel):
    formula_type: Literal["tiered", "stretch", "safe_harbor", "discretionary"]
    tiers: List[MatchingTier]
    annual_true_up: bool = True
    true_up_threshold: Decimal = Decimal("5.00")

class MatchingTier(BaseModel):
    employee_min: float = Field(..., ge=0, le=1)
    employee_max: float = Field(..., ge=0, le=1)
    match_rate: float = Field(..., ge=0, le=2)

# Example: "100% on first 3%, 50% on next 2%"
tiered_formula = MatchingFormula(
    formula_type="tiered",
    tiers=[
        MatchingTier(employee_min=0.00, employee_max=0.03, match_rate=1.00),
        MatchingTier(employee_min=0.03, employee_max=0.05, match_rate=0.50)
    ]
)
```

### Story S073-03: Loan & Investment Events (5 points)
**As a** participant services specialist
**I want** event types for loans and investment elections
**So that** we can track participant-directed transactions

**Acceptance Criteria:**
- Loan origination, payment, and default events
- Investment election changes and rebalancing
- Hardship withdrawal processing
- In-service distribution events
- Integration with external recordkeeper systems

### Story S073-04: Advanced Plan Administration Events (8 points)
**As a** plan administrator
**I want** comprehensive administrative event types
**So that** we can model all plan operations and compliance requirements

**Acceptance Criteria:**
- Forfeiture processing and reallocation events
- Distribution events (lump sum, installment, rollover)
- Beneficiary designation and processing
- Plan amendment and restatement events
- Correction events for operational failures

### Story S073-05: Regulatory Limits Service (10 points)
**As a** system architect
**I want** version-controlled regulatory limits with automated updates
**So that** all compliance calculations use current IRS limits

**Acceptance Criteria:**
- Automated IRS limit ingestion from official sources
- Version control with effective date tracking
- Mid-year limit change support (rare but required)
- API for limit lookup by plan year and date
- Integration with external tax services

**Limits Service Architecture:**
```python
class RegulatoryLimitsService:
    def get_limits(self, plan_year: int, effective_date: date = None) -> IRSLimits
    def get_limits_range(self, start_year: int, end_year: int) -> List[IRSLimits]
    def validate_contribution(self, contribution: ContributionPayload) -> ComplianceResult
    def check_for_updates(self) -> List[LimitUpdate]
    def apply_limit_updates(self, updates: List[LimitUpdate]) -> UpdateResult
```

### Story S073-06: Data Protection & PII Security Framework (12 points)
**As a** security officer
**I want** comprehensive protection for participant PII and sensitive data
**So that** we comply with data privacy regulations and internal policies

**Acceptance Criteria:**
- Field-level encryption for PII (SSN, birth date, compensation)
- Role-based access control with audit logging
- Data masking and anonymization for non-production
- Automated PII discovery and classification
- GDPR/CCPA compliance for right to be forgotten

**Security Implementation:**
```python
class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"  # PII requiring encryption

class SecurityManager:
    def encrypt_field(self, field_name: str, value: str) -> str
    def decrypt_field(self, field_name: str, encrypted_value: str) -> str
    def mask_data(self, data: Dict, user_role: str) -> Dict
    def audit_access(self, user: str, table: str, operation: str) -> None
```

### Story S073-07: Scenario Isolation Architecture (8 points)
**As a** benefits analyst
**I want** to run multiple plan design scenarios simultaneously
**So that** I can compare different plan configurations

**Acceptance Criteria:**
- Complete data isolation between scenarios using composite keys
- Support for 10+ plan design variations per scenario
- Efficient storage and querying of scenario data
- Scenario comparison and reporting tools
- Migration tools for promoting scenarios to production

### Story S073-08: Advanced Compliance Enforcement Engine (15 points)
**As a** compliance officer
**I want** automated enforcement of all IRS regulations
**So that** all contributions comply with regulations and avoid penalties

**Acceptance Criteria:**
- Real-time Section 402(g) and 415(c) limit enforcement
- ADP/ACP testing with automatic correction
- Top-heavy testing and minimum contribution calculations
- HCE determination with lookback period support
- Automatic corrective action processing

**Advanced Compliance Features:**
```python
class ComplianceEngine:
    def validate_adp_acp(self, plan_year: int) -> ADPACPResult
    def perform_top_heavy_test(self, plan_year: int) -> TopHeavyResult
    def calculate_minimum_contributions(self, plan_year: int) -> List[MinimumContribution]
    def process_corrective_distributions(self, violations: List[ComplianceViolation]) -> CorrectionResult
    def generate_compliance_reports(self, plan_year: int) -> ComplianceReport
```

### Story S073-09: Performance Optimization with Polars (10 points)
**As a** system architect
**I want** high-performance processing using Polars
**So that** we can handle 100K+ employees efficiently

**Acceptance Criteria:**
- Polars integration for vectorized operations
- Parallel processing for event generation
- Memory-efficient data structures
- Performance benchmarks: <10 minutes for 100K employees
- Backward compatibility with existing pandas code

### Story S073-10: Advanced Reporting & Analytics (8 points)
**As a** benefits analyst
**I want** comprehensive reporting and analytics capabilities
**So that** I can analyze plan performance and participant behavior

**Acceptance Criteria:**
- Executive dashboards with plan metrics
- Participant behavior analytics
- Cost analysis and projection reports
- Benchmarking against industry standards
- Export capabilities for external systems

---

## Technical Architecture

### Advanced Event Schema
```python
# Extended event types for advanced features
class AdvancedDCPlanEvent(SimulationEvent):
    event_type: Literal[
        # Basic events (from E021 MVP)
        "eligibility", "enrollment", "contribution", "vesting",
        # Advanced events (E021-B)
        "loan_origination", "loan_payment", "loan_default",
        "distribution", "hardship_withdrawal", "in_service_distribution",
        "forfeiture", "forfeiture_allocation", "investment_election",
        "beneficiary_designation", "plan_amendment", "correction"
    ]

class LoanOriginationPayload(BaseModel):
    loan_id: str
    loan_amount: Decimal
    loan_reason: Literal["general", "hardship", "primary_residence"]
    interest_rate: Decimal
    term_months: int
    payment_amount: Decimal

class DistributionPayload(BaseModel):
    distribution_id: str
    distribution_type: Literal["lump_sum", "installment", "rollover", "rmd"]
    gross_amount: Decimal
    taxable_amount: Decimal
    withholding_amount: Decimal
    distribution_reason: str
```

### Performance Architecture
```python
# Polars-based high-performance processing
import polars as pl

class HighPerformanceEventProcessor:
    def process_contributions_vectorized(self, df: pl.DataFrame) -> pl.DataFrame:
        """Process contributions using vectorized operations"""
        return df.with_columns([
            pl.when(pl.col("source") == "employee_pre_tax")
            .then(pl.col("amount"))
            .otherwise(0)
            .alias("pre_tax_amount"),

            pl.when(pl.col("source") == "employer_match")
            .then(pl.col("amount"))
            .otherwise(0)
            .alias("match_amount")
        ]).group_by(["employee_id", "plan_year"]).agg([
            pl.sum("pre_tax_amount").alias("total_pre_tax"),
            pl.sum("match_amount").alias("total_match")
        ])
```

### Security Architecture
```python
# Field-level encryption with key management
class FieldLevelEncryption:
    def __init__(self, key_management_service: KeyManagementService):
        self.kms = key_management_service

    def encrypt_pii_fields(self, record: Dict) -> Dict:
        """Encrypt PII fields using field-specific keys"""
        encrypted_record = record.copy()

        for field_name, value in record.items():
            if self.is_pii_field(field_name):
                key = self.kms.get_field_key(field_name)
                encrypted_record[field_name] = self.encrypt_value(value, key)

        return encrypted_record
```

---

## Performance Requirements (Enterprise)

| Metric | Enterprise Requirement | Implementation Strategy |
|--------|------------------------|------------------------|
| Employee Capacity | 100,000+ employees | Polars vectorized processing |
| Event Processing | <50ms per 1M events | Parallel processing, optimized algorithms |
| Multi-Year Simulation | 2025-2034 in <60 minutes | Incremental processing, caching |
| Concurrent Scenarios | 10+ scenarios simultaneously | Efficient data partitioning |
| Memory Usage | <16GB for 100K employees | Memory-mapped files, streaming |
| Data Encryption | <10% performance impact | Hardware-accelerated encryption |

---

## Security & Compliance

### Data Classification Framework
```yaml
data_classification:
  restricted:  # PII requiring encryption
    fields: [ssn, birth_date, bank_account]
    encryption: AES-256-GCM
    key_rotation: 90_days

  confidential:  # Sensitive business data
    fields: [compensation, contribution_amounts]
    encryption: AES-256-GCM
    access_control: role_based

  internal:  # Internal use only
    fields: [employee_id, job_level, department]
    masking: hash_based

  public:  # Non-sensitive
    fields: [plan_id, event_type]
    protection: none
```

### Access Control Matrix
| Role | Restricted Data | Confidential Data | Internal Data | Public Data |
|------|----------------|-------------------|---------------|-------------|
| Admin | Full Access | Full Access | Full Access | Full Access |
| Compliance Officer | Masked | Full Access | Full Access | Full Access |
| Benefits Analyst | Blocked | Aggregated Only | Full Access | Full Access |
| Developer | Blocked | Blocked | Masked | Full Access |
| Service Account | Encrypted Only | Encrypted Only | Hash Only | Full Access |

---

## Integration Points

### External Systems
- **Payroll Systems**: Real-time contribution data feeds
- **Recordkeepers**: Account balance reconciliation
- **Tax Services**: Automated IRS limit updates
- **Compliance Vendors**: ADP/ACP testing validation
- **Audit Firms**: Data extract and reporting

### Internal Systems
- **E021 MVP**: Builds upon basic DC plan foundation
- **E020 Polars**: Uses high-performance data processing
- **E022 Eligibility Engine**: Advanced eligibility determination
- **Workforce Simulation**: Enhanced workforce event integration

---

## Risks & Mitigations

### Technical Risks
- **Risk**: Performance degradation with advanced features
- **Mitigation**: Comprehensive benchmarking, Polars optimization

- **Risk**: Security implementation complexity
- **Mitigation**: Phased rollout, security audit, pen testing

### Compliance Risks
- **Risk**: ERISA compliance gaps
- **Mitigation**: Legal review, industry expert consultation

- **Risk**: Data privacy violations
- **Mitigation**: Privacy impact assessment, automated compliance monitoring

---

## Implementation Timeline

### Phase 1: Core Advanced Features (Sprints 1-3)
- Story S073-02: True-Up Calculation Engine
- Story S073-04: Advanced Plan Administration Events
- Story S073-08: Advanced Compliance Enforcement Engine

### Phase 2: Security & Performance (Sprints 4-6)
- Story S073-06: Data Protection & PII Security Framework
- Story S073-09: Performance Optimization with Polars
- Story S073-07: Scenario Isolation Architecture

### Phase 3: Enterprise Features (Sprints 7-9)
- Story S073-01: ERISA Compliance Review & Documentation
- Story S073-05: Regulatory Limits Service
- Story S073-10: Advanced Reporting & Analytics
- Story S073-03: Loan & Investment Events

---

## Definition of Done

- [ ] **All Stories**: 10 stories completed with acceptance criteria met
- [ ] **Performance**: Enterprise performance requirements achieved
- [ ] **Security**: PII protection and access control implemented
- [ ] **Compliance**: ERISA requirements validated by legal review
- [ ] **Integration**: Seamless integration with E021 MVP
- [ ] **Testing**: Comprehensive test suite with 95%+ coverage
- [ ] **Documentation**: Complete implementation and user guides
- [ ] **Audit**: Security and compliance audit completed

**Total Story Points**: 107 points
**Estimated Duration**: 9-12 sprints

---

## Success Metrics

### Functional Metrics
- Support for 100,000+ employees
- <1% compliance violation rate
- 99.9% data accuracy for true-up calculations
- Zero PII data breaches or exposures

### Performance Metrics
- <60 minutes for full multi-year simulation (100K employees)
- <10% performance impact from security features
- <5 seconds for real-time compliance validation
- <1GB memory usage per 10K employees

### Business Metrics
- 50% reduction in manual compliance work
- 90% improvement in audit preparation time
- 100% automated regulatory limit updates
- Zero operational compliance failures

This epic transforms the E021 MVP into an enterprise-grade DC plan modeling platform capable of handling large-scale, complex retirement plan operations while maintaining the highest standards of security, compliance, and performance.
