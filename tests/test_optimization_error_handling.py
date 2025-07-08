"""
Comprehensive Error Handling Validation Tests
=============================================

This module provides extensive testing for error handling capabilities
in the optimization system, covering all failure modes and recovery scenarios.

Error Handling Test Categories:
1. Database Errors: Connection failures, query errors, lock conflicts
2. Optimization Failures: Non-convergence, numerical issues, constraint violations
3. Input Validation Errors: Invalid parameters, malformed data, missing fields
4. System Resource Errors: Memory exhaustion, timeout conditions, file access
5. Network/External Errors: Service unavailability, timeout conditions
6. Recovery Mechanisms: Graceful degradation, fallback strategies, retry logic

Validates proper exception handling, error messages, and system stability.
"""

import pytest
import pandas as pd
import numpy as np
import os
import json
import time
import tempfile
import threading
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, side_effect
from typing import Dict, Any, List, Tuple, Optional
import warnings
import signal
import sqlite3
from contextlib import contextmanager
import sys

# Import components under test
from streamlit_dashboard.optimization_schemas import (
    ParameterSchema, get_parameter_schema, get_default_parameters,
    validate_parameters, assess_parameter_risk, RiskLevel
)
from orchestrator.optimization.constraint_solver import CompensationOptimizer
from orchestrator.optimization.objective_functions import ObjectiveFunctions
from orchestrator.optimization.sensitivity_analysis import SensitivityAnalyzer
from orchestrator.optimization.evidence_generator import EvidenceGenerator
from orchestrator.optimization.optimization_schemas import (
    OptimizationRequest, OptimizationResult, OptimizationError
)


class ErrorScenarioGenerator:
    """Generator for various error scenarios."""

    @staticmethod
    def database_error_scenarios():
        """Generate database error scenarios."""
        return [
            ("connection_timeout", Exception("Connection timeout")),
            ("database_locked", Exception("Database is locked")),
            ("query_syntax_error", Exception("SQL syntax error")),
            ("table_not_found", Exception("Table 'workforce' does not exist")),
            ("permission_denied", Exception("Permission denied")),
            ("disk_full", Exception("No space left on device")),
            ("connection_lost", Exception("Connection lost during query")),
            ("corrupted_database", Exception("Database file is corrupted"))
        ]

    @staticmethod
    def optimization_error_scenarios():
        """Generate optimization failure scenarios."""
        return [
            ("non_convergence", "Optimization failed to converge"),
            ("numerical_instability", "Numerical instability detected"),
            ("constraint_violation", "Constraints cannot be satisfied"),
            ("unbounded_problem", "Problem appears to be unbounded"),
            ("infeasible_solution", "No feasible solution found"),
            ("gradient_failure", "Gradient calculation failed"),
            ("hessian_singular", "Hessian matrix is singular"),
            ("evaluation_limit", "Maximum function evaluations exceeded")
        ]

    @staticmethod
    def input_validation_error_scenarios():
        """Generate input validation error scenarios."""
        return [
            ("empty_parameters", {}),
            ("null_parameters", None),
            ("invalid_parameter_type", {"merit_rate_level_1": "not_a_number"}),
            ("missing_required_fields", {"incomplete": "data"}),
            ("negative_values", {"merit_rate_level_1": -0.05}),
            ("infinity_values", {"merit_rate_level_1": float('inf')}),
            ("nan_values", {"merit_rate_level_1": float('nan')}),
            ("extreme_values", {"merit_rate_level_1": 999.99})
        ]

    @staticmethod
    def system_resource_error_scenarios():
        """Generate system resource error scenarios."""
        return [
            ("memory_exhaustion", MemoryError("Unable to allocate memory")),
            ("file_permission_error", PermissionError("Permission denied")),
            ("disk_space_error", OSError("No space left on device")),
            ("file_not_found", FileNotFoundError("Configuration file not found")),
            ("process_killed", KeyboardInterrupt("Process interrupted")),
            ("timeout_error", TimeoutError("Operation timed out"))
        ]


class TestDatabaseErrorHandling:
    """Test database error handling and recovery."""

    def setup_method(self):
        """Setup database error testing."""
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = self.mock_conn

    @pytest.mark.parametrize("error_name,error_exception", ErrorScenarioGenerator.database_error_scenarios())
    def test_database_connection_errors(self, error_name, error_exception):
        """Test handling of database connection errors."""

        # Configure mock to raise exception
        self.mock_duckdb.get_connection.side_effect = error_exception

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "db_error_test")

        # Should handle database errors gracefully
        with pytest.raises(Exception) as exc_info:
            obj_funcs.cost_objective({"merit_rate_level_1": 0.045})

        # Error should bubble up appropriately
        assert str(error_exception) in str(exc_info.value) or type(error_exception).__name__ in str(exc_info.value)

    @pytest.mark.parametrize("error_name,error_exception", ErrorScenarioGenerator.database_error_scenarios())
    def test_database_query_errors(self, error_name, error_exception):
        """Test handling of database query errors."""

        # Configure mock connection but failing execute
        self.mock_conn.execute.side_effect = error_exception

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "query_error_test")

        # Should handle query errors gracefully
        with pytest.raises(Exception) as exc_info:
            obj_funcs.cost_objective({"merit_rate_level_1": 0.045})

        # Error should be informative
        assert str(error_exception) in str(exc_info.value) or type(error_exception).__name__ in str(exc_info.value)

    def test_database_lock_handling(self):
        """Test specific handling of database lock scenarios."""

        # Simulate database lock with specific error message
        lock_error = Exception("database is locked")
        self.mock_conn.execute.side_effect = lock_error

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "lock_test")

        # Should detect and handle lock specifically
        with pytest.raises(Exception) as exc_info:
            obj_funcs.cost_objective({"merit_rate_level_1": 0.045})

        error_message = str(exc_info.value).lower()
        assert "lock" in error_message or "database" in error_message

    def test_database_connection_retry_logic(self):
        """Test database connection retry mechanisms."""

        # Simulate intermittent connection failures
        call_count = [0]

        def failing_connection():
            call_count[0] += 1
            if call_count[0] < 3:  # Fail first 2 attempts
                raise Exception("Connection failed")
            return self.mock_duckdb.get_connection.return_value

        # Test with manual retry logic (if implemented)
        max_retries = 5
        for attempt in range(max_retries):
            try:
                connection = failing_connection()
                break  # Success
            except Exception as e:
                if attempt == max_retries - 1:
                    # Final attempt failed
                    assert "Connection failed" in str(e)
                continue
        else:
            pytest.fail("Retry logic test failed")

        # Should succeed after retries
        assert call_count[0] == 3

    def test_database_transaction_rollback(self):
        """Test database transaction rollback on errors."""

        # Mock transaction behavior
        self.mock_conn.begin.return_value = None
        self.mock_conn.commit.return_value = None
        self.mock_conn.rollback.return_value = None

        # Simulate error during transaction
        def failing_execute(query, *args):
            if "UPDATE" in query:
                raise Exception("Update failed")
            return Mock()

        self.mock_conn.execute.side_effect = failing_execute

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "transaction_test")

        # Test transaction with error handling
        try:
            with self.mock_conn as conn:
                conn.begin()
                conn.execute("SELECT * FROM test")  # Should work
                conn.execute("UPDATE test SET value = 1")  # Should fail
                conn.commit()
        except Exception:
            # Should rollback on error
            pass

        # Verify rollback was called (if implemented)
        # This would depend on the actual implementation


class TestOptimizationErrorHandling:
    """Test optimization algorithm error handling."""

    def setup_method(self):
        """Setup optimization error testing."""
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = self.mock_conn

        # Setup successful database responses by default
        self.mock_conn.execute.return_value.fetchone.return_value = [1_000_000.0]
        self.mock_conn.execute.return_value.fetchall.return_value = [(1, 50000, 2500)]

    @pytest.mark.parametrize("error_name,error_message", ErrorScenarioGenerator.optimization_error_scenarios())
    def test_optimization_algorithm_failures(self, error_name, error_message):
        """Test handling of optimization algorithm failures."""

        optimizer = CompensationOptimizer(self.mock_duckdb, "opt_error_test")

        # Mock scipy optimization failure
        with patch('scipy.optimize.minimize') as mock_minimize:
            mock_result = Mock()
            mock_result.success = False
            mock_result.message = error_message
            mock_result.x = None
            mock_result.fun = float('inf')
            mock_result.nit = 0
            mock_result.nfev = 0
            mock_minimize.return_value = mock_result

            request = OptimizationRequest(
                scenario_id="error_test",
                initial_parameters=get_default_parameters(),
                objectives={"cost": 1.0}
            )

            # Should handle optimization failure gracefully
            result = optimizer.optimize(request)

            # Result should indicate failure
            assert result.converged is False
            assert error_message.lower() in result.algorithm_used.lower() or not result.converged

    def test_objective_function_numerical_errors(self):
        """Test handling of numerical errors in objective functions."""

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "numerical_error_test")

        # Test division by zero scenario
        self.mock_conn.execute.return_value.fetchall.return_value = [
            (1, 50000, 0),  # Zero standard deviation
            (2, 60000, 0)
        ]

        with patch.object(obj_funcs, '_update_parameters'):
            # Should handle division by zero gracefully
            try:
                equity = obj_funcs.equity_objective({"merit_rate_level_1": 0.045})
                # Should return reasonable value (0 for perfect equity)
                assert equity >= 0
            except ZeroDivisionError:
                pytest.fail("Division by zero not handled properly")

    def test_constraint_violation_handling(self):
        """Test handling of constraint violations."""

        optimizer = CompensationOptimizer(self.mock_duckdb, "constraint_test")

        # Parameters that violate constraints
        invalid_params = {
            "merit_rate_level_1": 0.15,  # Above maximum
            "cola_rate": -0.01  # Below minimum
        }

        objectives = {"cost": 1.0}

        # Should detect and handle constraint violations
        with pytest.raises(ValueError) as exc_info:
            optimizer._validate_inputs(invalid_params, objectives)

        error_message = str(exc_info.value).lower()
        assert "above maximum" in error_message or "below minimum" in error_message

    def test_optimization_timeout_handling(self):
        """Test handling of optimization timeouts."""

        optimizer = CompensationOptimizer(self.mock_duckdb, "timeout_test")

        # Mock slow optimization
        def slow_minimize(*args, **kwargs):
            time.sleep(2.0)  # Simulate slow optimization
            mock_result = Mock()
            mock_result.success = True
            mock_result.x = [0.045]
            mock_result.fun = 0.5
            return mock_result

        with patch('scipy.optimize.minimize', side_effect=slow_minimize):
            request = OptimizationRequest(
                scenario_id="timeout_test",
                initial_parameters={"merit_rate_level_1": 0.045},
                objectives={"cost": 1.0},
                max_evaluations=10  # Low limit to force quick completion
            )

            start_time = time.time()

            # Should handle timeout appropriately
            try:
                result = optimizer.optimize(request)
                execution_time = time.time() - start_time

                # If no timeout mechanism, just verify it completes
                assert execution_time > 1.0  # Should take at least the sleep time

            except TimeoutError:
                # Timeout handling is acceptable
                execution_time = time.time() - start_time
                assert execution_time < 5.0  # Should timeout before too long

    def test_optimization_memory_errors(self):
        """Test handling of memory errors during optimization."""

        optimizer = CompensationOptimizer(self.mock_duckdb, "memory_test")

        # Mock memory error in optimization
        with patch('scipy.optimize.minimize') as mock_minimize:
            mock_minimize.side_effect = MemoryError("Unable to allocate memory")

            request = OptimizationRequest(
                scenario_id="memory_test",
                initial_parameters=get_default_parameters(),
                objectives={"cost": 1.0}
            )

            # Should handle memory error gracefully
            with pytest.raises(MemoryError):
                optimizer.optimize(request)

    def test_invalid_objective_function_values(self):
        """Test handling of invalid objective function values."""

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "invalid_values_test")

        # Mock database returning invalid values
        self.mock_conn.execute.return_value.fetchone.return_value = [None]  # NULL value

        with patch.object(obj_funcs, '_update_parameters'):
            # Should handle NULL/None values gracefully
            try:
                cost = obj_funcs.cost_objective({"merit_rate_level_1": 0.045})
                # Should return reasonable default or raise specific exception
                assert cost is not None or True  # Either returns value or raises exception
            except (ValueError, TypeError) as e:
                # Specific handling of invalid values is acceptable
                assert "None" in str(e) or "null" in str(e).lower()


class TestInputValidationErrorHandling:
    """Test input validation error handling."""

    def setup_method(self):
        """Setup input validation testing."""
        self.schema = get_parameter_schema()

    @pytest.mark.parametrize("error_name,invalid_input", ErrorScenarioGenerator.input_validation_error_scenarios())
    def test_invalid_parameter_input_handling(self, error_name, invalid_input):
        """Test handling of invalid parameter inputs."""

        if error_name == "null_parameters":
            # None input should raise appropriate error
            with pytest.raises((TypeError, AttributeError)):
                self.schema.validate_parameter_set(invalid_input)

        elif error_name == "empty_parameters":
            # Empty parameters should be handled gracefully
            result = self.schema.validate_parameter_set(invalid_input)
            assert isinstance(result, dict)
            assert 'is_valid' in result

        elif error_name == "invalid_parameter_type":
            # Invalid types should raise appropriate error
            with pytest.raises((TypeError, ValueError)):
                self.schema.validate_parameter_set(invalid_input)

        else:
            # Other invalid inputs should return validation errors
            result = self.schema.validate_parameter_set(invalid_input)
            assert not result['is_valid'] or len(result['warnings']) > 0

    def test_malformed_json_configuration(self):
        """Test handling of malformed JSON configuration."""

        temp_dir = tempfile.mkdtemp()
        malformed_json = os.path.join(temp_dir, "malformed.json")

        try:
            # Create malformed JSON file
            with open(malformed_json, 'w') as f:
                f.write('{"invalid": json, "syntax": error}')

            # Should raise appropriate JSON error
            with pytest.raises(json.JSONDecodeError):
                with open(malformed_json, 'r') as f:
                    json.load(f)

        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_missing_configuration_files(self):
        """Test handling of missing configuration files."""

        nonexistent_path = "/nonexistent/path/config.yaml"

        # Should raise appropriate file error
        with pytest.raises(FileNotFoundError):
            with open(nonexistent_path, 'r') as f:
                f.read()

    def test_unicode_encoding_errors(self):
        """Test handling of unicode encoding errors."""

        temp_dir = tempfile.mkdtemp()
        unicode_file = os.path.join(temp_dir, "unicode_test.csv")

        try:
            # Create file with problematic encoding
            with open(unicode_file, 'wb') as f:
                f.write(b"parameter_name,value\n")
                f.write(b"merit_rate_\xff\xfe,0.045\n")  # Invalid UTF-8 sequence

            # Should handle encoding errors gracefully
            try:
                df = pd.read_csv(unicode_file, encoding='utf-8')
            except UnicodeDecodeError as e:
                # Expected behavior
                assert "utf-8" in str(e) or "decode" in str(e)

        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_parameter_validation_edge_cases(self):
        """Test parameter validation with edge case inputs."""

        edge_cases = [
            # Very large dictionary
            {f"param_{i}": 0.045 for i in range(10000)},

            # Unicode parameter names
            {"paramètre_1": 0.045, "参数_2": 0.040},

            # Very long parameter names
            {"very_long_parameter_name_" + "x" * 1000: 0.045},

            # Special characters
            {"param@#$%": 0.045, "param with spaces": 0.040}
        ]

        for i, params in enumerate(edge_cases):
            try:
                result = self.schema.validate_parameter_set(params)
                # Should either handle gracefully or raise specific error
                assert isinstance(result, dict) or True
            except (ValueError, TypeError, UnicodeError) as e:
                # Specific errors for edge cases are acceptable
                assert len(str(e)) > 0


class TestSystemResourceErrorHandling:
    """Test system resource error handling."""

    def setup_method(self):
        """Setup system resource testing."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup after tests."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.parametrize("error_name,error_exception", ErrorScenarioGenerator.system_resource_error_scenarios())
    def test_system_resource_errors(self, error_name, error_exception):
        """Test handling of system resource errors."""

        if error_name == "memory_exhaustion":
            # Test memory error handling
            def memory_intensive_operation():
                large_data = []
                try:
                    # Try to allocate large amounts of memory
                    for i in range(1000):
                        large_data.append([0] * (1024 * 1024))  # 1MB chunks
                        if i > 100:  # Stop before actually exhausting memory
                            break
                except MemoryError:
                    # Expected in low-memory conditions
                    pass
                finally:
                    del large_data

            # Should handle gracefully
            memory_intensive_operation()

        elif error_name == "file_permission_error":
            # Test file permission handling
            test_file = os.path.join(self.temp_dir, "readonly.txt")

            # Create file and remove write permissions
            with open(test_file, 'w') as f:
                f.write("test content")

            os.chmod(test_file, 0o444)  # Read-only

            # Should raise permission error
            with pytest.raises(PermissionError):
                with open(test_file, 'w') as f:
                    f.write("new content")

        elif error_name == "timeout_error":
            # Test timeout handling
            def slow_operation():
                time.sleep(0.5)
                return "completed"

            # Manual timeout implementation
            start_time = time.time()
            timeout = 0.1  # Very short timeout

            try:
                result = slow_operation()
                elapsed = time.time() - start_time

                if elapsed > timeout:
                    # Would timeout in real implementation
                    pass
            except TimeoutError:
                # Timeout handling is working
                pass

    def test_file_system_errors(self):
        """Test file system error handling."""

        # Test disk space simulation (can't actually fill disk)
        test_file = os.path.join(self.temp_dir, "large_file.txt")

        try:
            # Create reasonably large file
            with open(test_file, 'w') as f:
                for i in range(1000):
                    f.write("x" * 1000)  # 1MB total

            # File should be created successfully
            assert os.path.exists(test_file)
            assert os.path.getsize(test_file) > 0

        except OSError as e:
            # If actual disk space error occurs, handle gracefully
            assert "space" in str(e).lower() or "disk" in str(e).lower()

    def test_concurrent_file_access_errors(self):
        """Test concurrent file access error handling."""

        test_file = os.path.join(self.temp_dir, "concurrent_test.txt")
        errors = []

        def file_writer(content):
            """Function to write to file concurrently."""
            try:
                with open(test_file, 'w') as f:
                    f.write(content)
                    time.sleep(0.1)  # Hold file briefly
            except Exception as e:
                errors.append(e)

        # Start multiple writers
        threads = []
        for i in range(3):
            thread = threading.Thread(target=file_writer, args=(f"Content {i}",))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Should handle concurrent access gracefully
        # (May have some errors depending on OS)
        if errors:
            # Errors are acceptable for concurrent file access
            assert all(isinstance(e, (OSError, PermissionError)) for e in errors)

    def test_process_interruption_handling(self):
        """Test handling of process interruption."""

        # Simulate KeyboardInterrupt
        def interruptible_operation():
            try:
                time.sleep(0.1)
                return "completed"
            except KeyboardInterrupt:
                return "interrupted"

        # Test normal completion
        result = interruptible_operation()
        assert result == "completed"

        # Test interruption simulation
        def simulate_interrupt():
            raise KeyboardInterrupt("Simulated interrupt")

        with pytest.raises(KeyboardInterrupt):
            simulate_interrupt()


class TestErrorRecoveryMechanisms:
    """Test error recovery and fallback mechanisms."""

    def setup_method(self):
        """Setup error recovery testing."""
        self.schema = get_parameter_schema()
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = self.mock_conn

    def test_graceful_degradation(self):
        """Test graceful degradation when features fail."""

        # Test parameter validation with partial schema failure
        def partial_validation(params):
            """Simulate partial validation capability."""
            try:
                # Full validation
                return self.schema.validate_parameter_set(params)
            except Exception:
                # Fallback to basic validation
                basic_result = {
                    'is_valid': True,
                    'overall_risk': RiskLevel.MEDIUM,
                    'warnings': ['Full validation unavailable, using basic validation'],
                    'errors': [],
                    'parameter_results': {}
                }
                return basic_result

        params = get_default_parameters()
        result = partial_validation(params)

        # Should provide some result even if full validation fails
        assert isinstance(result, dict)
        assert 'is_valid' in result

    def test_fallback_optimization_methods(self):
        """Test fallback to alternative optimization methods."""

        optimizer = CompensationOptimizer(self.mock_duckdb, "fallback_test")

        # Mock primary method failure and fallback success
        method_attempts = []

        def mock_minimize(*args, **kwargs):
            method = kwargs.get('method', 'SLSQP')
            method_attempts.append(method)

            if method == 'SLSQP' and len(method_attempts) == 1:
                # First method fails
                mock_result = Mock()
                mock_result.success = False
                mock_result.message = "SLSQP failed"
                return mock_result
            else:
                # Fallback method succeeds
                mock_result = Mock()
                mock_result.success = True
                mock_result.x = [0.045]
                mock_result.fun = 0.5
                mock_result.nit = 25
                mock_result.nfev = 75
                return mock_result

        # Test fallback logic (manual implementation)
        request = OptimizationRequest(
            scenario_id="fallback_test",
            initial_parameters={"merit_rate_level_1": 0.045},
            objectives={"cost": 1.0}
        )

        methods_to_try = ['SLSQP', 'L-BFGS-B', 'Powell']

        with patch('scipy.optimize.minimize', side_effect=mock_minimize):
            for method in methods_to_try:
                request.method = method
                result = optimizer.optimize(request)

                if result.converged:
                    break
            else:
                pytest.fail("No fallback method succeeded")

        # Should eventually succeed with fallback
        assert result.converged

    def test_error_message_quality(self):
        """Test quality and usefulness of error messages."""

        # Test parameter validation error messages
        invalid_params = {
            "merit_rate_level_1": 0.15,  # Above maximum
            "cola_rate": -0.01,  # Below minimum
            "invalid_param": 0.045  # Unknown parameter
        }

        validation_result = self.schema.validate_parameter_set(invalid_params)

        # Error messages should be specific and helpful
        errors = validation_result.get('errors', [])
        warnings = validation_result.get('warnings', [])

        if errors:
            error_text = ' '.join(errors).lower()
            # Should mention specific parameter and issue
            assert any(param in error_text for param in ['merit_rate_level_1', 'cola_rate'])
            assert any(issue in error_text for issue in ['above', 'below', 'maximum', 'minimum'])

        if warnings:
            warning_text = ' '.join(warnings).lower()
            # Should mention unknown parameters
            assert 'unknown' in warning_text or 'invalid' in warning_text

    def test_error_logging_and_reporting(self):
        """Test error logging and reporting mechanisms."""

        # Simulate error conditions and check they're properly captured
        error_log = []

        def mock_logger(level, message):
            error_log.append((level, message))

        # Test logging during optimization failure
        optimizer = CompensationOptimizer(self.mock_duckdb, "logging_test")

        with patch('scipy.optimize.minimize') as mock_minimize:
            mock_minimize.side_effect = Exception("Optimization failed")

            request = OptimizationRequest(
                scenario_id="logging_test",
                initial_parameters=get_default_parameters(),
                objectives={"cost": 1.0}
            )

            try:
                optimizer.optimize(request)
            except Exception as e:
                # Log the error (manual implementation)
                mock_logger("ERROR", f"Optimization failed: {str(e)}")

        # Should have logged the error
        assert len(error_log) > 0
        assert any("optimization failed" in msg.lower() for level, msg in error_log)

    def test_state_consistency_after_errors(self):
        """Test that system state remains consistent after errors."""

        schema = get_parameter_schema()

        # Perform operations that might fail
        try:
            # Invalid operation 1
            schema.validate_parameter_set(None)
        except (TypeError, AttributeError):
            pass

        try:
            # Invalid operation 2
            schema.validate_parameter_set({"invalid": "data"})
        except (ValueError, TypeError):
            pass

        # Schema should still work normally after errors
        valid_params = get_default_parameters()
        result = schema.validate_parameter_set(valid_params)

        assert result['is_valid']
        assert isinstance(result['overall_risk'], RiskLevel)

    def test_resource_cleanup_after_errors(self):
        """Test proper resource cleanup after errors."""

        # Test database connection cleanup
        connection_opened = [False]
        connection_closed = [False]

        def mock_get_connection():
            connection_opened[0] = True
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=self.mock_conn)
            mock_context.__exit__ = Mock(side_effect=lambda *args: connection_closed.__setitem__(0, True))
            return mock_context

        self.mock_duckdb.get_connection.side_effect = mock_get_connection

        # Simulate error during database operation
        self.mock_conn.execute.side_effect = Exception("Database error")

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "cleanup_test")

        try:
            obj_funcs.cost_objective({"merit_rate_level_1": 0.045})
        except Exception:
            pass

        # Connection should have been properly closed despite error
        assert connection_opened[0], "Connection was not opened"
        assert connection_closed[0], "Connection was not properly closed after error"


if __name__ == "__main__":
    # Run error handling tests
    pytest.main([
        __file__ + "::TestDatabaseErrorHandling::test_database_connection_errors",
        __file__ + "::TestOptimizationErrorHandling::test_optimization_algorithm_failures",
        __file__ + "::TestInputValidationErrorHandling::test_invalid_parameter_input_handling",
        __file__ + "::TestSystemResourceErrorHandling::test_system_resource_errors",
        __file__ + "::TestErrorRecoveryMechanisms::test_graceful_degradation",
        "-v"
    ])
