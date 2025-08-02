# Financial Audit Validation Suite

Comprehensive validation framework for ensuring financial precision and audit trail compliance in the migrated orchestrator_dbt event generation system.

## Overview ✨

This validation suite was created as part of **Story S031-03: Event Generation Performance** to ensure the migrated event generation system maintains the same level of financial precision and audit trail completeness as the MVP system while meeting enterprise regulatory compliance requirements.

### Key Features 🎯

- **Financial Precision Validation**: Ensures 6-decimal precision in all compensation calculations
- **Audit Trail Completeness**: Validates required audit fields and UUID integrity
- **Event Sourcing Integrity**: Checks immutability and ordering of events
- **Data Consistency**: Validates consistency across related tables
- **Business Rule Compliance**: Ensures business logic compliance
- **Performance Monitoring**: Tracks validation performance impact
- **Regulatory Compliance**: Meets enterprise audit requirements

## Quick Start 🚀

### Basic Usage

```python
from orchestrator_dbt.validation import create_financial_audit_validator
from orchestrator_dbt.core.database_manager import DatabaseManager
from orchestrator_dbt.core.config import OrchestrationConfig

# Create validator
config = OrchestrationConfig()
database_manager = DatabaseManager(config)
validator = create_financial_audit_validator(database_manager, config)

# Run comprehensive validation
summary = validator.run_comprehensive_validation(simulation_year=2025)

# Check results
if summary.is_compliant:
    print("✅ All validation checks passed")
else:
    print(f"❌ {summary.critical_issues} critical issues found")
    for issue in summary.get_issues_by_severity(ValidationSeverity.CRITICAL):
        print(f"   • {issue.check_name}: {issue.message}")
```

### Command Line Interface

```bash
# Run all validation checks
python orchestrator_dbt/validation/run_validation.py

# Run validation for specific year
python orchestrator_dbt/validation/run_validation.py --year 2025

# Run only financial precision checks
python orchestrator_dbt/validation/run_validation.py --scope financial_precision

# Quick validation (financial precision only)
python orchestrator_dbt/validation/run_validation.py --quick

# Detailed reporting
python orchestrator_dbt/validation/run_validation.py --verbose --report validation_report.json
```

## Validation Categories 📋

### 1. Financial Precision (`financial_precision`)

Validates that all financial calculations maintain 6-decimal precision:

- **Compensation Precision**: Ensures compensation values don't exceed 6 decimal places
- **Calculation Consistency**: Validates events match workforce snapshots
- **Proration Accuracy**: Checks partial-year event proration calculations
- **Cumulative Accuracy**: Validates compensation chains across multiple years

```python
# Run only financial precision validation
summary = validator.run_comprehensive_validation(
    simulation_year=2025,
    validation_scope=[ValidationCategory.FINANCIAL_PRECISION]
)
```

### 2. Audit Trail (`audit_trail`)

Ensures complete audit trail for regulatory compliance:

- **Required Fields**: Validates presence of all audit-required fields
- **UUID Integrity**: Checks UUID format and uniqueness
- **Timestamp Consistency**: Validates logical timestamp ordering
- **Event Sequence**: Ensures proper event sequence numbering

### 3. Event Sourcing (`event_sourcing`)

Validates event sourcing architecture integrity:

- **Event Immutability**: Ensures events cannot be modified
- **Event Ordering**: Validates chronological event consistency
- **Workforce Reconstruction**: Tests ability to rebuild state from events

### 4. Data Consistency (`data_consistency`)

Checks consistency across related tables:

- **Employee ID Consistency**: Validates IDs across all tables
- **Cross-table Compensation**: Ensures compensation matches between tables
- **Employment Status**: Validates status consistency

### 5. Business Rules (`business_rules`)

Validates business logic compliance:

- **Compensation Limits**: Checks increase limits and ranges
- **Promotion Eligibility**: Validates promotion business rules
- **Termination Rules**: Ensures termination logic compliance

### 6. Performance (`performance`)

Monitors performance requirements:

- **Query Performance**: Benchmarks critical query execution times
- **Data Volume Handling**: Tests large dataset processing capability

### 7. Regulatory Compliance (`regulatory_compliance`)

Ensures regulatory requirements are met:

- **Data Retention**: Validates retention policy compliance
- **Compensation Equity**: Checks equity compliance requirements

## Integration with Development Workflow 🔄

### Pre-commit Validation

Add to your pre-commit hooks:

```bash
#!/bin/bash
# .git/hooks/pre-commit

echo "Running financial audit validation..."
python orchestrator_dbt/validation/run_validation.py --quick

if [ $? -ne 0 ]; then
    echo "❌ Validation failed - commit blocked"
    exit 1
fi

echo "✅ Validation passed"
```

### CI/CD Integration

```yaml
# .github/workflows/validation.yml
name: Financial Audit Validation

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.11

    - name: Install dependencies
      run: |
        pip install -r requirements.txt

    - name: Run validation suite
      run: |
        python orchestrator_dbt/validation/run_validation.py --verbose --report validation_report.json

    - name: Upload validation report
      uses: actions/upload-artifact@v2
      if: always()
      with:
        name: validation-report
        path: validation_report.json
```

### Testing Integration

```python
# In your test suite
from orchestrator_dbt.validation import validate_financial_precision_quick

def test_event_generation_precision():
    """Test that event generation maintains financial precision."""
    # Generate test events
    events = generate_test_events()

    # Run quick validation
    result = validate_financial_precision_quick(database_manager)

    assert result['is_compliant'], f"Precision issues: {result['error_issues']}"
    assert result['success_rate'] >= 95.0, "Success rate below threshold"
```

## Advanced Usage 🔧

### Custom Validation Rules

```python
class CustomValidator(FinancialAuditValidator):
    """Custom validator with additional business rules."""

    def _validate_custom_business_rules(self, simulation_year):
        """Add custom business rule validation."""
        # Custom validation logic
        check_name = "custom_rule_validation"

        try:
            # Your custom validation query
            with self.db_manager.get_connection() as conn:
                result = conn.execute("SELECT COUNT(*) FROM custom_check").fetchone()

                if result[0] > 0:
                    self._add_validation_result(
                        check_name=check_name,
                        category=ValidationCategory.BUSINESS_RULES,
                        severity=ValidationSeverity.ERROR,
                        status="FAIL",
                        message="Custom business rule violation",
                        affected_records=result[0]
                    )
                else:
                    self._add_validation_result(
                        check_name=check_name,
                        category=ValidationCategory.BUSINESS_RULES,
                        severity=ValidationSeverity.INFO,
                        status="PASS",
                        message="Custom business rules compliant"
                    )

        except Exception as e:
            self._add_validation_result(
                check_name=check_name,
                category=ValidationCategory.BUSINESS_RULES,
                severity=ValidationSeverity.ERROR,
                status="FAIL",
                message=f"Custom validation failed: {str(e)}"
            )
```

### Performance Monitoring

```python
# Monitor validation performance
validator = create_financial_audit_validator(db_manager, config)
summary = validator.run_comprehensive_validation()

print(f"Validation took {summary.total_execution_time:.3f}s")

# Get detailed performance metrics
for category, time_taken in validator.performance_metrics['check_execution_times'].items():
    print(f"{category}: {time_taken:.3f}s")
```

## Validation Report Format 📊

The validation suite generates detailed JSON reports:

```json
{
  "validation_summary": {
    "timestamp": "2025-01-01T12:00:00",
    "total_checks": 15,
    "passed_checks": 13,
    "failed_checks": 2,
    "warning_checks": 0,
    "critical_issues": 0,
    "error_issues": 2,
    "success_rate": 86.7,
    "is_compliant": false,
    "total_execution_time": 3.456
  },
  "validation_results": [
    {
      "check_name": "compensation_precision_events",
      "category": "financial_precision",
      "severity": "error",
      "status": "FAIL",
      "message": "Financial precision violations found: 5 events exceed 6 decimal places",
      "details": {
        "violation_count": 5,
        "affected_employees": 3,
        "max_compensation_decimals": 8,
        "required_precision": 6
      },
      "affected_records": 5,
      "resolution_guidance": "Review compensation calculation logic to ensure proper rounding to 6 decimal places"
    }
  ],
  "metadata": {
    "generated_by": "orchestrator_dbt_validation_suite",
    "story": "S031-03-event-generation-performance",
    "purpose": "financial_precision_and_audit_trail_validation"
  }
}
```

## Testing 🧪

Run the validation test suite:

```bash
# Run all tests
python orchestrator_dbt/validation/test_validation_suite.py

# Run specific test categories
python -m unittest orchestrator_dbt.validation.test_validation_suite.TestFinancialAuditValidator

# Run with coverage
python -m coverage run orchestrator_dbt/validation/test_validation_suite.py
python -m coverage report
```

## Performance Considerations ⚡

### Optimization Tips

1. **Batch Processing**: Validation uses batch SQL operations for efficiency
2. **Selective Validation**: Use `validation_scope` to run only needed checks
3. **Quick Validation**: Use `--quick` for development feedback
4. **Parallel Execution**: Some checks run in parallel automatically

### Performance Benchmarks

| Operation | Target Time | Description |
|-----------|-------------|-------------|
| Quick Validation | <30 seconds | Financial precision only |
| Full Validation | <5 minutes | All categories |
| Large Dataset (1M+ events) | <15 minutes | Comprehensive validation |

## Troubleshooting 🔧

### Common Issues

**Issue**: Validation fails with database connection error
```bash
❌ Failed to validate: database connection error
```
**Solution**: Ensure database file exists and no other processes have it locked

**Issue**: Memory issues with large datasets
```bash
❌ Memory error during validation
```
**Solution**: Use selective validation scope or increase system memory

**Issue**: Performance slower than expected
```bash
⚠️ Validation took 15 minutes (expected <5 minutes)
```
**Solution**: Check database indexes and consider running with limited scope

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run validation with debug logging
validator = create_financial_audit_validator(db_manager, config)
summary = validator.run_comprehensive_validation()
```

## Integration with Story S031-03 🎯

This validation suite directly supports the objectives of Story S031-03:

- **✅ Financial Precision**: Validates 6-decimal precision maintained during migration
- **✅ Audit Trail Compliance**: Ensures regulatory audit trail requirements
- **✅ Performance Validation**: Monitors impact on system performance
- **✅ Quality Assurance**: Comprehensive validation of migrated system
- **✅ Stakeholder Confidence**: Detailed reporting for regulatory review

## Contributing 🤝

When adding new validation checks:

1. **Add to appropriate category** in `FinancialAuditValidator`
2. **Include comprehensive tests** in `test_validation_suite.py`
3. **Update documentation** in this README
4. **Follow naming conventions**: `_check_specific_validation_name`
5. **Include resolution guidance** for failed checks

### Example New Check

```python
def _check_new_business_rule(self, simulation_year: Optional[int]) -> None:
    """Check new business rule compliance."""
    check_name = "new_business_rule_compliance"

    try:
        # Validation logic here
        with self.db_manager.get_connection() as conn:
            result = conn.execute("SELECT COUNT(*) FROM violations").fetchone()

            if result[0] > 0:
                self._add_validation_result(
                    check_name=check_name,
                    category=ValidationCategory.BUSINESS_RULES,
                    severity=ValidationSeverity.ERROR,
                    status="FAIL",
                    message=f"Business rule violations: {result[0]}",
                    affected_records=result[0],
                    resolution_guidance="Review business rule implementation"
                )
            else:
                self._add_validation_result(
                    check_name=check_name,
                    category=ValidationCategory.BUSINESS_RULES,
                    severity=ValidationSeverity.INFO,
                    status="PASS",
                    message="Business rule compliance verified"
                )

    except Exception as e:
        self._add_validation_result(
            check_name=check_name,
            category=ValidationCategory.BUSINESS_RULES,
            severity=ValidationSeverity.ERROR,
            status="FAIL",
            message=f"Validation failed: {str(e)}",
            resolution_guidance="Check database connectivity and query logic"
        )
```

---

**For questions or support, refer to the main orchestrator_dbt documentation or create an issue in the project repository.**
