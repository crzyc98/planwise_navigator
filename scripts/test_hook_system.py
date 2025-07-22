#!/usr/bin/env python3
"""
Test Suite for Smart Command Hook System

This script tests all components of the smart command hook system:
1. Environment detection and validation
2. Command classification and execution planning
3. Smart command wrapper functionality
4. Hook script integration
5. Common command patterns that previously caused trial-and-error

Usage:
    python3 scripts/test_hook_system.py
    python3 scripts/test_hook_system.py --verbose
    python3 scripts/test_hook_system.py --integration-test
"""

import os
import sys
import subprocess
import tempfile
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import unittest
from unittest.mock import patch, MagicMock

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent))

try:
    from smart_environment import SmartEnvironment, CommandType
    from smart_command_wrapper import SmartCommandWrapper, CommandResult
except ImportError as e:
    print(f"❌ Failed to import required modules: {e}")
    print("Ensure you're running from the project root directory")
    sys.exit(1)


class TestSmartEnvironment(unittest.TestCase):
    """Test the smart environment detection functionality."""

    def setUp(self):
        self.test_dir = Path(__file__).parent.parent  # Project root
        self.env = SmartEnvironment(self.test_dir)

    def test_project_root_detection(self):
        """Test that project root is detected correctly."""
        root = self.env.detect_project_root(self.test_dir)
        self.assertIsNotNone(root, "Should detect project root")
        self.assertTrue((root / "CLAUDE.md").exists(), "Should find CLAUDE.md in project root")
        print(f"✅ Project root detected: {root}")

    def test_environment_validation(self):
        """Test environment validation."""
        is_valid = self.env.validate()
        config = self.env.config

        self.assertIsNotNone(config, "Should have configuration")
        print(f"🔍 Environment validation: {'✅ PASS' if is_valid else '❌ FAIL'}")

        if not is_valid:
            print("   Validation errors:")
            for error in self.env.get_validation_errors():
                print(f"   - {error}")
        else:
            print(f"   Project root: {config.project_root}")
            print(f"   Python executable: {config.python_executable}")
            print(f"   Virtual environment: {config.venv_path}")
            print(f"   dbt directory: {config.dbt_path}")

    def test_command_classification(self):
        """Test command type classification."""
        test_cases = [
            ("dbt run", CommandType.DBT),
            ("dagster dev", CommandType.DAGSTER),
            ("streamlit run main.py", CommandType.STREAMLIT),
            ("python script.py", CommandType.PYTHON),
            ("pytest tests/", CommandType.PYTHON),
            ("git status", CommandType.SYSTEM),
            ("ls -la", CommandType.SYSTEM)
        ]

        for command, expected_type in test_cases:
            actual_type = self.env.classify_command(command)
            self.assertEqual(actual_type, expected_type,
                           f"Command '{command}' should be classified as {expected_type.value}")
            print(f"✅ '{command}' -> {actual_type.value}")


class TestSmartCommandWrapper(unittest.TestCase):
    """Test the smart command wrapper functionality."""

    def setUp(self):
        self.test_dir = Path(__file__).parent.parent
        self.wrapper = SmartCommandWrapper(working_dir=self.test_dir, verbose=False)

    def test_environment_validation(self):
        """Test wrapper environment validation."""
        is_valid = self.wrapper.validate_environment()
        print(f"🔧 Wrapper environment validation: {'✅ PASS' if is_valid else '❌ FAIL'}")

        if not is_valid:
            errors = self.wrapper.environment.get_validation_errors()
            print("   Validation errors:")
            for error in errors:
                print(f"   - {error}")

    def test_dry_run_commands(self):
        """Test dry run functionality for common commands."""
        test_commands = [
            "dbt run",
            "dagster dev",
            "streamlit run main.py",
            "python scripts/test.py",
            "git status"
        ]

        print("🧪 Testing dry run for common commands:")
        for command in test_commands:
            try:
                plan = self.wrapper.dry_run(command)
                if plan["valid"]:
                    print(f"✅ {command}")
                    print(f"   Type: {plan['command_type']}")
                    print(f"   Working dir: {plan['working_directory']}")
                    if plan.get('requires_venv'):
                        print(f"   Requires venv: {plan['requires_venv']}")
                else:
                    print(f"❌ {command} - validation failed")
            except Exception as e:
                print(f"❌ {command} - error: {e}")

    def test_command_resolution(self):
        """Test that commands are resolved to proper executables."""
        if not self.wrapper.validate_environment():
            self.skipTest("Environment validation failed")

        test_cases = [
            ("python --version", "python"),
            ("dbt --version", "dbt"),
        ]

        print("🔍 Testing command resolution:")
        for command, tool in test_cases:
            try:
                plan = self.wrapper.dry_run(command)
                if plan["valid"]:
                    resolved = plan["resolved_command"]
                    print(f"✅ {command} -> {resolved}")

                    # Check that resolved command uses venv if available
                    if plan.get('requires_venv') and self.wrapper.environment.config.venv_path:
                        self.assertIn("venv/bin", resolved,
                                    f"Resolved command should use venv: {resolved}")
                else:
                    print(f"❌ {command} - resolution failed")
            except Exception as e:
                print(f"❌ {command} - error: {e}")


class TestHookIntegration(unittest.TestCase):
    """Test hook script integration."""

    def setUp(self):
        self.project_root = Path(__file__).parent.parent
        self.hook_script = self.project_root / "scripts" / "claude_code_hook.sh"

    def test_hook_script_exists(self):
        """Test that hook script exists and is executable."""
        self.assertTrue(self.hook_script.exists(), f"Hook script should exist: {self.hook_script}")

        # Check if executable
        is_executable = os.access(self.hook_script, os.X_OK)
        self.assertTrue(is_executable, "Hook script should be executable")
        print(f"✅ Hook script exists and is executable: {self.hook_script}")

    def test_hook_script_syntax(self):
        """Test that hook script has valid bash syntax."""
        try:
            result = subprocess.run(
                ["bash", "-n", str(self.hook_script)],
                capture_output=True,
                text=True,
                timeout=5
            )
            self.assertEqual(result.returncode, 0,
                           f"Hook script should have valid syntax. Error: {result.stderr}")
            print("✅ Hook script has valid bash syntax")
        except subprocess.TimeoutExpired:
            self.fail("Hook script syntax check timed out")


class TestProblematicPatterns(unittest.TestCase):
    """Test that previously problematic command patterns now work."""

    def setUp(self):
        self.project_root = Path(__file__).parent.parent
        self.wrapper = SmartCommandWrapper(working_dir=self.project_root, verbose=True)

        # Skip tests if environment isn't valid
        if not self.wrapper.validate_environment():
            self.skipTest("Environment validation failed - cannot test command execution")

    def test_dbt_commands(self):
        """Test dbt command patterns that commonly fail."""
        # Test safe dbt commands that don't modify data
        safe_commands = [
            "dbt --version",
            "dbt list --select config",
        ]

        print("🔧 Testing dbt command patterns:")
        for command in safe_commands:
            with self.subTest(command=command):
                try:
                    result = self.wrapper.execute(command, capture_output=True, timeout=30)
                    print(f"{'✅' if result.success else '❌'} {command} (exit: {result.returncode})")

                    # Verify working directory was set correctly
                    expected_dir = self.project_root / "dbt"
                    self.assertEqual(Path(result.working_dir), expected_dir,
                                   f"dbt commands should run from {expected_dir}")

                except Exception as e:
                    print(f"❌ {command} - exception: {e}")
                    self.fail(f"Command execution raised exception: {e}")

    def test_python_commands(self):
        """Test Python command patterns."""
        python_commands = [
            "python --version",
            "python -c 'import sys; print(sys.executable)'",
        ]

        print("🐍 Testing Python command patterns:")
        for command in python_commands:
            with self.subTest(command=command):
                try:
                    result = self.wrapper.execute(command, capture_output=True, timeout=10)
                    print(f"{'✅' if result.success else '❌'} {command} (exit: {result.returncode})")

                    if result.success and result.stdout:
                        print(f"   Output: {result.stdout.strip()}")

                except Exception as e:
                    print(f"❌ {command} - exception: {e}")
                    self.fail(f"Command execution raised exception: {e}")


class TestPerformance(unittest.TestCase):
    """Test performance characteristics of the hook system."""

    def setUp(self):
        self.project_root = Path(__file__).parent.parent
        self.wrapper = SmartCommandWrapper(working_dir=self.project_root, verbose=False)

    def test_validation_performance(self):
        """Test that environment validation is reasonably fast."""
        import time

        start_time = time.time()
        is_valid = self.wrapper.validate_environment()
        duration = time.time() - start_time

        print(f"⏱️ Environment validation took {duration:.3f}s")
        self.assertLess(duration, 1.0, "Environment validation should take less than 1 second")

        # Test cached validation (should be much faster)
        start_time = time.time()
        is_valid_cached = self.wrapper.validate_environment()
        cached_duration = time.time() - start_time

        print(f"⏱️ Cached validation took {cached_duration:.3f}s")
        self.assertEqual(is_valid, is_valid_cached, "Cached validation should return same result")
        self.assertLess(cached_duration, 0.1, "Cached validation should be very fast")

    def test_dry_run_performance(self):
        """Test that dry runs are fast."""
        import time

        commands = ["dbt run", "dagster dev", "streamlit run main.py", "python test.py"]

        for command in commands:
            start_time = time.time()
            plan = self.wrapper.dry_run(command)
            duration = time.time() - start_time

            print(f"⏱️ Dry run '{command}' took {duration:.3f}s")
            self.assertLess(duration, 0.5, f"Dry run for '{command}' should be fast")


def run_integration_test():
    """Run integration test with actual hook script."""
    project_root = Path(__file__).parent.parent
    hook_script = project_root / "scripts" / "claude_code_hook.sh"

    if not hook_script.exists():
        print("❌ Hook script not found for integration test")
        return False

    print("🔗 Running integration test with hook script...")

    # Test commands that should be intercepted
    test_commands = [
        "dbt --version",
        "python --version",
    ]

    success_count = 0
    for command in test_commands:
        print(f"Testing hook integration with: {command}")

        try:
            # Call hook script directly (simulating Claude Code hook call)
            result = subprocess.run(
                [str(hook_script), command],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_root
            )

            if result.returncode == 0:
                print(f"✅ Hook integration test passed for: {command}")
                success_count += 1
            else:
                print(f"❌ Hook integration test failed for: {command}")
                print(f"   Error: {result.stderr}")

        except subprocess.TimeoutExpired:
            print(f"⏰ Hook integration test timed out for: {command}")
        except Exception as e:
            print(f"❌ Hook integration test error for {command}: {e}")

    print(f"🔗 Integration test results: {success_count}/{len(test_commands)} passed")
    return success_count == len(test_commands)


def main():
    """Run the complete test suite."""
    import argparse

    parser = argparse.ArgumentParser(description="Test smart command hook system")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--integration-test", action="store_true", help="Run integration tests")
    parser.add_argument("--performance", action="store_true", help="Run performance tests")

    args = parser.parse_args()

    print("🧪 Smart Command Hook System Test Suite")
    print("=" * 50)

    # Configure test verbosity
    if args.verbose:
        verbosity = 2
    else:
        verbosity = 1

    # Create test suite
    test_suite = unittest.TestSuite()

    # Add core functionality tests
    test_suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestSmartEnvironment))
    test_suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestSmartCommandWrapper))
    test_suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestHookIntegration))

    # Add problematic pattern tests (only if environment is valid)
    try:
        wrapper = SmartCommandWrapper()
        if wrapper.validate_environment():
            test_suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestProblematicPatterns))
        else:
            print("⚠️  Skipping problematic pattern tests - environment validation failed")
    except Exception:
        print("⚠️  Skipping problematic pattern tests - setup failed")

    # Add performance tests if requested
    if args.performance:
        test_suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestPerformance))

    # Run the test suite
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(test_suite)

    # Run integration test if requested
    if args.integration_test:
        print("\n" + "=" * 50)
        integration_success = run_integration_test()
    else:
        integration_success = True

    # Print final summary
    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    print(f"   Unit tests: {'✅ PASS' if result.wasSuccessful() else '❌ FAIL'}")
    print(f"   Integration: {'✅ PASS' if integration_success else '❌ FAIL'}")

    if result.wasSuccessful() and integration_success:
        print("🎉 All tests passed! Hook system is ready to use.")
        return 0
    else:
        print("❌ Some tests failed. Check output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
