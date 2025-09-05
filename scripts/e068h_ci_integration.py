#!/usr/bin/env python3
"""
E068H CI/CD Integration Script

Automated testing pipeline integration for E068H Scale & Parity Testing.
Provides CI/CD-friendly execution with proper exit codes, JSON reporting,
and integration with GitHub Actions, Jenkins, or other CI/CD systems.

This script orchestrates:
- Scale testing validation
- Parity testing validation
- Performance regression detection
- Comprehensive reporting for CI/CD systems
- Automated deployment readiness assessment

Usage in CI/CD pipelines:
- GitHub Actions: Uses JSON reports for step outputs
- Jenkins: Provides JUnit-compatible XML reports
- General CI: Standard exit codes and structured logging

Epic E068H: Production deployment validation automation.
"""

import os
import sys
import json
import time
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class E068HCIIntegration:
    """
    CI/CD integration orchestrator for E068H testing framework.

    Provides standardized testing pipeline with proper exit codes,
    structured reporting, and deployment readiness assessment.
    """

    def __init__(self, reports_dir: Path = Path("reports/ci_integration")):
        """
        Initialize CI/CD integration.

        Args:
            reports_dir: Directory for CI/CD reports
        """
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Configure logging for CI/CD
        self.logger = logging.getLogger("E068H_CI")
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

        # Test results storage
        self.test_results = {
            'scale_testing': None,
            'parity_testing': None,
            'overall_status': 'not_run'
        }

    def run_comprehensive_ci_validation(self,
                                      test_mode: str = "standard",
                                      timeout_minutes: int = 30) -> int:
        """
        Run comprehensive CI/CD validation pipeline.

        Args:
            test_mode: CI test mode ("quick", "standard", "comprehensive")
            timeout_minutes: Maximum execution time in minutes

        Returns:
            Exit code (0 = success, 1 = failure, 2 = timeout)
        """
        self.logger.info("="*60)
        self.logger.info("E068H CI/CD VALIDATION PIPELINE STARTING")
        self.logger.info("="*60)
        self.logger.info(f"Test mode: {test_mode}")
        self.logger.info(f"Timeout: {timeout_minutes} minutes")
        self.logger.info(f"Reports directory: {self.reports_dir}")

        start_time = time.time()
        timeout_seconds = timeout_minutes * 60

        try:
            # Step 1: Environment validation
            self.logger.info("\n--- STEP 1: ENVIRONMENT VALIDATION ---")
            env_status = self._validate_environment()
            if not env_status:
                self.logger.error("❌ Environment validation failed")
                return 1

            # Step 2: Scale testing
            self.logger.info("\n--- STEP 2: SCALE TESTING ---")
            scale_start = time.time()

            if time.time() - start_time > timeout_seconds:
                self.logger.error("⏰ Timeout before scale testing")
                return 2

            scale_status = self._run_scale_testing(test_mode)
            scale_time = time.time() - scale_start

            self.logger.info(f"Scale testing completed in {scale_time:.1f}s")

            if not scale_status:
                self.logger.error("❌ Scale testing failed")
                self._generate_ci_reports(failed_at="scale_testing")
                return 1

            # Step 3: Parity testing
            self.logger.info("\n--- STEP 3: PARITY TESTING ---")
            parity_start = time.time()

            if time.time() - start_time > timeout_seconds:
                self.logger.error("⏰ Timeout before parity testing")
                return 2

            parity_status = self._run_parity_testing(test_mode)
            parity_time = time.time() - parity_start

            self.logger.info(f"Parity testing completed in {parity_time:.1f}s")

            if not parity_status:
                self.logger.error("❌ Parity testing failed")
                self._generate_ci_reports(failed_at="parity_testing")
                return 1

            # Step 4: Final assessment
            self.logger.info("\n--- STEP 4: DEPLOYMENT READINESS ASSESSMENT ---")
            deployment_ready = self._assess_deployment_readiness()

            total_time = time.time() - start_time

            # Generate comprehensive reports
            self._generate_ci_reports()

            # Final status
            if deployment_ready:
                self.test_results['overall_status'] = 'passed'
                self.logger.info("="*60)
                self.logger.info("✅ E068H CI/CD VALIDATION PASSED")
                self.logger.info("="*60)
                self.logger.info(f"Total time: {total_time:.1f}s")
                self.logger.info("System is ready for production deployment")
                return 0
            else:
                self.test_results['overall_status'] = 'failed'
                self.logger.error("="*60)
                self.logger.error("❌ E068H CI/CD VALIDATION FAILED")
                self.logger.error("="*60)
                self.logger.error("System not ready for production deployment")
                return 1

        except Exception as e:
            self.test_results['overall_status'] = 'error'
            self.logger.error(f"❌ CI/CD validation error: {e}")
            self._generate_ci_reports(error=str(e))
            return 1

    def _validate_environment(self) -> bool:
        """Validate CI/CD environment and dependencies."""
        self.logger.info("Validating environment...")

        try:
            # Check Python version
            python_version = sys.version_info
            if python_version < (3, 11):
                self.logger.error(f"Python {python_version.major}.{python_version.minor} < 3.11 required")
                return False

            # Check project structure
            required_paths = [
                Path("config/simulation_config.yaml"),
                Path("dbt/dbt_project.yml"),
                Path("navigator_orchestrator/__init__.py"),
                Path("scripts/scale_testing_framework.py"),
                Path("scripts/parity_testing_framework.py")
            ]

            for path in required_paths:
                if not path.exists():
                    self.logger.error(f"Missing required file: {path}")
                    return False

            # Check database accessibility
            from navigator_orchestrator.config import get_database_path
            db_path = get_database_path()

            if not db_path.parent.exists():
                db_path.parent.mkdir(parents=True, exist_ok=True)

            # Test database connection
            import duckdb
            with duckdb.connect(str(db_path)) as conn:
                conn.execute("SELECT 1").fetchone()

            self.logger.info("✅ Environment validation passed")
            return True

        except Exception as e:
            self.logger.error(f"Environment validation failed: {e}")
            return False

    def _run_scale_testing(self, test_mode: str) -> bool:
        """Run scale testing via subprocess."""
        self.logger.info(f"Running scale testing in {test_mode} mode...")

        try:
            # Prepare scale testing command
            cmd = [
                sys.executable,
                "scripts/scale_testing_framework.py",
                "--reports-dir", str(self.reports_dir / "scale_testing")
            ]

            # Add mode-specific arguments
            if test_mode == "quick":
                cmd.append("--quick")
            elif test_mode == "comprehensive":
                cmd.extend(["--full", "--runs", "5"])
            else:  # standard
                cmd.extend(["--full", "--runs", "3"])

            # Execute scale testing
            self.logger.info(f"Executing: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes max
            )

            # Log output
            if result.stdout:
                self.logger.info("Scale testing output:")
                for line in result.stdout.splitlines()[-20:]:  # Last 20 lines
                    self.logger.info(f"  {line}")

            if result.stderr:
                self.logger.warning("Scale testing stderr:")
                for line in result.stderr.splitlines()[-10:]:  # Last 10 lines
                    self.logger.warning(f"  {line}")

            # Store results
            self.test_results['scale_testing'] = {
                'exit_code': result.returncode,
                'success': result.returncode == 0,
                'execution_time': None,  # Will be parsed from output if needed
                'stdout': result.stdout,
                'stderr': result.stderr
            }

            if result.returncode == 0:
                self.logger.info("✅ Scale testing passed")
                return True
            else:
                self.logger.error(f"❌ Scale testing failed with exit code {result.returncode}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error("❌ Scale testing timed out")
            self.test_results['scale_testing'] = {
                'exit_code': -1,
                'success': False,
                'error': 'timeout'
            }
            return False
        except Exception as e:
            self.logger.error(f"❌ Scale testing execution error: {e}")
            self.test_results['scale_testing'] = {
                'exit_code': -1,
                'success': False,
                'error': str(e)
            }
            return False

    def _run_parity_testing(self, test_mode: str) -> bool:
        """Run parity testing via subprocess."""
        self.logger.info(f"Running parity testing in {test_mode} mode...")

        try:
            # Prepare parity testing command
            cmd = [
                sys.executable,
                "scripts/parity_testing_framework.py",
                "--reports-dir", str(self.reports_dir / "parity_testing")
            ]

            # Add mode-specific arguments
            if test_mode == "quick":
                cmd.append("--quick")
            elif test_mode == "comprehensive":
                cmd.append("--full")
            else:  # standard
                cmd.append("--full")

            # Execute parity testing
            self.logger.info(f"Executing: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1200  # 20 minutes max
            )

            # Log output
            if result.stdout:
                self.logger.info("Parity testing output:")
                for line in result.stdout.splitlines()[-20:]:  # Last 20 lines
                    self.logger.info(f"  {line}")

            if result.stderr:
                self.logger.warning("Parity testing stderr:")
                for line in result.stderr.splitlines()[-10:]:  # Last 10 lines
                    self.logger.warning(f"  {line}")

            # Store results
            self.test_results['parity_testing'] = {
                'exit_code': result.returncode,
                'success': result.returncode == 0,
                'execution_time': None,
                'stdout': result.stdout,
                'stderr': result.stderr
            }

            if result.returncode == 0:
                self.logger.info("✅ Parity testing passed")
                return True
            else:
                self.logger.error(f"❌ Parity testing failed with exit code {result.returncode}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error("❌ Parity testing timed out")
            self.test_results['parity_testing'] = {
                'exit_code': -1,
                'success': False,
                'error': 'timeout'
            }
            return False
        except Exception as e:
            self.logger.error(f"❌ Parity testing execution error: {e}")
            self.test_results['parity_testing'] = {
                'exit_code': -1,
                'success': False,
                'error': str(e)
            }
            return False

    def _assess_deployment_readiness(self) -> bool:
        """Assess overall deployment readiness."""
        self.logger.info("Assessing deployment readiness...")

        scale_passed = self.test_results.get('scale_testing', {}).get('success', False)
        parity_passed = self.test_results.get('parity_testing', {}).get('success', False)

        self.logger.info(f"Scale testing: {'✅ PASSED' if scale_passed else '❌ FAILED'}")
        self.logger.info(f"Parity testing: {'✅ PASSED' if parity_passed else '❌ FAILED'}")

        deployment_ready = scale_passed and parity_passed

        if deployment_ready:
            self.logger.info("✅ Deployment readiness: APPROVED")
        else:
            self.logger.error("❌ Deployment readiness: NOT APPROVED")

        return deployment_ready

    def _generate_ci_reports(self, failed_at: Optional[str] = None, error: Optional[str] = None):
        """Generate CI/CD-compatible reports."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Generate JSON report for CI/CD systems
        json_report = {
            'metadata': {
                'generated': datetime.now().isoformat(),
                'framework': 'E068H CI/CD Integration',
                'version': '1.0.0',
                'failed_at': failed_at,
                'error': error
            },
            'summary': {
                'overall_status': self.test_results['overall_status'],
                'deployment_ready': self.test_results['overall_status'] == 'passed',
                'scale_testing_passed': self.test_results.get('scale_testing', {}).get('success', False),
                'parity_testing_passed': self.test_results.get('parity_testing', {}).get('success', False)
            },
            'results': self.test_results
        }

        json_path = self.reports_dir / f"e068h_ci_report_{timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(json_report, f, indent=2)

        # Generate JUnit XML for Jenkins/CI systems
        junit_path = self._generate_junit_xml(timestamp)

        # Generate GitHub Actions summary
        github_summary_path = self._generate_github_summary(timestamp)

        # Generate deployment decision file
        deployment_decision_path = self._generate_deployment_decision(timestamp)

        self.logger.info("CI/CD reports generated:")
        self.logger.info(f"  JSON Report: {json_path}")
        self.logger.info(f"  JUnit XML: {junit_path}")
        self.logger.info(f"  GitHub Summary: {github_summary_path}")
        self.logger.info(f"  Deployment Decision: {deployment_decision_path}")

    def _generate_junit_xml(self, timestamp: str) -> Path:
        """Generate JUnit-compatible XML report."""
        junit_path = self.reports_dir / f"e068h_junit_{timestamp}.xml"

        # Create JUnit XML structure
        testsuites = ET.Element("testsuites")
        testsuite = ET.SubElement(testsuites, "testsuite")
        testsuite.set("name", "E068H_ValidationSuite")
        testsuite.set("tests", "2")

        # Scale testing case
        scale_case = ET.SubElement(testsuite, "testcase")
        scale_case.set("name", "ScaleTesting")
        scale_case.set("classname", "E068H.ScaleTesting")

        scale_result = self.test_results.get('scale_testing', {})
        if not scale_result.get('success', False):
            failure = ET.SubElement(scale_case, "failure")
            failure.set("type", "ScaleTestFailure")
            failure.text = scale_result.get('error', 'Scale testing failed')

        # Parity testing case
        parity_case = ET.SubElement(testsuite, "testcase")
        parity_case.set("name", "ParityTesting")
        parity_case.set("classname", "E068H.ParityTesting")

        parity_result = self.test_results.get('parity_testing', {})
        if not parity_result.get('success', False):
            failure = ET.SubElement(parity_case, "failure")
            failure.set("type", "ParityTestFailure")
            failure.text = parity_result.get('error', 'Parity testing failed')

        # Write XML
        tree = ET.ElementTree(testsuites)
        tree.write(junit_path, encoding='utf-8', xml_declaration=True)

        return junit_path

    def _generate_github_summary(self, timestamp: str) -> Path:
        """Generate GitHub Actions job summary."""
        summary_path = self.reports_dir / f"github_summary_{timestamp}.md"

        scale_passed = self.test_results.get('scale_testing', {}).get('success', False)
        parity_passed = self.test_results.get('parity_testing', {}).get('success', False)
        overall_passed = self.test_results['overall_status'] == 'passed'

        lines = [
            "# E068H Production Validation Results",
            "",
            f"## Overall Status: {'✅ PASSED' if overall_passed else '❌ FAILED'}",
            "",
            "### Test Results",
            "",
            f"| Test Suite | Status | Result |",
            f"|------------|--------|--------|",
            f"| Scale Testing | {'✅' if scale_passed else '❌'} | {'PASSED' if scale_passed else 'FAILED'} |",
            f"| Parity Testing | {'✅' if parity_passed else '❌'} | {'PASSED' if parity_passed else 'FAILED'} |",
            "",
            f"### Deployment Decision",
            "",
            f"**Production Deployment:** {'✅ APPROVED' if overall_passed else '❌ NOT APPROVED'}",
            ""
        ]

        if not overall_passed:
            lines.extend([
                "### Issues to Address",
                ""
            ])

            if not scale_passed:
                lines.append("- ❌ Scale testing failed - Review performance scaling issues")
            if not parity_passed:
                lines.append("- ❌ Parity testing failed - Result consistency issues detected")

            lines.append("")

        lines.extend([
            f"### Report Details",
            f"- Generated: {datetime.now().isoformat()}",
            f"- Framework: E068H CI/CD Integration v1.0.0",
            ""
        ])

        with open(summary_path, 'w') as f:
            f.write('\n'.join(lines))

        # Set GitHub Actions summary if in GitHub environment
        github_summary = os.environ.get('GITHUB_STEP_SUMMARY')
        if github_summary:
            with open(github_summary, 'w') as f:
                f.write('\n'.join(lines))

        return summary_path

    def _generate_deployment_decision(self, timestamp: str) -> Path:
        """Generate deployment decision file for automation systems."""
        decision_path = self.reports_dir / f"deployment_decision_{timestamp}.json"

        overall_passed = self.test_results['overall_status'] == 'passed'

        decision = {
            'deployment_approved': overall_passed,
            'decision_timestamp': datetime.now().isoformat(),
            'decision_basis': {
                'scale_testing_passed': self.test_results.get('scale_testing', {}).get('success', False),
                'parity_testing_passed': self.test_results.get('parity_testing', {}).get('success', False)
            },
            'recommendation': 'DEPLOY' if overall_passed else 'DO_NOT_DEPLOY',
            'next_actions': [
                'Proceed with production deployment' if overall_passed else 'Address test failures',
                'Monitor production performance' if overall_passed else 'Re-run validation after fixes'
            ]
        }

        with open(decision_path, 'w') as f:
            json.dump(decision, f, indent=2)

        return decision_path


def main():
    """Main entry point for E068H CI/CD integration."""
    parser = argparse.ArgumentParser(
        description="E068H CI/CD Integration Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CI/CD Integration Examples:

  # GitHub Actions
  python scripts/e068h_ci_integration.py --mode standard --timeout 30

  # Jenkins Pipeline
  python scripts/e068h_ci_integration.py --mode comprehensive --timeout 45

  # Quick validation
  python scripts/e068h_ci_integration.py --mode quick --timeout 15
        """
    )

    parser.add_argument("--mode", choices=["quick", "standard", "comprehensive"],
                       default="standard",
                       help="CI testing mode (default: standard)")
    parser.add_argument("--timeout", type=int, default=30,
                       help="Maximum execution time in minutes (default: 30)")
    parser.add_argument("--reports-dir", type=Path, default=Path("reports/ci_integration"),
                       help="Directory for CI reports (default: reports/ci_integration)")
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose logging")

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Run CI/CD validation
    ci = E068HCIIntegration(reports_dir=args.reports_dir)
    exit_code = ci.run_comprehensive_ci_validation(
        test_mode=args.mode,
        timeout_minutes=args.timeout
    )

    # Set environment variables for CI/CD systems
    if exit_code == 0:
        os.environ["E068H_DEPLOYMENT_APPROVED"] = "true"
        os.environ["E068H_VALIDATION_STATUS"] = "passed"
    else:
        os.environ["E068H_DEPLOYMENT_APPROVED"] = "false"
        os.environ["E068H_VALIDATION_STATUS"] = "failed"

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
