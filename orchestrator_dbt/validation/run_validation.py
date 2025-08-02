#!/usr/bin/env python3
"""
Command-line interface for running comprehensive financial audit validation.

This script provides a convenient way to execute validation checks for the
migrated event generation system, ensuring financial precision and audit
trail compliance.

Usage:
    # Run all validation checks
    python orchestrator_dbt/validation/run_validation.py

    # Run validation for specific year
    python orchestrator_dbt/validation/run_validation.py --year 2025

    # Run only financial precision checks
    python orchestrator_dbt/validation/run_validation.py --scope financial_precision

    # Run with detailed reporting
    python orchestrator_dbt/validation/run_validation.py --verbose --report validation_report.json

    # Quick validation (financial precision only)
    python orchestrator_dbt/validation/run_validation.py --quick

Integration with Story S031-03:
- Validates migrated event generation system maintains MVP financial precision
- Ensures audit trail completeness for regulatory compliance
- Provides performance benchmarking for the 65% improvement target
- Creates comprehensive reports for stakeholder review
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from orchestrator_dbt.core.database_manager import DatabaseManager
from orchestrator_dbt.core.config import OrchestrationConfig
from orchestrator_dbt.validation import (
    FinancialAuditValidator,
    ValidationCategory,
    create_financial_audit_validator,
    validate_financial_precision_quick
)


def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def parse_validation_scope(scope_arg: Optional[str]) -> Optional[List[ValidationCategory]]:
    """Parse validation scope argument into categories."""
    if not scope_arg:
        return None

    scope_mapping = {
        'financial_precision': ValidationCategory.FINANCIAL_PRECISION,
        'audit_trail': ValidationCategory.AUDIT_TRAIL,
        'event_sourcing': ValidationCategory.EVENT_SOURCING,
        'data_consistency': ValidationCategory.DATA_CONSISTENCY,
        'business_rules': ValidationCategory.BUSINESS_RULES,
        'performance': ValidationCategory.PERFORMANCE,
        'regulatory_compliance': ValidationCategory.REGULATORY_COMPLIANCE
    }

    scopes = [s.strip() for s in scope_arg.split(',')]
    categories = []

    for scope in scopes:
        if scope in scope_mapping:
            categories.append(scope_mapping[scope])
        else:
            print(f"⚠️ Unknown validation scope: {scope}")
            print(f"Available scopes: {', '.join(scope_mapping.keys())}")
            sys.exit(1)

    return categories


def print_validation_summary(summary, verbose: bool = False) -> None:
    """Print validation summary to console."""
    print("\n" + "="*80)
    print("📋 FINANCIAL AUDIT VALIDATION SUMMARY")
    print("="*80)

    # Overall status
    status_icon = "✅" if summary.is_compliant else "❌"
    print(f"\n{status_icon} Overall Status: {'COMPLIANT' if summary.is_compliant else 'NON-COMPLIANT'}")
    print(f"📊 Success Rate: {summary.success_rate:.1f}%")
    print(f"⏱️  Total Execution Time: {summary.total_execution_time:.3f}s")
    print(f"📅 Validation Timestamp: {summary.validation_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

    # Check summary
    print(f"\n📈 Check Summary:")
    print(f"   Total Checks: {summary.total_checks}")
    print(f"   ✅ Passed: {summary.passed_checks}")
    print(f"   ❌ Failed: {summary.failed_checks}")
    print(f"   ⚠️  Warnings: {summary.warning_checks}")

    # Issue summary
    if summary.critical_issues > 0 or summary.error_issues > 0:
        print(f"\n🚨 Issues Found:")
        if summary.critical_issues > 0:
            print(f"   🔴 Critical: {summary.critical_issues}")
        if summary.error_issues > 0:
            print(f"   🟠 Error: {summary.error_issues}")

    # Category breakdown
    if verbose:
        print(f"\n📂 Results by Category:")
        categories = {}
        for result in summary.results:
            category = result.category.value
            if category not in categories:
                categories[category] = {'pass': 0, 'fail': 0, 'warning': 0}
            categories[category][result.status.lower()] += 1

        for category, counts in categories.items():
            total = sum(counts.values())
            print(f"   {category}: {counts['pass']}/{total} passed")

    # Detailed results
    if verbose or not summary.is_compliant:
        print(f"\n📋 Detailed Results:")
        for result in summary.results:
            status_icon = "✅" if result.status == "PASS" else "❌" if result.status == "FAIL" else "⚠️"
            severity_icon = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🟢"}.get(result.severity.value, "")

            print(f"   {status_icon} {severity_icon} {result.check_name}")
            print(f"      Category: {result.category.value}")
            print(f"      Message: {result.message}")

            if result.affected_records > 0:
                print(f"      Affected Records: {result.affected_records}")

            if result.resolution_guidance:
                print(f"      Resolution: {result.resolution_guidance}")

            if verbose and result.details:
                print(f"      Details: {json.dumps(result.details, indent=8, default=str)}")

            print()


def save_validation_report(summary, report_path: Path) -> None:
    """Save detailed validation report to JSON file."""
    report_data = {
        'validation_summary': {
            'timestamp': summary.validation_timestamp.isoformat(),
            'total_checks': summary.total_checks,
            'passed_checks': summary.passed_checks,
            'failed_checks': summary.failed_checks,
            'warning_checks': summary.warning_checks,
            'critical_issues': summary.critical_issues,
            'error_issues': summary.error_issues,
            'success_rate': summary.success_rate,
            'is_compliant': summary.is_compliant,
            'total_execution_time': summary.total_execution_time
        },
        'validation_results': [result.to_dict() for result in summary.results],
        'metadata': {
            'generated_by': 'orchestrator_dbt_validation_suite',
            'story': 'S031-03-event-generation-performance',
            'purpose': 'financial_precision_and_audit_trail_validation'
        }
    }

    with open(report_path, 'w') as f:
        json.dump(report_data, f, indent=2, default=str)

    print(f"📄 Detailed report saved to: {report_path}")


def run_quick_validation(database_manager: DatabaseManager, year: Optional[int]) -> bool:
    """Run quick financial precision validation."""
    print("🏃‍♂️ Running quick financial precision validation...")

    try:
        result = validate_financial_precision_quick(database_manager, year)

        print(f"\n✅ Quick Validation Results:")
        print(f"   Compliant: {result['is_compliant']}")
        print(f"   Success Rate: {result['success_rate']:.1f}%")
        print(f"   Critical Issues: {result['critical_issues']}")
        print(f"   Error Issues: {result['error_issues']}")

        if not result['is_compliant']:
            print(f"\n❌ Issues found:")
            for check_result in result['results']:
                if check_result['status'] != 'PASS':
                    print(f"   • {check_result['check_name']}: {check_result['message']}")

        return result['is_compliant']

    except Exception as e:
        print(f"❌ Quick validation failed: {str(e)}")
        return False


def main():
    """Main validation CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Run comprehensive financial audit validation for orchestrator_dbt',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Run all validation checks
  %(prog)s --year 2025                       # Validate specific year
  %(prog)s --scope financial_precision       # Run only financial checks
  %(prog)s --quick                           # Quick validation
  %(prog)s --verbose --report report.json   # Detailed reporting
        """
    )

    parser.add_argument(
        '--year',
        type=int,
        help='Specific simulation year to validate (default: all years)'
    )

    parser.add_argument(
        '--scope',
        type=str,
        help='Comma-separated list of validation scopes (financial_precision, audit_trail, event_sourcing, data_consistency, business_rules, performance, regulatory_compliance)'
    )

    parser.add_argument(
        '--quick',
        action='store_true',
        help='Run quick financial precision validation only'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output with detailed results'
    )

    parser.add_argument(
        '--report',
        type=Path,
        help='Save detailed validation report to JSON file'
    )

    parser.add_argument(
        '--config',
        type=Path,
        help='Path to custom configuration file'
    )

    args = parser.parse_args()

    # Set up logging
    setup_logging(args.verbose)

    print("🔍 Starting Financial Audit Validation Suite")
    print(f"📅 Story: S031-03 Event Generation Performance")
    print(f"🎯 Purpose: Validate financial precision and audit trail compliance")

    try:
        # Load configuration
        if args.config:
            config = OrchestrationConfig(args.config)
            print(f"📁 Using custom config: {args.config}")
        else:
            config = OrchestrationConfig()
            print(f"📁 Using default configuration")

        # Initialize database manager
        database_manager = DatabaseManager(config)
        print(f"🗄️ Connected to database: {config.database.path}")

        # Run quick validation if requested
        if args.quick:
            is_compliant = run_quick_validation(database_manager, args.year)
            sys.exit(0 if is_compliant else 1)

        # Parse validation scope
        validation_scope = parse_validation_scope(args.scope)
        if validation_scope:
            scope_names = [cat.value for cat in validation_scope]
            print(f"🎯 Validation scope: {', '.join(scope_names)}")
        else:
            print(f"🎯 Validation scope: ALL categories")

        # Create validator
        validator = create_financial_audit_validator(database_manager, config)

        # Run comprehensive validation
        print(f"\n🚀 Running comprehensive validation...")
        if args.year:
            print(f"📅 Target year: {args.year}")

        summary = validator.run_comprehensive_validation(
            simulation_year=args.year,
            validation_scope=validation_scope
        )

        # Print results
        print_validation_summary(summary, args.verbose)

        # Save report if requested
        if args.report:
            save_validation_report(summary, args.report)

        # Exit with appropriate code
        if summary.is_compliant:
            print(f"\n🎉 Validation completed successfully - system is compliant!")
            sys.exit(0)
        else:
            print(f"\n⚠️ Validation completed with issues - review results above")
            sys.exit(1)

    except KeyboardInterrupt:
        print(f"\n⏹️ Validation interrupted by user")
        sys.exit(130)

    except Exception as e:
        print(f"\n💥 Validation failed with error: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
