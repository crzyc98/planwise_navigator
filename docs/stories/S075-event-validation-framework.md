# Story S075: Implement Event Validation Framework

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 12
**Priority**: High

## Story

**As a** compliance officer
**I want** automated validation of plan events
**So that** we catch data quality issues before they impact calculations

## Business Context

This story implements a comprehensive validation framework for DC plan events to ensure data quality, regulatory compliance, and business rule enforcement. The framework validates events against plan rules, IRS regulations, and data integrity constraints before they enter the event stream.

## Acceptance Criteria

### Core Validation Framework
- [ ] **Events validated against business rules** using Pydantic models
- [ ] **Invalid events quarantined** with detailed error descriptions
- [ ] **Daily data quality reports** generated with trend analysis
- [ ] **Alert on validation failure rates >1%**
- [ ] **Integrated compliance testing** for IRS limits and ERISA requirements
- [ ] **Performance validation** for vectorized operations

### HCE Determination Validation
- [ ] **Partial-year HCE determination** using YTD compensation vs. plan-year thresholds
- [ ] **HCE status recalculation** on each payroll event
- [ ] **Unit tests for HCE determination** across full-year and partial-year scenarios

### IRS Compliance Validation
- [ ] **Real-time 402(g) and 415(c) limit checks** on every contribution event
- [ ] **Pre-contribution validation** to prevent limit violations
- [ ] **Automatic contribution capping** when limits approached
- [ ] **Compliance event generation** for audit trail
- [ ] **Integration with payroll systems** for hard-stop enforcement
- [ ] **Year-specific limit retrieval** from versioned irs_limits table

## Technical Specifications

### Validation Framework Architecture
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, ValidationError
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

class ValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class ValidationResult(BaseModel):
    is_valid: bool
    severity: ValidationSeverity
    rule_id: str
    message: str
    field_path: Optional[str] = None
    suggested_fix: Optional[str] = None
    regulatory_citation: Optional[str] = None
    error_code: Optional[str] = None

class EventValidationContext(BaseModel):
    plan_config: Dict[str, Any]
    irs_limits: Dict[int, Any]  # Keyed by plan_year
    employee_data: Dict[str, Any]
    ytd_contributions: Dict[str, Decimal]
    current_date: date
    validation_mode: str = "strict"  # strict, permissive, audit_only

class BaseEventValidator(ABC):
    """Abstract base class for event validators"""

    def __init__(self, context: EventValidationContext):
        self.context = context

    @abstractmethod
    def validate(self, event: Dict[str, Any]) -> List[ValidationResult]:
        """Validate event and return validation results"""
        pass

    @abstractmethod
    def get_validator_id(self) -> str:
        """Return unique identifier for this validator"""
        pass
```

### Core Event Validators

#### Schema Validation
```python
class SchemaValidator(BaseEventValidator):
    """Validates event structure and data types"""

    def validate(self, event: Dict[str, Any]) -> List[ValidationResult]:
        results = []

        try:
            # Validate against Pydantic schema
            from models.events import RetirementPlanEvent
            validated_event = RetirementPlanEvent(**event)

            results.append(ValidationResult(
                is_valid=True,
                severity=ValidationSeverity.INFO,
                rule_id="SCHEMA_001",
                message="Event schema validation passed"
            ))

        except ValidationError as e:
            for error in e.errors():
                results.append(ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    rule_id="SCHEMA_002",
                    message=f"Schema validation failed: {error['msg']}",
                    field_path=".".join(str(loc) for loc in error['loc']),
                    suggested_fix="Correct the field value according to schema requirements",
                    error_code="SCHEMA_VIOLATION"
                ))

        return results

    def get_validator_id(self) -> str:
        return "schema_validator"
```

#### Business Rule Validator
```python
class BusinessRuleValidator(BaseEventValidator):
    """Validates business logic and plan-specific rules"""

    def validate(self, event: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        event_type = event.get('event_type')

        if event_type == 'enrollment':
            results.extend(self._validate_enrollment_rules(event))
        elif event_type == 'contribution':
            results.extend(self._validate_contribution_rules(event))
        elif event_type == 'vesting':
            results.extend(self._validate_vesting_rules(event))

        return results

    def _validate_enrollment_rules(self, event: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        payload = event.get('payload', {})
        employee_id = event.get('employee_id')

        # Rule: Total contribution rate cannot exceed 100%
        total_rate = (
            payload.get('pre_tax_contribution_rate', 0) +
            payload.get('roth_contribution_rate', 0)
        )

        if total_rate > 1.0:
            results.append(ValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                rule_id="BIZ_001",
                message=f"Total contribution rate {total_rate:.2%} exceeds 100%",
                suggested_fix="Reduce contribution rates to total ≤ 100%",
                error_code="CONTRIBUTION_RATE_EXCEEDED"
            ))

        # Rule: Check eligibility requirements
        employee_data = self.context.employee_data.get(employee_id, {})
        plan_config = self.context.plan_config

        employee_age = self._calculate_age(employee_data.get('birth_date'), event.get('effective_date'))
        if employee_age < plan_config.get('eligibility', {}).get('minimum_age', 21):
            results.append(ValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                rule_id="BIZ_002",
                message=f"Employee age {employee_age} below minimum eligibility age",
                regulatory_citation="IRC Section 410(a)(1)(A)",
                error_code="AGE_ELIGIBILITY_VIOLATION"
            ))

        return results

    def _validate_contribution_rules(self, event: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        payload = event.get('payload', {})
        amount = Decimal(str(payload.get('amount', 0)))

        # Rule: Contribution amount must be positive
        if amount <= 0:
            results.append(ValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                rule_id="BIZ_003",
                message="Contribution amount must be positive",
                field_path="payload.amount",
                error_code="INVALID_CONTRIBUTION_AMOUNT"
            ))

        # Rule: Check for reasonable contribution amounts
        if amount > 100000:  # Arbitrary large amount check
            results.append(ValidationResult(
                is_valid=False,
                severity=ValidationSeverity.WARNING,
                rule_id="BIZ_004",
                message=f"Unusually large contribution amount: ${amount:,.2f}",
                suggested_fix="Verify contribution amount is correct",
                error_code="LARGE_CONTRIBUTION_WARNING"
            ))

        return results

    def _calculate_age(self, birth_date: date, as_of_date: date) -> int:
        """Calculate age as of specific date"""
        return as_of_date.year - birth_date.year - ((as_of_date.month, as_of_date.day) < (birth_date.month, birth_date.day))

    def get_validator_id(self) -> str:
        return "business_rule_validator"
```

#### IRS Compliance Validator
```python
class IRSComplianceValidator(BaseEventValidator):
    """Validates IRS regulatory compliance"""

    def validate(self, event: Dict[str, Any]) -> List[ValidationResult]:
        results = []

        if event.get('event_type') == 'contribution':
            results.extend(self._validate_402g_limits(event))
            results.extend(self._validate_415c_limits(event))
            results.extend(self._validate_catch_up_eligibility(event))

        return results

    def _validate_402g_limits(self, event: Dict[str, Any]) -> List[ValidationResult]:
        """Validate Section 402(g) elective deferral limits"""
        results = []
        employee_id = event.get('employee_id')
        plan_year = event.get('plan_year')
        payload = event.get('payload', {})

        # Get employee data and current contributions
        employee_data = self.context.employee_data.get(employee_id, {})
        ytd_contributions = self.context.ytd_contributions.get(employee_id, {})

        # Calculate current deferrals
        current_deferrals = (
            ytd_contributions.get('employee_pre_tax', Decimal('0')) +
            ytd_contributions.get('employee_roth', Decimal('0'))
        )

        # Add new contribution if it's an elective deferral
        contribution_source = payload.get('source', '')
        new_amount = Decimal(str(payload.get('amount', 0)))

        if contribution_source in ['employee_pre_tax', 'employee_roth']:
            projected_deferrals = current_deferrals + new_amount

            # Get IRS limits for the plan year
            irs_limits = self.context.irs_limits.get(plan_year, {})
            deferral_limit = Decimal(str(irs_limits.get('employee_deferral_limit', 23500)))
            catch_up_limit = Decimal(str(irs_limits.get('catch_up_contribution_limit', 7500)))

            # Check catch-up eligibility
            birth_date = employee_data.get('birth_date')
            is_catch_up_eligible = self._is_catch_up_eligible(birth_date, plan_year)

            applicable_limit = deferral_limit + (catch_up_limit if is_catch_up_eligible else Decimal('0'))

            if projected_deferrals > applicable_limit:
                excess_amount = projected_deferrals - applicable_limit
                results.append(ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    rule_id="IRS_402G_001",
                    message=f"Exceeds 402(g) limit: ${projected_deferrals:,.2f} > ${applicable_limit:,.2f}",
                    suggested_fix=f"Reduce contribution by ${excess_amount:,.2f}",
                    regulatory_citation="IRC Section 402(g)",
                    error_code="402G_LIMIT_EXCEEDED"
                ))
            elif projected_deferrals > applicable_limit * Decimal('0.95'):
                # Warning when approaching limit
                results.append(ValidationResult(
                    is_valid=True,
                    severity=ValidationSeverity.WARNING,
                    rule_id="IRS_402G_002",
                    message=f"Approaching 402(g) limit: ${projected_deferrals:,.2f} (limit: ${applicable_limit:,.2f})",
                    error_code="402G_LIMIT_WARNING"
                ))

        return results

    def _validate_415c_limits(self, event: Dict[str, Any]) -> List[ValidationResult]:
        """Validate Section 415(c) annual additions limits"""
        results = []
        employee_id = event.get('employee_id')
        plan_year = event.get('plan_year')
        payload = event.get('payload', {})

        # Get current annual additions
        ytd_contributions = self.context.ytd_contributions.get(employee_id, {})
        current_additions = sum(ytd_contributions.values())

        # Add new contribution
        new_amount = Decimal(str(payload.get('amount', 0)))
        projected_additions = current_additions + new_amount

        # Get IRS limit
        irs_limits = self.context.irs_limits.get(plan_year, {})
        additions_limit = Decimal(str(irs_limits.get('annual_additions_limit', 69000)))

        if projected_additions > additions_limit:
            excess_amount = projected_additions - additions_limit
            results.append(ValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                rule_id="IRS_415C_001",
                message=f"Exceeds 415(c) limit: ${projected_additions:,.2f} > ${additions_limit:,.2f}",
                suggested_fix=f"Reduce contribution by ${excess_amount:,.2f}",
                regulatory_citation="IRC Section 415(c)",
                error_code="415C_LIMIT_EXCEEDED"
            ))

        return results

    def _validate_catch_up_eligibility(self, event: Dict[str, Any]) -> List[ValidationResult]:
        """Validate catch-up contribution eligibility"""
        results = []
        payload = event.get('payload', {})

        if payload.get('source') == 'employee_catch_up':
            employee_id = event.get('employee_id')
            plan_year = event.get('plan_year')

            employee_data = self.context.employee_data.get(employee_id, {})
            birth_date = employee_data.get('birth_date')

            if not self._is_catch_up_eligible(birth_date, plan_year):
                results.append(ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    rule_id="IRS_CATCHUP_001",
                    message="Employee not eligible for catch-up contributions",
                    regulatory_citation="IRC Section 414(v)",
                    error_code="CATCH_UP_NOT_ELIGIBLE"
                ))

        return results

    def _is_catch_up_eligible(self, birth_date: date, plan_year: int) -> bool:
        """Check if employee is catch-up eligible (age 50+ by year end)"""
        if not birth_date:
            return False
        year_end_age = plan_year - birth_date.year
        return year_end_age >= 50

    def get_validator_id(self) -> str:
        return "irs_compliance_validator"
```

#### HCE Determination Validator
```python
class HCEDeterminationValidator(BaseEventValidator):
    """Validates HCE status determination and recalculation"""

    def validate(self, event: Dict[str, Any]) -> List[ValidationResult]:
        results = []

        if event.get('event_type') == 'hce_status':
            results.extend(self._validate_hce_calculation(event))
        elif event.get('event_type') == 'contribution':
            # Trigger HCE recalculation on compensation events
            results.extend(self._validate_hce_recalculation_trigger(event))

        return results

    def _validate_hce_calculation(self, event: Dict[str, Any]) -> List[ValidationResult]:
        """Validate HCE status calculation logic"""
        results = []
        payload = event.get('payload', {})
        employee_id = event.get('employee_id')
        plan_year = event.get('plan_year')

        # Validate compensation annualization for partial year employees
        ytd_compensation = Decimal(str(payload.get('ytd_compensation', 0)))
        annualized_compensation = Decimal(str(payload.get('annualized_compensation', 0)))

        employee_data = self.context.employee_data.get(employee_id, {})
        hire_date = employee_data.get('hire_date')

        # Check if annualization is correct for partial year employees
        if hire_date and hire_date.year == plan_year:
            months_worked = 12 - hire_date.month + 1
            expected_annualized = ytd_compensation * Decimal('12') / Decimal(str(months_worked))

            if abs(annualized_compensation - expected_annualized) > Decimal('100'):
                results.append(ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    rule_id="HCE_001",
                    message=f"Incorrect compensation annualization: ${annualized_compensation:,.2f} vs expected ${expected_annualized:,.2f}",
                    field_path="payload.annualized_compensation",
                    error_code="HCE_ANNUALIZATION_ERROR"
                ))

        # Validate HCE threshold comparison
        hce_threshold = Decimal(str(payload.get('hce_threshold', 0)))
        is_hce = payload.get('is_hce', False)
        expected_hce = annualized_compensation >= hce_threshold

        if is_hce != expected_hce:
            results.append(ValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                rule_id="HCE_002",
                message=f"Incorrect HCE determination: {is_hce} (compensation: ${annualized_compensation:,.2f}, threshold: ${hce_threshold:,.2f})",
                error_code="HCE_DETERMINATION_ERROR"
            ))

        return results

    def _validate_hce_recalculation_trigger(self, event: Dict[str, Any]) -> List[ValidationResult]:
        """Check if HCE status should be recalculated after compensation event"""
        results = []

        # This would trigger a separate HCE recalculation process
        # For validation purposes, we just note that recalculation may be needed
        results.append(ValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            rule_id="HCE_003",
            message="HCE status recalculation may be required after compensation change",
            error_code="HCE_RECALC_TRIGGER"
        ))

        return results

    def get_validator_id(self) -> str:
        return "hce_determination_validator"
```

### Event Validation Pipeline
```python
class EventValidationPipeline:
    """Orchestrates event validation through multiple validators"""

    def __init__(self, validators: List[BaseEventValidator]):
        self.validators = validators
        self.quarantine_threshold = 0.01  # 1% failure rate

    def validate_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Validate single event through all validators"""
        all_results = []

        for validator in self.validators:
            try:
                results = validator.validate(event)
                all_results.extend(results)
            except Exception as e:
                all_results.append(ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.CRITICAL,
                    rule_id="PIPELINE_001",
                    message=f"Validator {validator.get_validator_id()} failed: {str(e)}",
                    error_code="VALIDATOR_EXCEPTION"
                ))

        # Determine overall validation status
        has_errors = any(not result.is_valid for result in all_results)
        has_critical = any(result.severity == ValidationSeverity.CRITICAL for result in all_results)

        return {
            'event': event,
            'validation_results': [result.dict() for result in all_results],
            'is_valid': not has_errors,
            'should_quarantine': has_critical,
            'validation_timestamp': datetime.utcnow(),
            'validator_version': '1.0.0'
        }

    def validate_batch(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate batch of events and generate summary report"""
        validated_events = []
        quarantined_events = []
        validation_summary = {
            'total_events': len(events),
            'valid_events': 0,
            'invalid_events': 0,
            'quarantined_events': 0,
            'validation_errors': [],
            'error_summary': {}
        }

        for event in events:
            validation_result = self.validate_event(event)

            if validation_result['should_quarantine']:
                quarantined_events.append(validation_result)
                validation_summary['quarantined_events'] += 1
            elif validation_result['is_valid']:
                validated_events.append(event)
                validation_summary['valid_events'] += 1
            else:
                validation_summary['invalid_events'] += 1
                validation_summary['validation_errors'].append(validation_result)

            # Collect error statistics
            for result in validation_result['validation_results']:
                if not result['is_valid']:
                    error_code = result.get('error_code', 'UNKNOWN')
                    validation_summary['error_summary'][error_code] = validation_summary['error_summary'].get(error_code, 0) + 1

        # Calculate failure rate and trigger alerts if needed
        failure_rate = (validation_summary['invalid_events'] + validation_summary['quarantined_events']) / validation_summary['total_events']
        if failure_rate > self.quarantine_threshold:
            self._trigger_validation_alert(failure_rate, validation_summary)

        return {
            'validated_events': validated_events,
            'quarantined_events': quarantined_events,
            'summary': validation_summary,
            'failure_rate': failure_rate
        }

    def _trigger_validation_alert(self, failure_rate: float, summary: Dict[str, Any]):
        """Trigger alert when validation failure rate exceeds threshold"""
        # Implementation would send alert to monitoring system
        print(f"ALERT: Validation failure rate {failure_rate:.2%} exceeds threshold {self.quarantine_threshold:.2%}")
        print(f"Error summary: {summary['error_summary']}")
```

### Data Quality Reporting
```python
class DataQualityReporter:
    """Generates data quality reports and trend analysis"""

    def __init__(self, validation_history_table: str):
        self.validation_history_table = validation_history_table

    def generate_daily_report(self, report_date: date) -> Dict[str, Any]:
        """Generate daily data quality report"""
        # Query validation results from database
        validation_data = self._query_validation_data(report_date)

        report = {
            'report_date': report_date,
            'total_events_processed': len(validation_data),
            'validation_summary': self._calculate_validation_summary(validation_data),
            'error_trends': self._analyze_error_trends(validation_data),
            'top_validation_failures': self._get_top_failures(validation_data),
            'compliance_metrics': self._calculate_compliance_metrics(validation_data),
            'recommendations': self._generate_recommendations(validation_data)
        }

        return report

    def _calculate_validation_summary(self, validation_data: List[Dict]) -> Dict[str, Any]:
        """Calculate validation summary statistics"""
        total = len(validation_data)
        valid = sum(1 for v in validation_data if v['is_valid'])
        quarantined = sum(1 for v in validation_data if v['should_quarantine'])

        return {
            'total_events': total,
            'valid_events': valid,
            'invalid_events': total - valid,
            'quarantined_events': quarantined,
            'success_rate': valid / total if total > 0 else 0,
            'failure_rate': (total - valid) / total if total > 0 else 0
        }

    def _analyze_error_trends(self, validation_data: List[Dict]) -> Dict[str, Any]:
        """Analyze error trends over time"""
        # Implementation would analyze trends
        return {'trend_analysis': 'stable', 'emerging_issues': []}

    def _get_top_failures(self, validation_data: List[Dict]) -> List[Dict[str, Any]]:
        """Get top validation failure types"""
        error_counts = {}
        for validation in validation_data:
            if not validation['is_valid']:
                for result in validation['validation_results']:
                    if not result['is_valid']:
                        error_code = result.get('error_code', 'UNKNOWN')
                        error_counts[error_code] = error_counts.get(error_code, 0) + 1

        return sorted([{'error_code': k, 'count': v} for k, v in error_counts.items()],
                     key=lambda x: x['count'], reverse=True)[:10]
```

## Implementation Tasks

### Phase 1: Core Framework
- [ ] **Implement base validation classes** and result structures
- [ ] **Create schema validator** for event structure validation
- [ ] **Build business rule validator** for plan-specific rules
- [ ] **Add comprehensive unit tests** for validation logic

### Phase 2: Compliance Validators
- [ ] **Implement IRS compliance validator** for 402(g) and 415(c) limits
- [ ] **Create HCE determination validator** with annualization logic
- [ ] **Add catch-up contribution validation** for age eligibility
- [ ] **Build integration tests** with plan configuration

### Phase 3: Pipeline and Reporting
- [ ] **Create event validation pipeline** for batch processing
- [ ] **Implement quarantine system** for invalid events
- [ ] **Build data quality reporting** with trend analysis
- [ ] **Add alerting system** for validation failure thresholds

## Dependencies

- **S072**: Retirement Plan Event Schema (defines event structure)
- **S074**: Plan Configuration Schema (provides plan rules)
- **S073**: dbt Models (provides IRS limits and employee data)
- **Existing workforce data**: Employee demographics and compensation

## Success Metrics

### Data Quality Requirements
- [ ] **Validation accuracy**: <0.1% false positive rate
- [ ] **Performance**: <10ms per event validation
- [ ] **Coverage**: 100% of event types have validation rules
- [ ] **Compliance**: Zero undetected IRS violations in production

### Operational Requirements
- [ ] **Failure rate monitoring**: Alert when >1% events fail validation
- [ ] **Quarantine processing**: Invalid events isolated within 1 minute
- [ ] **Report generation**: Daily reports available by 8 AM
- [ ] **Trend analysis**: 30-day rolling validation metrics

## Definition of Done

- [ ] **Complete validation framework** supporting all event types
- [ ] **IRS compliance validation** for all major regulations
- [ ] **HCE determination validation** with partial-year support
- [ ] **Event quarantine system** with detailed error reporting
- [ ] **Data quality reporting** with trend analysis
- [ ] **Comprehensive testing** covering all validation scenarios
- [ ] **Performance benchmarks met** for enterprise-scale processing
- [ ] **Integration verified** with event processing pipeline
