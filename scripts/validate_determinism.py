#!/usr/bin/env python3
"""
CI/CD Integration Script for Epic E067 Determinism Validation

This script can be integrated into CI/CD pipelines to automatically validate
that multi-threading determinism is maintained across code changes.

Exit codes:
- 0: All determinism tests passed
- 1: Determinism tests failed
- 2: Test execution error
"""

import subprocess
import sys
from pathlib import Path


def run_determinism_tests() -> int:
    """Run determinism validation tests and return appropriate exit code."""

    print("🔐 Running Epic E067 Determinism Validation for CI/CD")
    print("=" * 60)

    project_root = Path(__file__).parent.parent

    tests = [
        ("Component Determinism", project_root / "test_determinism_fix.py"),
        ("Threading Determinism", project_root / "test_threading_determinism.py")
    ]

    passed_tests = 0
    total_tests = len(tests)

    for test_name, test_script in tests:
        print(f"🧪 Running {test_name}...")

        try:
            result = subprocess.run(
                [sys.executable, str(test_script)],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=60  # 1 minute timeout per test
            )

            if result.returncode == 0:
                passed_tests += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
                print("STDOUT:", result.stdout[-500:] if result.stdout else "No output")
                print("STDERR:", result.stderr[-500:] if result.stderr else "No errors")

        except subprocess.TimeoutExpired:
            print(f"⏰ {test_name}: TIMEOUT (>60 seconds)")
        except Exception as e:
            print(f"💥 {test_name}: ERROR - {e}")

    # Summary
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed_tests}/{total_tests} passed")

    if passed_tests == total_tests:
        print("🎯 DETERMINISM VALIDATION: PASSED")
        print("✅ Multi-threading determinism is maintained")
        print("🚀 Safe to deploy to production")
        return 0
    else:
        print("🎯 DETERMINISM VALIDATION: FAILED")
        print("❌ Multi-threading determinism issues detected")
        print("⚠️ DO NOT deploy until issues are resolved")
        return 1


def main():
    """Main entry point for CI/CD integration."""
    try:
        return run_determinism_tests()
    except Exception as e:
        print(f"💥 CRITICAL ERROR in determinism validation: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
