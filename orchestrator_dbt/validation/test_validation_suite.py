#!/usr/bin/env python3
"""
Integration tests for the comprehensive validation suite.

Tests ensure the financial audit validation system correctly identifies
issues in the migrated event generation system and validates compliance
with financial precision and audit trail requirements.

Test Coverage:
- Financial precision validation accuracy
- Audit trail completeness detection
- Event sourcing integrity checks
- Data consistency validation
- Performance requirement validation
- End-to-end validation workflow

Integration with Story S031-03:
- Validates that the validation suite can detect issues in migrated system
- Ensures validation suite maintains same standards as MVP system
- Tests performance impact of validation on large datasets
- Verifies regulatory compliance reporting accuracy
"""

import unittest
import time
import tempfile
import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock

# Test imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from orchestrator_dbt.validation import (
    FinancialAuditValidator,
    ValidationResult,
    ValidationSummary,
    ValidationSeverity,
    ValidationCategory,
    create_financial_audit_validator,
    validate_financial_precision_quick
)
from orchestrator_dbt.core.database_manager import DatabaseManager
from orchestrator_dbt.core.config import OrchestrationConfig


class MockDatabaseManager:
    """Mock database manager for testing validation logic."""

    def __init__(self, test_data: Dict[str, Any] = None):
        self.test_data = test_data or {}
        self.query_history = []

    def get_connection(self):
        return MockConnection(self.test_data, self.query_history)


class MockConnection:
    """Mock database connection for testing."""

    def __init__(self, test_data: Dict[str, Any], query_history: List[str]):
        self.test_data = test_data
        self.query_history = query_history

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, query: str, params: List[Any] = None):
        self.query_history.append((query, params))
        return MockQueryResult(self.test_data.get('query_results', {}))


class MockQueryResult:
    """Mock query result for testing."""

    def __init__(self, results: Dict[str, Any]):
        self.results = results

    def fetchone(self):
        return self.results.get('fetchone', None)

    def fetchall(self):
        return self.results.get('fetchall', [])

    def df(self):
        import pandas as pd
        return self.results.get('df', pd.DataFrame())


class TestFinancialAuditValidator(unittest.TestCase):
    """Test cases for FinancialAuditValidator."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_config = Mock(spec=OrchestrationConfig)
        self.mock_db_manager = MockDatabaseManager()

        self.validator = FinancialAuditValidator(
            database_manager=self.mock_db_manager,
            config=self.mock_config,
            precision_decimals=6,
            enable_performance_monitoring=True
        )

    def test_validator_initialization(self):
        """Test validator initializes correctly."""
        self.assertEqual(self.validator.precision_decimals, 6)
        self.assertTrue(self.validator.enable_performance_monitoring)
        self.assertEqual(len(self.validator.validation_results), 0)
        self.assertIsNone(self.validator.validation_summary)

    def test_compensation_precision_validation_pass(self):
        """Test compensation precision validation passes with correct data."""
        # Mock data with proper precision
        self.mock_db_manager.test_data = {
            'query_results': {
                'fetchone': (0, 0, 0, 0)  # No violations
            }
        }

        self.validator._check_compensation_precision_in_events(2025)

        # Should have one passing result
        self.assertEqual(len(self.validator.validation_results), 1)
        result = self.validator.validation_results[0]
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.category, ValidationCategory.FINANCIAL_PRECISION)
        self.assertEqual(result.severity, ValidationSeverity.INFO)

    def test_compensation_precision_validation_fail(self):
        """Test compensation precision validation fails with improper precision."""
        # Mock data with precision violations
        self.mock_db_manager.test_data = {
            'query_results': {
                'fetchone': (5, 3, 8, 7)  # 5 violations, 3 employees, max 8 decimals, max 7 prev decimals
            }
        }

        self.validator._check_compensation_precision_in_events(2025)

        # Should have one failing result
        self.assertEqual(len(self.validator.validation_results), 1)
        result = self.validator.validation_results[0]
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.category, ValidationCategory.FINANCIAL_PRECISION)
        self.assertEqual(result.severity, ValidationSeverity.ERROR)
        self.assertEqual(result.affected_records, 5)
        self.assertIn("precision violations", result.message.lower())

    def test_compensation_calculation_consistency_pass(self):
        """Test compensation calculation consistency validation passes."""
        import pandas as pd

        # Mock empty DataFrame (no inconsistencies)
        self.mock_db_manager.test_data = {
            'query_results': {
                'df': pd.DataFrame()  # Empty = no inconsistencies
            }
        }

        self.validator._check_compensation_calculation_consistency(2025)

        result = self.validator.validation_results[0]
        self.assertEqual(result.status, "PASS")
        self.assertIn("consistent", result.message.lower())

    def test_compensation_calculation_consistency_fail(self):
        """Test compensation calculation consistency validation fails."""
        import pandas as pd

        # Mock DataFrame with inconsistencies
        inconsistent_data = pd.DataFrame({
            'employee_id': ['EMP_2025_000001', 'EMP_2025_000002'],
            'simulation_year': [2025, 2025],
            'final_compensation_from_events': [75000.123456, 80000.654321],
            'final_compensation_from_snapshot': [75000.123457, 80000.654322],
            'compensation_difference': [0.000001, 0.000001]
        })

        self.mock_db_manager.test_data = {
            'query_results': {
                'df': inconsistent_data
            }
        }

        self.validator._check_compensation_calculation_consistency(2025)

        result = self.validator.validation_results[0]
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.affected_records, 2)
        self.assertIn("inconsistencies", result.message.lower())

    def test_proration_accuracy_validation(self):
        """Test proration accuracy validation."""
        # Mock proration analysis results
        self.mock_db_manager.test_data = {
            'query_results': {
                'fetchone': (100, 80, 5, 0.02)  # 100 total, 80 with proration, 5 violations, avg error 0.02
            }
        }

        self.validator._check_proration_accuracy(2025)

        result = self.validator.validation_results[0]
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.severity, ValidationSeverity.WARNING)
        self.assertEqual(result.affected_records, 5)
        self.assertIn("proration accuracy issues", result.message.lower())

    def test_cumulative_compensation_accuracy(self):
        """Test cumulative compensation accuracy validation."""
        # Mock cumulative compensation analysis
        self.mock_db_manager.test_data = {
            'query_results': {
                'fetchone': (250, 10, 150, 8)  # 250 transitions, 10 broken, 150 employees, 8 affected
            }
        }

        self.validator._check_cumulative_compensation_accuracy(2025)

        result = self.validator.validation_results[0]
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.severity, ValidationSeverity.ERROR)
        self.assertEqual(result.affected_records, 10)
        self.assertIn("chain integrity violated", result.message.lower())

    def test_audit_field_completeness_pass(self):
        """Test audit field completeness validation passes."""
        # Mock complete audit data
        self.mock_db_manager.test_data = {
            'query_results': {
                'fetchone': (1000, 0, 0, 0, 0, 0, 0)  # 1000 events, no missing fields
            }
        }

        self.validator._check_audit_field_completeness(2025)

        result = self.validator.validation_results[0]
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.category, ValidationCategory.AUDIT_TRAIL)
        self.assertIn("complete", result.message.lower())

    def test_audit_field_completeness_fail(self):
        """Test audit field completeness validation fails."""
        # Mock incomplete audit data
        self.mock_db_manager.test_data = {
            'query_results': {
                'fetchone': (1000, 5, 0, 10, 2, 0, 8)  # Missing values in various fields
            }
        }

        self.validator._check_audit_field_completeness(2025)

        result = self.validator.validation_results[0]
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.severity, ValidationSeverity.CRITICAL)
        self.assertEqual(result.affected_records, 25)  # Sum of all missing values
        self.assertIn("missing", result.message.lower())

    def test_comprehensive_validation_execution(self):
        """Test comprehensive validation executes all categories."""
        # Mock minimal passing data for all checks
        self.mock_db_manager.test_data = {
            'query_results': {
                'fetchone': (0, 0, 0, 0),  # Default to no issues
                'df': __import__('pandas').DataFrame()  # Empty DataFrame
            }
        }

        summary = self.validator.run_comprehensive_validation(simulation_year=2025)

        # Should have results from multiple categories
        self.assertIsInstance(summary, ValidationSummary)
        self.assertGreater(summary.total_checks, 0)
        self.assertGreater(len(self.validator.validation_results), 0)

        # Check that different categories are represented
        categories_found = set(result.category for result in self.validator.validation_results)
        self.assertIn(ValidationCategory.FINANCIAL_PRECISION, categories_found)
        self.assertIn(ValidationCategory.AUDIT_TRAIL, categories_found)

    def test_validation_scope_filtering(self):
        """Test validation scope filtering works correctly."""
        # Mock minimal data
        self.mock_db_manager.test_data = {
            'query_results': {
                'fetchone': (0, 0, 0, 0),
                'df': __import__('pandas').DataFrame()
            }
        }

        # Run validation with limited scope
        summary = self.validator.run_comprehensive_validation(
            simulation_year=2025,
            validation_scope=[ValidationCategory.FINANCIAL_PRECISION]
        )

        # Should only have financial precision results
        categories_found = set(result.category for result in self.validator.validation_results)
        self.assertEqual(categories_found, {ValidationCategory.FINANCIAL_PRECISION})

    def test_validation_result_structure(self):
        """Test validation result structure is correct."""
        self.validator._add_validation_result(
            check_name="test_check",
            category=ValidationCategory.FINANCIAL_PRECISION,
            severity=ValidationSeverity.ERROR,
            status="FAIL",
            message="Test message",
            details={"test_key": "test_value"},
            affected_records=5,
            resolution_guidance="Test guidance"
        )

        result = self.validator.validation_results[0]

        self.assertEqual(result.check_name, "test_check")
        self.assertEqual(result.category, ValidationCategory.FINANCIAL_PRECISION)
        self.assertEqual(result.severity, ValidationSeverity.ERROR)
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.message, "Test message")
        self.assertEqual(result.details["test_key"], "test_value")
        self.assertEqual(result.affected_records, 5)
        self.assertEqual(result.resolution_guidance, "Test guidance")

    def test_validation_summary_generation(self):
        """Test validation summary is generated correctly."""
        # Add various types of results
        self.validator._add_validation_result(
            "pass_check", ValidationCategory.FINANCIAL_PRECISION,
            ValidationSeverity.INFO, "PASS", "Passed"
        )
        self.validator._add_validation_result(
            "fail_check", ValidationCategory.AUDIT_TRAIL,
            ValidationSeverity.ERROR, "FAIL", "Failed"
        )
        self.validator._add_validation_result(
            "warning_check", ValidationCategory.DATA_CONSISTENCY,
            ValidationSeverity.WARNING, "WARNING", "Warning"
        )
        self.validator._add_validation_result(
            "critical_check", ValidationCategory.EVENT_SOURCING,
            ValidationSeverity.CRITICAL, "FAIL", "Critical"
        )

        summary = self.validator._generate_validation_summary(1.5)

        self.assertEqual(summary.total_checks, 4)
        self.assertEqual(summary.passed_checks, 1)
        self.assertEqual(summary.failed_checks, 2)
        self.assertEqual(summary.warning_checks, 1)
        self.assertEqual(summary.critical_issues, 1)
        self.assertEqual(summary.error_issues, 1)
        self.assertEqual(summary.success_rate, 25.0)  # 1/4 = 25%
        self.assertFalse(summary.is_compliant)  # Has critical and error issues
        self.assertEqual(summary.total_execution_time, 1.5)


class TestValidationUtilities(unittest.TestCase):
    """Test cases for validation utility functions."""

    def test_create_financial_audit_validator(self):
        """Test validator factory function."""
        mock_db_manager = Mock(spec=DatabaseManager)
        mock_config = Mock(spec=OrchestrationConfig)

        validator = create_financial_audit_validator(
            database_manager=mock_db_manager,
            config=mock_config,
            precision_decimals=4
        )

        self.assertIsInstance(validator, FinancialAuditValidator)
        self.assertEqual(validator.precision_decimals, 4)
        self.assertTrue(validator.enable_performance_monitoring)

    def test_quick_validation_function(self):
        """Test quick validation utility function."""
        mock_db_manager = MockDatabaseManager({
            'query_results': {
                'fetchone': (0, 0, 0, 0)  # No precision violations
            }
        })

        result = validate_financial_precision_quick(mock_db_manager, 2025)

        self.assertIsInstance(result, dict)
        self.assertIn('is_compliant', result)
        self.assertIn('success_rate', result)
        self.assertIn('critical_issues', result)
        self.assertIn('error_issues', result)
        self.assertIn('results', result)

    def test_validation_result_to_dict(self):
        """Test validation result serialization."""
        result = ValidationResult(
            check_name="test_check",
            category=ValidationCategory.FINANCIAL_PRECISION,
            severity=ValidationSeverity.ERROR,
            status="FAIL",
            message="Test message",
            details={"key": "value"},
            affected_records=10,
            resolution_guidance="Test guidance"
        )

        result_dict = result.to_dict()

        self.assertEqual(result_dict['check_name'], "test_check")
        self.assertEqual(result_dict['category'], "financial_precision")
        self.assertEqual(result_dict['severity'], "error")
        self.assertEqual(result_dict['status'], "FAIL")
        self.assertEqual(result_dict['message'], "Test message")
        self.assertEqual(result_dict['details']['key'], "value")
        self.assertEqual(result_dict['affected_records'], 10)
        self.assertEqual(result_dict['resolution_guidance'], "Test guidance")


class TestValidationIntegration(unittest.TestCase):
    """Integration tests for validation suite."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_validation_report_generation(self):
        """Test validation report can be generated and saved."""
        # Create validator with mock data
        mock_db_manager = MockDatabaseManager({
            'query_results': {
                'fetchone': (0, 0, 0, 0),
                'df': __import__('pandas').DataFrame()
            }
        })

        validator = FinancialAuditValidator(
            database_manager=mock_db_manager,
            config=Mock(spec=OrchestrationConfig),
            precision_decimals=6
        )

        # Run validation
        summary = validator.run_comprehensive_validation(
            simulation_year=2025,
            validation_scope=[ValidationCategory.FINANCIAL_PRECISION]
        )

        # Generate report
        report_path = self.temp_path / "test_report.json"

        report_data = {
            'validation_summary': {
                'timestamp': summary.validation_timestamp.isoformat(),
                'total_checks': summary.total_checks,
                'success_rate': summary.success_rate,
                'is_compliant': summary.is_compliant
            },
            'validation_results': [result.to_dict() for result in summary.results]
        }

        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=2)

        # Verify report was created and is valid JSON
        self.assertTrue(report_path.exists())

        with open(report_path, 'r') as f:
            loaded_data = json.load(f)

        self.assertIn('validation_summary', loaded_data)
        self.assertIn('validation_results', loaded_data)
        self.assertEqual(loaded_data['validation_summary']['total_checks'], summary.total_checks)

    def test_performance_metrics_tracking(self):
        """Test performance metrics are tracked correctly."""
        mock_db_manager = MockDatabaseManager({
            'query_results': {
                'fetchone': (0, 0, 0, 0),
                'df': __import__('pandas').DataFrame()
            }
        })

        validator = FinancialAuditValidator(
            database_manager=mock_db_manager,
            config=Mock(spec=OrchestrationConfig),
            enable_performance_monitoring=True
        )

        start_time = time.time()
        summary = validator.run_comprehensive_validation(simulation_year=2025)
        end_time = time.time()

        # Verify performance metrics
        self.assertGreater(summary.total_execution_time, 0)
        self.assertLess(summary.total_execution_time, end_time - start_time + 0.1)  # Some tolerance

        # Check performance metrics dictionary
        self.assertIn('validation_start_time', validator.performance_metrics)
        self.assertIn('check_execution_times', validator.performance_metrics)


class TestValidationCLI(unittest.TestCase):
    """Test cases for validation CLI functionality."""

    @patch('orchestrator_dbt.validation.run_validation.DatabaseManager')
    @patch('orchestrator_dbt.validation.run_validation.OrchestrationConfig')
    def test_cli_imports_correctly(self, mock_config, mock_db_manager):
        """Test CLI script imports work correctly."""
        try:
            from orchestrator_dbt.validation.run_validation import (
                setup_logging,
                parse_validation_scope,
                run_quick_validation
            )
            self.assertTrue(True)  # Import successful
        except ImportError as e:
            self.fail(f"CLI import failed: {str(e)}")

    def test_scope_parsing(self):
        """Test validation scope parsing."""
        from orchestrator_dbt.validation.run_validation import parse_validation_scope

        # Test single scope
        result = parse_validation_scope("financial_precision")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ValidationCategory.FINANCIAL_PRECISION)

        # Test multiple scopes
        result = parse_validation_scope("financial_precision,audit_trail")
        self.assertEqual(len(result), 2)
        self.assertIn(ValidationCategory.FINANCIAL_PRECISION, result)
        self.assertIn(ValidationCategory.AUDIT_TRAIL, result)

        # Test None input
        result = parse_validation_scope(None)
        self.assertIsNone(result)


def run_test_suite():
    """Run the complete validation test suite."""
    print("🧪 Running Financial Audit Validation Test Suite")
    print("="*60)

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestFinancialAuditValidator))
    suite.addTests(loader.loadTestsFromTestCase(TestValidationUtilities))
    suite.addTests(loader.loadTestsFromTestCase(TestValidationIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestValidationCLI))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*60)
    print(f"🧪 Test Summary:")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    print(f"   Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")

    if result.wasSuccessful():
        print("✅ All tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        return False


if __name__ == '__main__':
    success = run_test_suite()
    exit(0 if success else 1)
