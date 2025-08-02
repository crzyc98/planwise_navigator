"""
Comprehensive Validation Suite for orchestrator_dbt.

This package provides enterprise-grade validation capabilities for financial
calculations, audit trail completeness, and regulatory compliance across
the workforce simulation platform.

Key Components:
- FinancialAuditValidator: Comprehensive financial precision and audit trail validation
- ValidationResult/ValidationSummary: Structured validation reporting
- Performance impact monitoring and compliance reporting

Usage:
    from orchestrator_dbt.validation import (
        FinancialAuditValidator,
        create_financial_audit_validator,
        validate_financial_precision_quick
    )

    # Create validator
    validator = create_financial_audit_validator(database_manager, config)

    # Run comprehensive validation
    summary = validator.run_comprehensive_validation(simulation_year=2025)

    # Check compliance
    if summary.is_compliant:
        print("✅ All validation checks passed")
    else:
        print(f"❌ {summary.critical_issues} critical issues found")
"""

from .financial_audit_validator import (
    FinancialAuditValidator,
    ValidationResult,
    ValidationSummary,
    ValidationSeverity,
    ValidationCategory,
    create_financial_audit_validator,
    validate_financial_precision_quick
)

__all__ = [
    'FinancialAuditValidator',
    'ValidationResult',
    'ValidationSummary',
    'ValidationSeverity',
    'ValidationCategory',
    'create_financial_audit_validator',
    'validate_financial_precision_quick'
]
