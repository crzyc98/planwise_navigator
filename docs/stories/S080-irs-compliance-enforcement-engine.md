# Story S080: IRS Compliance Enforcement Engine

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 13
**Priority**: High

## Story

**As a** compliance officer
**I want** automated enforcement of Section 415(c) and 402(g) limits
**So that** all contributions comply with IRS regulations and avoid penalties

## Business Context

This story implements a comprehensive IRS compliance enforcement engine that automatically validates all retirement plan contributions against federal regulations. The engine prevents violations before they occur, generates corrective action events, and maintains complete audit trails for regulatory compliance.

## Acceptance Criteria

### Section 415(c) Annual Additions Limit Enforcement
- [ ] **Real-time tracking** of aggregate contributions (EE + ER + after-tax)
- [ ] **Include all sources**: deferrals, match, profit sharing, true-ups, forfeitures
- [ ] **Hard-stop constraint** preventing contributions exceeding annual limit
- [ ] **Automatic allocation adjustments** when approaching limits

### Section 402(g) Elective Deferral Limit Enforcement
- [ ] **Track combined pre-tax + Roth deferrals** against annual limit
- [ ] **Separate validation** for catch-up contributions (age 50+)
- [ ] **Mid-year catch-up eligibility** detection
- [ ] **Prevent excess deferrals** through payroll integration

### Compliance Event Generation
- [ ] **EVT_EXCESS_DEFERRAL_CORRECTION** for 402(g) violations
- [ ] **EVT_ANNUAL_ADDITIONS_EXCEEDED** for 415(c) violations
- [ ] **EVT_CATCH_UP_ELIGIBLE** when participant reaches age 50
- [ ] **EVT_CONTRIBUTION_CAPPED** when limits enforced

### Corrective Actions
- [ ] **Automatic refund calculations** for excess deferrals
- [ ] **Reallocation logic** for employer contributions
- [ ] **Compliance correction audit trail**

### Year-Specific Limit Integration
- [ ] **Dynamic limit retrieval** from irs_limits table by plan year
- [ ] **Support for mid-year limit changes** (rare but possible)

## Technical Specifications

### Compliance Models
```python
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import uuid

class ComplianceViolationType(str, Enum):
    EXCESS_DEFERRAL_402G = "402g_excess_deferral"
    ANNUAL_ADDITIONS_415C = "415c_annual_additions"
    CATCH_UP_INELIGIBLE = "catch_up_ineligible"
    COMPENSATION_LIMIT = "compensation_limit_exceeded"

class CorrectionMethod(str, Enum):
    REFUND_EMPLOYEE = "refund_employee"
    REDUCE_EMPLOYER = "reduce_employer_contribution"
    REALLOCATE_SOURCES = "reallocate_contribution_sources"
    CAP_CONTRIBUTION = "cap_at_limit"
    NO_ACTION = "no_action_required"

class ContributionSource(str, Enum):
    EMPLOYEE_PRE_TAX = "employee_pre_tax"
    EMPLOYEE_ROTH = "employee_roth"
    EMPLOYEE_AFTER_TAX = "employee_after_tax"
    EMPLOYEE_CATCH_UP = "employee_catch_up"
    EMPLOYER_MATCH = "employer_match"
    EMPLOYER_MATCH_TRUE_UP = "employer_match_true_up"
    EMPLOYER_NONELECTIVE = "employer_nonelective"
    EMPLOYER_PROFIT_SHARING = "employer_profit_sharing"
    FORFEITURE_ALLOCATION = "forfeiture_allocation"

class ContributionValidationInput(BaseModel):
    employee_id: str
    plan_id: str
    plan_year: int
    contribution_source: ContributionSource
    contribution_amount: Decimal
    effective_date: date

    # Employee context
    birth_date: date
    hire_date: date
    current_compensation: Decimal
    ytd_compensation: Decimal

    # Current year contributions (all sources)
    ytd_contributions: Dict[ContributionSource, Decimal] = Field(default_factory=dict)

    # Payroll context
    pay_period_start: date
    pay_period_end: date
    payroll_frequency: str = "bi_weekly"  # weekly, bi_weekly, semi_monthly, monthly

class ComplianceValidationResult(BaseModel):
    employee_id: str
    plan_id: str
    plan_year: int
    validation_timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Validation outcome
    is_compliant: bool
    allowed_amount: Decimal
    excess_amount: Decimal = Decimal('0')

    # Limit information
    applicable_limits: Dict[str, Decimal]
    limit_utilization: Dict[str, float]  # Percentage of limits used

    # Violations found
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    # Corrective actions
    recommended_correction: Optional[CorrectionMethod] = None
    correction_details: Dict[str, Any] = Field(default_factory=dict)

    # Context
    catch_up_eligible: bool = False
    remaining_capacity: Dict[str, Decimal] = Field(default_factory=dict)

class ComplianceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    plan_id: str
    event_type: str  # Maps to compliance event types
    effective_date: date
    plan_year: int

    # Compliance details
    violation_type: ComplianceViolationType
    limit_type: str
    applicable_limit: Decimal
    current_amount: Decimal
    excess_amount: Decimal

    # Correction information
    correction_method: CorrectionMethod
    correction_amount: Decimal
    affected_sources: List[ContributionSource]
    correction_deadline: Optional[date] = None

    # Audit trail
    detection_method: str = "real_time_validation"
    payroll_system_notified: bool = False
    participant_notified: bool = False

    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_system: str = "compliance_engine"
```

### IRS Compliance Engine
```python
class IRSComplianceEngine:
    """Comprehensive IRS compliance enforcement engine"""

    def __init__(self, irs_limits_service, contribution_service, event_publisher):
        self.irs_limits_service = irs_limits_service
        self.contribution_service = contribution_service
        self.event_publisher = event_publisher

    def validate_contribution(
        self,
        validation_input: ContributionValidationInput
    ) -> ComplianceValidationResult:
        """Validate contribution against all applicable IRS limits"""

        # Get applicable IRS limits
        irs_limits = self.irs_limits_service.get_limits(validation_input.plan_year)

        # Initialize result
        result = ComplianceValidationResult(
            employee_id=validation_input.employee_id,
            plan_id=validation_input.plan_id,
            plan_year=validation_input.plan_year,
            is_compliant=True,
            allowed_amount=validation_input.contribution_amount,
            applicable_limits=self._build_applicable_limits(irs_limits, validation_input)
        )

        # Check catch-up eligibility
        result.catch_up_eligible = self._is_catch_up_eligible(
            validation_input.birth_date,
            validation_input.plan_year
        )

        # Validate against 402(g) limits
        if validation_input.contribution_source in [
            ContributionSource.EMPLOYEE_PRE_TAX,
            ContributionSource.EMPLOYEE_ROTH,
            ContributionSource.EMPLOYEE_CATCH_UP
        ]:
            self._validate_402g_limits(validation_input, result, irs_limits)

        # Validate against 415(c) limits
        self._validate_415c_limits(validation_input, result, irs_limits)

        # Validate against compensation limits
        self._validate_compensation_limits(validation_input, result, irs_limits)

        # Generate corrective actions if needed
        if not result.is_compliant:
            self._generate_corrective_actions(validation_input, result)

        return result

    def _validate_402g_limits(
        self,
        input_data: ContributionValidationInput,
        result: ComplianceValidationResult,
        irs_limits: Any
    ) -> None:
        """Validate Section 402(g) elective deferral limits"""

        # Calculate current deferrals (excluding catch-up)
        current_deferrals = (
            input_data.ytd_contributions.get(ContributionSource.EMPLOYEE_PRE_TAX, Decimal('0')) +
            input_data.ytd_contributions.get(ContributionSource.EMPLOYEE_ROTH, Decimal('0'))
        )

        # Calculate catch-up contributions
        catch_up_contributions = input_data.ytd_contributions.get(
            ContributionSource.EMPLOYEE_CATCH_UP, Decimal('0')
        )

        # Determine applicable limit
        base_limit = Decimal(str(irs_limits.employee_deferral_limit))
        catch_up_limit = Decimal(str(irs_limits.catch_up_contribution_limit)) if result.catch_up_eligible else Decimal('0')

        # Check if this is a catch-up contribution
        if input_data.contribution_source == ContributionSource.EMPLOYEE_CATCH_UP:
            if not result.catch_up_eligible:
                # Not eligible for catch-up
                result.is_compliant = False
                result.allowed_amount = Decimal('0')
                result.excess_amount = input_data.contribution_amount
                result.violations.append({
                    'violation_type': ComplianceViolationType.CATCH_UP_INELIGIBLE,
                    'message': 'Employee not eligible for catch-up contributions',
                    'regulatory_citation': 'IRC Section 414(v)'
                })
                return

            # Validate catch-up limit
            projected_catch_up = catch_up_contributions + input_data.contribution_amount
            if projected_catch_up > catch_up_limit:
                excess = projected_catch_up - catch_up_limit
                result.is_compliant = False
                result.allowed_amount = input_data.contribution_amount - excess
                result.excess_amount = excess
                result.violations.append({
                    'violation_type': ComplianceViolationType.EXCESS_DEFERRAL_402G,
                    'message': f'Catch-up contribution exceeds limit: ${projected_catch_up:,.2f} > ${catch_up_limit:,.2f}',
                    'regulatory_citation': 'IRC Section 414(v)'
                })
        else:
            # Regular deferral - check base limit
            projected_deferrals = current_deferrals + input_data.contribution_amount
            if projected_deferrals > base_limit:
                excess = projected_deferrals - base_limit
                result.is_compliant = False
                result.allowed_amount = input_data.contribution_amount - excess
                result.excess_amount = excess
                result.violations.append({
                    'violation_type': ComplianceViolationType.EXCESS_DEFERRAL_402G,
                    'message': f'Elective deferrals exceed limit: ${projected_deferrals:,.2f} > ${base_limit:,.2f}',
                    'regulatory_citation': 'IRC Section 402(g)'
                })

        # Calculate remaining capacity
        remaining_base = max(Decimal('0'), base_limit - current_deferrals)
        remaining_catch_up = max(Decimal('0'), catch_up_limit - catch_up_contributions) if result.catch_up_eligible else Decimal('0')

        result.remaining_capacity['402g_base'] = remaining_base
        result.remaining_capacity['402g_catch_up'] = remaining_catch_up

        # Warning if approaching limit
        if not result.violations and projected_deferrals > base_limit * Decimal('0.95'):
            result.warnings.append('Approaching 402(g) elective deferral limit')

    def _validate_415c_limits(
        self,
        input_data: ContributionValidationInput,
        result: ComplianceValidationResult,
        irs_limits: Any
    ) -> None:
        """Validate Section 415(c) annual additions limits"""

        # Calculate current annual additions (all sources)
        current_additions = sum(input_data.ytd_contributions.values())
        projected_additions = current_additions + input_data.contribution_amount

        # Get applicable limit (lesser of dollar limit or compensation limit)
        dollar_limit = Decimal(str(irs_limits.annual_additions_limit))
        compensation_limit = min(
            Decimal(str(irs_limits.compensation_limit)),
            input_data.ytd_compensation
        )
        applicable_limit = min(dollar_limit, compensation_limit)

        if projected_additions > applicable_limit:
            excess = projected_additions - applicable_limit

            # Determine if this violates the result (may already be non-compliant from 402g)
            if excess > result.excess_amount:
                result.is_compliant = False
                result.allowed_amount = input_data.contribution_amount - excess
                result.excess_amount = excess

            result.violations.append({
                'violation_type': ComplianceViolationType.ANNUAL_ADDITIONS_415C,
                'message': f'Annual additions exceed limit: ${projected_additions:,.2f} > ${applicable_limit:,.2f}',
                'regulatory_citation': 'IRC Section 415(c)',
                'limit_breakdown': {
                    'dollar_limit': float(dollar_limit),
                    'compensation_limit': float(compensation_limit),
                    'applicable_limit': float(applicable_limit)
                }
            })

        # Calculate remaining capacity
        remaining_capacity = max(Decimal('0'), applicable_limit - current_additions)
        result.remaining_capacity['415c'] = remaining_capacity

        # Warning if approaching limit
        if not any(v['violation_type'] == ComplianceViolationType.ANNUAL_ADDITIONS_415C for v in result.violations):
            if projected_additions > applicable_limit * Decimal('0.95'):
                result.warnings.append('Approaching 415(c) annual additions limit')

    def _validate_compensation_limits(
        self,
        input_data: ContributionValidationInput,
        result: ComplianceValidationResult,
        irs_limits: Any
    ) -> None:
        """Validate compensation-based limits"""

        compensation_limit = Decimal(str(irs_limits.compensation_limit))

        if input_data.ytd_compensation > compensation_limit:
            # Compensation exceeds IRS limit - should cap calculations
            result.warnings.append(
                f'Compensation ${input_data.ytd_compensation:,.2f} exceeds IRS limit ${compensation_limit:,.2f}'
            )

    def _generate_corrective_actions(
        self,
        input_data: ContributionValidationInput,
        result: ComplianceValidationResult
    ) -> None:
        """Generate recommended corrective actions"""

        # Determine appropriate correction method based on violation type and source
        violation_types = [v['violation_type'] for v in result.violations]

        if ComplianceViolationType.EXCESS_DEFERRAL_402G in violation_types:
            if input_data.contribution_source in [
                ContributionSource.EMPLOYEE_PRE_TAX,
                ContributionSource.EMPLOYEE_ROTH
            ]:
                result.recommended_correction = CorrectionMethod.REFUND_EMPLOYEE
                result.correction_details = {
                    'refund_amount': float(result.excess_amount),
                    'refund_source': input_data.contribution_source.value,
                    'correction_deadline': self._calculate_correction_deadline(input_data.plan_year),
                    'earnings_calculation_required': True
                }
            elif input_data.contribution_source == ContributionSource.EMPLOYEE_CATCH_UP:
                result.recommended_correction = CorrectionMethod.CAP_CONTRIBUTION
                result.correction_details = {
                    'capped_amount': float(result.allowed_amount),
                    'excess_amount': float(result.excess_amount)
                }

        elif ComplianceViolationType.ANNUAL_ADDITIONS_415C in violation_types:
            # Check if employer contributions can be reduced
            employer_sources = [
                ContributionSource.EMPLOYER_MATCH,
                ContributionSource.EMPLOYER_MATCH_TRUE_UP,
                ContributionSource.EMPLOYER_NONELECTIVE,
                ContributionSource.EMPLOYER_PROFIT_SHARING
            ]

            if input_data.contribution_source in employer_sources:
                result.recommended_correction = CorrectionMethod.REDUCE_EMPLOYER
                result.correction_details = {
                    'reduction_amount': float(result.excess_amount),
                    'affected_source': input_data.contribution_source.value
                }
            else:
                result.recommended_correction = CorrectionMethod.REALLOCATE_SOURCES
                result.correction_details = {
                    'reallocation_required': float(result.excess_amount),
                    'priority_order': ['employer_profit_sharing', 'employer_match_true_up', 'employer_match']
                }

        else:
            result.recommended_correction = CorrectionMethod.CAP_CONTRIBUTION
            result.correction_details = {
                'capped_amount': float(result.allowed_amount)
            }

    def process_contribution_with_enforcement(
        self,
        validation_input: ContributionValidationInput
    ) -> Dict[str, Any]:
        """Process contribution with automatic enforcement"""

        # Validate contribution
        validation_result = self.validate_contribution(validation_input)

        processing_result = {
            'original_amount': float(validation_input.contribution_amount),
            'processed_amount': float(validation_result.allowed_amount),
            'excess_amount': float(validation_result.excess_amount),
            'is_compliant': validation_result.is_compliant,
            'violations': validation_result.violations,
            'warnings': validation_result.warnings,
            'events_generated': []
        }

        # Generate compliance events for violations
        if not validation_result.is_compliant:
            compliance_events = self._generate_compliance_events(validation_input, validation_result)
            processing_result['events_generated'] = compliance_events

            # Publish events
            for event in compliance_events:
                self.event_publisher.publish_event(event)

        # Generate warning events if approaching limits
        if validation_result.warnings:
            warning_events = self._generate_warning_events(validation_input, validation_result)
            processing_result['events_generated'].extend(warning_events)

            for event in warning_events:
                self.event_publisher.publish_event(event)

        return processing_result

    def _generate_compliance_events(
        self,
        input_data: ContributionValidationInput,
        result: ComplianceValidationResult
    ) -> List[ComplianceEvent]:
        """Generate compliance events for violations"""

        events = []

        for violation in result.violations:
            event = ComplianceEvent(
                employee_id=input_data.employee_id,
                plan_id=input_data.plan_id,
                event_type='compliance_violation',
                effective_date=input_data.effective_date,
                plan_year=input_data.plan_year,
                violation_type=violation['violation_type'],
                limit_type=self._get_limit_type_from_violation(violation['violation_type']),
                applicable_limit=self._get_applicable_limit(violation, result),
                current_amount=sum(input_data.ytd_contributions.values()) + input_data.contribution_amount,
                excess_amount=result.excess_amount,
                correction_method=result.recommended_correction or CorrectionMethod.NO_ACTION,
                correction_amount=result.excess_amount,
                affected_sources=[input_data.contribution_source],
                correction_deadline=self._calculate_correction_deadline(input_data.plan_year)
            )
            events.append(event)

        return events

    def _generate_warning_events(
        self,
        input_data: ContributionValidationInput,
        result: ComplianceValidationResult
    ) -> List[ComplianceEvent]:
        """Generate warning events for approaching limits"""

        events = []

        for warning in result.warnings:
            event = ComplianceEvent(
                employee_id=input_data.employee_id,
                plan_id=input_data.plan_id,
                event_type='compliance_warning',
                effective_date=input_data.effective_date,
                plan_year=input_data.plan_year,
                violation_type=self._determine_warning_type(warning),
                limit_type='warning',
                applicable_limit=Decimal('0'),
                current_amount=sum(input_data.ytd_contributions.values()) + input_data.contribution_amount,
                excess_amount=Decimal('0'),
                correction_method=CorrectionMethod.NO_ACTION,
                correction_amount=Decimal('0'),
                affected_sources=[input_data.contribution_source]
            )
            events.append(event)

        return events

    def _is_catch_up_eligible(self, birth_date: date, plan_year: int) -> bool:
        """Check if employee is catch-up eligible (age 50+ by year end)"""
        year_end_age = plan_year - birth_date.year
        return year_end_age >= 50

    def _build_applicable_limits(self, irs_limits: Any, input_data: ContributionValidationInput) -> Dict[str, Decimal]:
        """Build dictionary of applicable limits"""
        return {
            '402g_base': Decimal(str(irs_limits.employee_deferral_limit)),
            '402g_catch_up': Decimal(str(irs_limits.catch_up_contribution_limit)),
            '415c_dollar': Decimal(str(irs_limits.annual_additions_limit)),
            '415c_compensation': min(
                Decimal(str(irs_limits.compensation_limit)),
                input_data.ytd_compensation
            )
        }

    def _calculate_correction_deadline(self, plan_year: int) -> date:
        """Calculate correction deadline (March 15 following plan year)"""
        return date(plan_year + 1, 3, 15)

    def _get_limit_type_from_violation(self, violation_type: ComplianceViolationType) -> str:
        """Map violation type to limit type"""
        mapping = {
            ComplianceViolationType.EXCESS_DEFERRAL_402G: 'elective_deferral',
            ComplianceViolationType.ANNUAL_ADDITIONS_415C: 'annual_additions',
            ComplianceViolationType.CATCH_UP_INELIGIBLE: 'catch_up',
            ComplianceViolationType.COMPENSATION_LIMIT: 'compensation'
        }
        return mapping.get(violation_type, 'unknown')

    def _get_applicable_limit(self, violation: Dict[str, Any], result: ComplianceValidationResult) -> Decimal:
        """Extract applicable limit from violation details"""
        if 'limit_breakdown' in violation:
            return Decimal(str(violation['limit_breakdown']['applicable_limit']))

        # Default to first applicable limit
        limits = result.applicable_limits
        if violation['violation_type'] == ComplianceViolationType.EXCESS_DEFERRAL_402G:
            return limits.get('402g_base', Decimal('0'))
        elif violation['violation_type'] == ComplianceViolationType.ANNUAL_ADDITIONS_415C:
            return limits.get('415c_dollar', Decimal('0'))

        return Decimal('0')

    def _determine_warning_type(self, warning: str) -> ComplianceViolationType:
        """Determine violation type from warning message"""
        if '402(g)' in warning:
            return ComplianceViolationType.EXCESS_DEFERRAL_402G
        elif '415(c)' in warning:
            return ComplianceViolationType.ANNUAL_ADDITIONS_415C
        else:
            return ComplianceViolationType.COMPENSATION_LIMIT
```

### Payroll Integration Service
```python
class PayrollIntegrationService:
    """Service for real-time payroll integration and enforcement"""

    def __init__(self, compliance_engine, notification_service):
        self.compliance_engine = compliance_engine
        self.notification_service = notification_service

    def validate_payroll_contribution(
        self,
        payroll_request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate payroll contribution request in real-time"""

        # Build validation input
        validation_input = ContributionValidationInput(
            employee_id=payroll_request['employee_id'],
            plan_id=payroll_request['plan_id'],
            plan_year=payroll_request['pay_date'].year,
            contribution_source=ContributionSource(payroll_request['contribution_source']),
            contribution_amount=Decimal(str(payroll_request['amount'])),
            effective_date=payroll_request['pay_date'],
            birth_date=payroll_request['employee_birth_date'],
            hire_date=payroll_request['employee_hire_date'],
            current_compensation=Decimal(str(payroll_request['annual_compensation'])),
            ytd_compensation=Decimal(str(payroll_request['ytd_compensation'])),
            ytd_contributions=self._convert_ytd_contributions(payroll_request['ytd_contributions']),
            pay_period_start=payroll_request['pay_period_start'],
            pay_period_end=payroll_request['pay_period_end'],
            payroll_frequency=payroll_request.get('payroll_frequency', 'bi_weekly')
        )

        # Process with enforcement
        result = self.compliance_engine.process_contribution_with_enforcement(validation_input)

        # Format response for payroll system
        payroll_response = {
            'employee_id': payroll_request['employee_id'],
            'original_amount': result['original_amount'],
            'approved_amount': result['processed_amount'],
            'excess_amount': result['excess_amount'],
            'approval_status': 'approved' if result['is_compliant'] else 'rejected_with_adjustment',
            'violations': result['violations'],
            'warnings': result['warnings'],
            'requires_notification': len(result['violations']) > 0,
            'transaction_id': self._generate_transaction_id()
        }

        # Send notifications if violations occurred
        if result['violations']:
            self._send_violation_notifications(payroll_request, result)

        return payroll_response

    def _convert_ytd_contributions(self, ytd_data: Dict[str, float]) -> Dict[ContributionSource, Decimal]:
        """Convert YTD contribution data to proper format"""
        converted = {}
        for source_str, amount in ytd_data.items():
            try:
                source = ContributionSource(source_str)
                converted[source] = Decimal(str(amount))
            except ValueError:
                # Skip unknown contribution sources
                pass
        return converted

    def _send_violation_notifications(
        self,
        payroll_request: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """Send notifications for compliance violations"""

        notification = {
            'type': 'compliance_violation',
            'employee_id': payroll_request['employee_id'],
            'plan_id': payroll_request['plan_id'],
            'pay_date': payroll_request['pay_date'],
            'violations': result['violations'],
            'original_amount': result['original_amount'],
            'approved_amount': result['processed_amount'],
            'requires_participant_notification': True,
            'requires_plan_admin_notification': True
        }

        self.notification_service.send_compliance_notification(notification)

    def _generate_transaction_id(self) -> str:
        """Generate unique transaction ID for audit trail"""
        return str(uuid.uuid4())
```

## Implementation Tasks

### Phase 1: Core Compliance Engine
- [ ] **Implement compliance models** with comprehensive validation
- [ ] **Create IRS compliance engine** with 402(g) and 415(c) validation
- [ ] **Build corrective action generation** logic
- [ ] **Add comprehensive unit tests** for all violation scenarios

### Phase 2: Real-Time Enforcement
- [ ] **Implement payroll integration service** for real-time validation
- [ ] **Create compliance event generation** and publishing
- [ ] **Build notification system** for violations and warnings
- [ ] **Add performance optimization** for high-volume processing

### Phase 3: Advanced Features
- [ ] **Implement catch-up contribution handling** with mid-year eligibility
- [ ] **Create correction deadline tracking** and enforcement
- [ ] **Build compliance reporting** and audit trail
- [ ] **Add integration testing** with contribution processing pipeline

## Dependencies

- **S072**: Event Schema (for compliance events)
- **S081**: Regulatory Limits Service (for IRS limits)
- **S079**: HCE Determination (for participant classification)
- **Contribution processing pipeline**: Real-time integration
- **Payroll systems**: External integration

## Success Metrics

### Compliance Requirements
- [ ] **Violation detection**: 100% accuracy for all IRS violations
- [ ] **Real-time validation**: <100ms response time for payroll requests
- [ ] **Correction accuracy**: 100% accurate calculation of corrective actions
- [ ] **Audit compliance**: Complete trail for all enforcement actions

### Performance Requirements
- [ ] **Single validation**: <50ms per contribution
- [ ] **Batch processing**: 10,000 contributions in <5 minutes
- [ ] **Payroll integration**: <200ms end-to-end response
- [ ] **Memory efficiency**: <500MB for 100K employee validations

## Definition of Done

- [ ] **Complete IRS compliance engine** enforcing all major regulations
- [ ] **Real-time payroll integration** with hard-stop enforcement
- [ ] **Compliance event generation** with complete audit trail
- [ ] **Corrective action framework** with automated calculations
- [ ] **Comprehensive testing** covering all violation scenarios
- [ ] **Performance benchmarks met** for enterprise-scale processing
- [ ] **Documentation complete** with regulatory references
- [ ] **Integration verified** with contribution processing systems
