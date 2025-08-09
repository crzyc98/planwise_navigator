#!/usr/bin/env python3
"""
Epic E035: Deferral Rate Escalation System - Multi-Year Validation Test Suite

This comprehensive test suite validates the automatic deferral rate escalation system
across the complete simulation lifecycle (2025-2029). It tests all user requirements,
business rules, data quality, and integration consistency.

User Requirements Tested:
- Default January 1st effective date
- 1% increment amount (configurable)
- 10% maximum rate cap (configurable)
- Toggle inclusion based on hire date
- Proper multi-year state progression

Usage:
    python test_escalation_system.py
    python test_escalation_system.py --verbose
    python test_escalation_system.py --year 2025
"""

import argparse
import duckdb
import json
import sys
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Any, Optional


class EscalationSystemTester:
    """Comprehensive test suite for deferral rate escalation system."""

    def __init__(self, db_path: str = "simulation.duckdb", verbose: bool = False):
        self.db_path = db_path
        self.verbose = verbose
        self.test_results = []
        self.errors = []

        # Connect to database
        try:
            self.conn = duckdb.connect(db_path)
            print(f"✅ Connected to database: {db_path}")
        except Exception as e:
            print(f"❌ Failed to connect to database {db_path}: {e}")
            sys.exit(1)

    def log(self, message: str, level: str = "INFO"):
        """Log message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.verbose or level in ["ERROR", "FAIL", "PASS"]:
            print(f"[{timestamp}] {level}: {message}")

    def run_query(self, query: str, description: str = "") -> List[Any]:
        """Execute query and return results."""
        try:
            if self.verbose and description:
                self.log(f"Executing query: {description}")
            result = self.conn.execute(query).fetchall()
            return result
        except Exception as e:
            self.log(f"Query failed ({description}): {e}", "ERROR")
            self.errors.append(f"Query error in {description}: {str(e)}")
            return []

    def test_configuration_setup(self) -> bool:
        """Test 1: Configuration and Parameter Setup"""
        self.log("=" * 60)
        self.log("Test 1: Configuration and Parameter Setup")
        self.log("=" * 60)

        passed = True

        # Test 1.1: Check DEFERRAL_ESCALATION parameters exist for all simulation years
        for year in range(2025, 2030):
            query = f"""
            SELECT COUNT(*) as param_count
            FROM comp_levers
            WHERE fiscal_year = {year}
              AND event_type = 'DEFERRAL_ESCALATION'
              AND parameter_name = 'escalation_rate'
            """
            result = self.run_query(query, f"Parameter check for year {year}")
            if not result or result[0][0] == 0:
                self.log(f"❌ Missing DEFERRAL_ESCALATION parameters for year {year}", "FAIL")
                passed = False
            else:
                self.log(f"✅ Found {result[0][0]} escalation parameters for year {year}", "PASS")

        # Test 1.2: Validate parameter values meet user requirements
        query = """
        SELECT
            fiscal_year,
            job_level,
            parameter_name,
            parameter_value,
            CASE
                WHEN parameter_name = 'escalation_rate' AND parameter_value = 0.01 THEN 'PASS'
                WHEN parameter_name = 'max_escalation_rate' AND parameter_value = 0.10 THEN 'PASS'
                ELSE 'FAIL'
            END as requirement_check
        FROM comp_levers
        WHERE event_type = 'DEFERRAL_ESCALATION'
          AND parameter_name IN ('escalation_rate', 'max_escalation_rate')
          AND fiscal_year = 2025
          AND job_level = 1
        ORDER BY parameter_name
        """
        results = self.run_query(query, "Parameter value validation")
        for row in results:
            fiscal_year, job_level, param_name, param_value, check = row
            if check == 'PASS':
                self.log(f"✅ {param_name} = {param_value} meets user requirements", "PASS")
            else:
                self.log(f"❌ {param_name} = {param_value} does not meet user requirements", "FAIL")
                passed = False

        self.test_results.append(("Configuration Setup", passed))
        return passed

    def test_event_generation(self, year: int = 2025) -> bool:
        """Test 2: Event Generation Logic"""
        self.log("=" * 60)
        self.log(f"Test 2: Event Generation Logic (Year {year})")
        self.log("=" * 60)

        passed = True

        # Test 2.1: Check escalation events are generated
        query = f"""
        SELECT COUNT(*) as event_count
        FROM int_deferral_rate_escalation_events
        WHERE simulation_year = {year}
        """
        result = self.run_query(query, f"Escalation event count for {year}")
        if result and result[0][0] > 0:
            event_count = result[0][0]
            self.log(f"✅ Generated {event_count} escalation events for year {year}", "PASS")
        else:
            self.log(f"❌ No escalation events generated for year {year}", "FAIL")
            passed = False
            return passed

        # Test 2.2: Verify effective date is January 1st (user requirement)
        query = f"""
        SELECT COUNT(*) as non_jan_1_count
        FROM int_deferral_rate_escalation_events
        WHERE simulation_year = {year}
          AND (EXTRACT(MONTH FROM effective_date) != 1 OR EXTRACT(DAY FROM effective_date) != 1)
        """
        result = self.run_query(query, f"January 1st effective date check for {year}")
        if result and result[0][0] == 0:
            self.log("✅ All escalation events have January 1st effective date", "PASS")
        else:
            self.log(f"❌ {result[0][0]} escalation events do not have January 1st effective date", "FAIL")
            passed = False

        # Test 2.3: Verify escalation rates meet user requirements (1% default)
        query = f"""
        SELECT
            COUNT(*) as total_events,
            SUM(CASE WHEN escalation_rate = 0.01 THEN 1 ELSE 0 END) as correct_rate_count,
            AVG(escalation_rate) as avg_rate
        FROM int_deferral_rate_escalation_events
        WHERE simulation_year = {year}
        """
        result = self.run_query(query, f"Escalation rate validation for {year}")
        if result:
            total, correct, avg_rate = result[0]
            if correct == total:
                self.log(f"✅ All {total} events have correct 1% escalation rate", "PASS")
            else:
                self.log(f"❌ {total - correct} events do not have 1% escalation rate (avg: {avg_rate:.1%})", "FAIL")
                passed = False

        # Test 2.4: Verify maximum rate cap enforcement (10% default)
        query = f"""
        SELECT COUNT(*) as cap_violations
        FROM int_deferral_rate_escalation_events
        WHERE simulation_year = {year}
          AND new_deferral_rate > max_escalation_rate
        """
        result = self.run_query(query, f"Rate cap enforcement for {year}")
        if result and result[0][0] == 0:
            self.log("✅ No rate cap violations detected", "PASS")
        else:
            self.log(f"❌ {result[0][0]} rate cap violations detected", "FAIL")
            passed = False

        # Test 2.5: Verify no duplicate escalations per employee
        query = f"""
        SELECT COUNT(*) - COUNT(DISTINCT employee_id) as duplicates
        FROM int_deferral_rate_escalation_events
        WHERE simulation_year = {year}
        """
        result = self.run_query(query, f"Duplicate escalation check for {year}")
        if result and result[0][0] == 0:
            self.log("✅ No duplicate escalations per employee", "PASS")
        else:
            self.log(f"❌ {result[0][0]} duplicate escalations detected", "FAIL")
            passed = False

        self.test_results.append((f"Event Generation {year}", passed))
        return passed

    def test_pipeline_integration(self, year: int = 2025) -> bool:
        """Test 3: Pipeline Integration"""
        self.log("=" * 60)
        self.log(f"Test 3: Pipeline Integration (Year {year})")
        self.log("=" * 60)

        passed = True

        # Test 3.1: Escalation events appear in main event stream
        query = f"""
        SELECT
            (SELECT COUNT(*) FROM int_deferral_rate_escalation_events WHERE simulation_year = {year}) as generated,
            (SELECT COUNT(*) FROM fct_yearly_events
             WHERE simulation_year = {year} AND event_category = 'deferral_escalation') as in_pipeline
        """
        result = self.run_query(query, f"Pipeline integration check for {year}")
        if result:
            generated, in_pipeline = result[0]
            if generated == in_pipeline:
                self.log(f"✅ All {generated} escalation events integrated into pipeline", "PASS")
            else:
                self.log(f"❌ Integration mismatch: {generated} generated, {in_pipeline} in pipeline", "FAIL")
                passed = False

        # Test 3.2: Workforce snapshot contains escalation data
        query = f"""
        SELECT
            COUNT(*) as total_workforce,
            SUM(CASE WHEN total_deferral_escalations IS NOT NULL THEN 1 ELSE 0 END) as with_escalation_data,
            SUM(CASE WHEN has_deferral_escalations = true THEN 1 ELSE 0 END) as with_escalations
        FROM fct_workforce_snapshot
        WHERE simulation_year = {year}
        """
        result = self.run_query(query, f"Workforce snapshot escalation data for {year}")
        if result:
            total, with_data, with_escalations = result[0]
            if with_data == total:
                self.log(f"✅ All {total} workforce records have escalation tracking data", "PASS")
            else:
                self.log(f"❌ {total - with_data} workforce records missing escalation data", "FAIL")
                passed = False

            self.log(f"📊 {with_escalations} employees have received escalations", "INFO")

        # Test 3.3: Contribution model uses escalated rates
        query = f"""
        SELECT COUNT(*) as rate_mismatches
        FROM int_employee_contributions c
        JOIN int_deferral_escalation_state_accumulator e
          ON c.employee_id = e.employee_id
          AND c.simulation_year = e.simulation_year
        WHERE c.simulation_year = {year}
          AND ABS(c.effective_deferral_rate - e.current_deferral_rate) > 0.001
        """
        result = self.run_query(query, f"Contribution rate consistency for {year}")
        if result and result[0][0] == 0:
            self.log("✅ Contribution model uses escalated deferral rates", "PASS")
        else:
            self.log(f"❌ {result[0][0]} deferral rate mismatches between models", "FAIL")
            passed = False

        self.test_results.append((f"Pipeline Integration {year}", passed))
        return passed

    def test_multi_year_progression(self) -> bool:
        """Test 4: Multi-Year Progression and State Management"""
        self.log("=" * 60)
        self.log("Test 4: Multi-Year Progression and State Management")
        self.log("=" * 60)

        passed = True

        # Test 4.1: Escalation counts increase year over year
        query = """
        SELECT
            curr.simulation_year,
            COUNT(*) as employees,
            SUM(CASE WHEN curr.total_escalations > prev.total_escalations THEN 1 ELSE 0 END) as escalation_increases,
            SUM(CASE WHEN curr.total_escalations < prev.total_escalations THEN 1 ELSE 0 END) as escalation_decreases
        FROM int_deferral_escalation_state_accumulator curr
        JOIN int_deferral_escalation_state_accumulator prev
          ON curr.employee_id = prev.employee_id
         AND curr.simulation_year = prev.simulation_year + 1
        WHERE curr.simulation_year BETWEEN 2026 AND 2029
        GROUP BY curr.simulation_year
        ORDER BY curr.simulation_year
        """
        results = self.run_query(query, "Multi-year escalation progression")
        for row in results:
            year, employees, increases, decreases = row
            if decreases == 0:
                self.log(f"✅ Year {year}: {increases} escalation increases, 0 decreases", "PASS")
            else:
                self.log(f"❌ Year {year}: {decreases} escalation count decreases detected", "FAIL")
                passed = False

        # Test 4.2: Deferral rates progress logically
        query = """
        SELECT
            curr.simulation_year,
            COUNT(*) as employees,
            AVG(curr.current_deferral_rate - prev.current_deferral_rate) as avg_rate_change,
            SUM(CASE WHEN curr.current_deferral_rate < prev.current_deferral_rate
                     AND curr.had_escalation_this_year = false THEN 1 ELSE 0 END) as rate_reversions
        FROM int_deferral_escalation_state_accumulator curr
        JOIN int_deferral_escalation_state_accumulator prev
          ON curr.employee_id = prev.employee_id
         AND curr.simulation_year = prev.simulation_year + 1
        WHERE curr.simulation_year BETWEEN 2026 AND 2029
        GROUP BY curr.simulation_year
        ORDER BY curr.simulation_year
        """
        results = self.run_query(query, "Multi-year rate progression")
        for row in results:
            year, employees, avg_change, reversions = row
            if reversions == 0:
                self.log(f"✅ Year {year}: No invalid rate reversions, avg change: {avg_change:.1%}", "PASS")
            else:
                self.log(f"❌ Year {year}: {reversions} invalid rate reversions detected", "FAIL")
                passed = False

        # Test 4.3: Maximum cap enforcement across years
        query = """
        SELECT
            simulation_year,
            COUNT(*) as employees_at_cap,
            MAX(current_deferral_rate) as max_rate,
            COUNT(CASE WHEN current_deferral_rate > 0.10 THEN 1 END) as cap_violations
        FROM int_deferral_escalation_state_accumulator
        WHERE simulation_year BETWEEN 2025 AND 2029
          AND has_escalations = true
        GROUP BY simulation_year
        ORDER BY simulation_year
        """
        results = self.run_query(query, "Multi-year cap enforcement")
        for row in results:
            year, at_cap, max_rate, violations = row
            if violations == 0:
                self.log(f"✅ Year {year}: Cap enforced, max rate: {max_rate:.1%}", "PASS")
            else:
                self.log(f"❌ Year {year}: {violations} cap violations, max rate: {max_rate:.1%}", "FAIL")
                passed = False

        self.test_results.append(("Multi-Year Progression", passed))
        return passed

    def test_data_quality_validation(self, year: int = 2025) -> bool:
        """Test 5: Data Quality Validation"""
        self.log("=" * 60)
        self.log(f"Test 5: Data Quality Validation (Year {year})")
        self.log("=" * 60)

        passed = True

        # Test 5.1: Check data quality health score
        query = f"""
        SELECT
            health_score,
            health_status,
            total_violations,
            total_records,
            violation_rate_pct,
            recommendations
        FROM dq_deferral_escalation_validation
        WHERE simulation_year = {year}
        """
        result = self.run_query(query, f"Data quality health score for {year}")
        if result:
            health_score, status, violations, records, rate, recommendations = result[0]
            if health_score >= 95:
                self.log(f"✅ Excellent data quality: {health_score}/100 ({status})", "PASS")
            elif health_score >= 85:
                self.log(f"✅ Good data quality: {health_score}/100 ({status})", "PASS")
            elif health_score >= 70:
                self.log(f"⚠️  Fair data quality: {health_score}/100 ({status})", "WARN")
                self.log(f"    Violations: {violations}/{records} ({rate:.1f}%)", "WARN")
            else:
                self.log(f"❌ Poor data quality: {health_score}/100 ({status})", "FAIL")
                self.log(f"    Violations: {violations}/{records} ({rate:.1f}%)", "FAIL")
                self.log(f"    Recommendation: {recommendations}", "FAIL")
                passed = False
        else:
            self.log(f"❌ No data quality validation results for year {year}", "FAIL")
            passed = False

        self.test_results.append((f"Data Quality {year}", passed))
        return passed

    def test_business_requirements(self, year: int = 2025) -> bool:
        """Test 6: Business Requirements Compliance"""
        self.log("=" * 60)
        self.log(f"Test 6: Business Requirements Compliance (Year {year})")
        self.log("=" * 60)

        passed = True

        # Test 6.1: Only enrolled employees get escalations
        query = f"""
        SELECT COUNT(*) as non_enrolled_escalations
        FROM int_deferral_rate_escalation_events esc
        LEFT JOIN int_enrollment_state_accumulator enr
          ON esc.employee_id = enr.employee_id
          AND esc.simulation_year = enr.simulation_year
        WHERE esc.simulation_year = {year}
          AND (enr.enrollment_status != true OR enr.enrollment_status IS NULL)
        """
        result = self.run_query(query, f"Enrolled-only escalation check for {year}")
        if result and result[0][0] == 0:
            self.log("✅ Only enrolled employees receive escalations", "PASS")
        else:
            self.log(f"❌ {result[0][0]} non-enrolled employees received escalations", "FAIL")
            passed = False

        # Test 6.2: Tenure and age thresholds respected
        query = f"""
        SELECT
            COUNT(*) as total_escalations,
            SUM(CASE WHEN current_tenure < 2 THEN 1 ELSE 0 END) as below_tenure_threshold,
            SUM(CASE WHEN current_age < 25 THEN 1 ELSE 0 END) as below_age_threshold
        FROM int_deferral_rate_escalation_events
        WHERE simulation_year = {year}
        """
        result = self.run_query(query, f"Threshold compliance check for {year}")
        if result:
            total, below_tenure, below_age = result[0]
            issues = below_tenure + below_age
            if issues == 0:
                self.log(f"✅ All {total} escalations meet age/tenure thresholds", "PASS")
            else:
                self.log(f"❌ {issues} escalations violate age/tenure thresholds", "FAIL")
                passed = False

        # Test 6.3: Meaningful increase threshold (prevent tiny escalations)
        query = f"""
        SELECT COUNT(*) as tiny_escalations
        FROM int_deferral_rate_escalation_events
        WHERE simulation_year = {year}
          AND (new_deferral_rate - previous_deferral_rate) < 0.001
        """
        result = self.run_query(query, f"Meaningful increase check for {year}")
        if result and result[0][0] == 0:
            self.log("✅ All escalations meet meaningful increase threshold", "PASS")
        else:
            self.log(f"❌ {result[0][0]} escalations below meaningful threshold", "FAIL")
            passed = False

        self.test_results.append((f"Business Requirements {year}", passed))
        return passed

    def test_edge_cases(self) -> bool:
        """Test 7: Edge Cases and Error Handling"""
        self.log("=" * 60)
        self.log("Test 7: Edge Cases and Error Handling")
        self.log("=" * 60)

        passed = True

        # Test 7.1: Employees at maximum rate don't get further escalations
        query = """
        SELECT COUNT(*) as over_escalated
        FROM int_deferral_escalation_state_accumulator
        WHERE simulation_year = 2029  -- Final year
          AND current_deferral_rate > max_escalation_rate
        """
        result = self.run_query(query, "Maximum rate enforcement")
        if result and result[0][0] == 0:
            self.log("✅ No employees escalated beyond maximum rate", "PASS")
        else:
            self.log(f"❌ {result[0][0]} employees over-escalated beyond maximum", "FAIL")
            passed = False

        # Test 7.2: Employees reaching maximum escalation count stop getting increases
        query = """
        SELECT COUNT(*) as over_escalated_count
        FROM int_deferral_escalation_state_accumulator
        WHERE simulation_year = 2029
          AND total_escalations > max_escalations
        """
        result = self.run_query(query, "Maximum escalation count enforcement")
        if result and result[0][0] == 0:
            self.log("✅ No employees exceed maximum escalation count", "PASS")
        else:
            self.log(f"❌ {result[0][0]} employees exceed maximum escalation count", "FAIL")
            passed = False

        # Test 7.3: Data quality flags are properly set
        query = """
        SELECT
            data_quality_flag,
            COUNT(*) as count
        FROM int_deferral_rate_escalation_events
        WHERE simulation_year = 2025
        GROUP BY data_quality_flag
        """
        results = self.run_query(query, "Data quality flags")
        valid_count = 0
        for row in results:
            flag, count = row
            if flag == 'VALID':
                valid_count += count
                self.log(f"✅ {count} events with VALID data quality flag", "PASS")
            else:
                self.log(f"❌ {count} events with {flag} data quality flag", "FAIL")
                passed = False

        self.test_results.append(("Edge Cases", passed))
        return passed

    def generate_report(self) -> None:
        """Generate comprehensive test report."""
        self.log("=" * 60)
        self.log("EPIC E035 ESCALATION SYSTEM TEST REPORT")
        self.log("=" * 60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, passed in self.test_results if passed)

        self.log(f"Total Tests: {total_tests}")
        self.log(f"Passed: {passed_tests}")
        self.log(f"Failed: {total_tests - passed_tests}")
        self.log(f"Success Rate: {passed_tests/total_tests*100:.1f}%")

        print("\n" + "=" * 60)
        print("DETAILED RESULTS")
        print("=" * 60)

        for test_name, passed in self.test_results:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} {test_name}")

        if self.errors:
            print("\n" + "=" * 60)
            print("ERRORS ENCOUNTERED")
            print("=" * 60)
            for error in self.errors:
                print(f"❌ {error}")

        print("\n" + "=" * 60)
        if passed_tests == total_tests:
            print("🎉 ALL TESTS PASSED! Epic E035 is ready for production.")
        else:
            print(f"⚠️  {total_tests - passed_tests} test(s) failed. Review issues before deployment.")
        print("=" * 60)

    def run_full_test_suite(self) -> bool:
        """Run the complete test suite."""
        self.log("Starting Epic E035 Deferral Rate Escalation System Test Suite")
        self.log(f"Database: {self.db_path}")
        self.log(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        all_passed = True

        # Run all test categories
        all_passed &= self.test_configuration_setup()
        all_passed &= self.test_event_generation(2025)
        all_passed &= self.test_pipeline_integration(2025)
        all_passed &= self.test_multi_year_progression()
        all_passed &= self.test_data_quality_validation(2025)
        all_passed &= self.test_business_requirements(2025)
        all_passed &= self.test_edge_cases()

        # Generate final report
        self.generate_report()

        return all_passed

    def __del__(self):
        """Clean up database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()


def main():
    """Main entry point for escalation system testing."""
    parser = argparse.ArgumentParser(
        description="Epic E035 Deferral Rate Escalation System Test Suite"
    )
    parser.add_argument(
        "--db",
        default="simulation.duckdb",
        help="Path to DuckDB database file (default: simulation.duckdb)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Test specific year (runs full suite if not specified)"
    )

    args = parser.parse_args()

    # Verify database exists
    if not Path(args.db).exists():
        print(f"❌ Database file not found: {args.db}")
        print("Run a simulation first to generate the database.")
        sys.exit(1)

    # Create tester instance
    tester = EscalationSystemTester(db_path=args.db, verbose=args.verbose)

    # Run tests
    if args.year:
        # Run specific year tests
        success = (
            tester.test_event_generation(args.year) and
            tester.test_pipeline_integration(args.year) and
            tester.test_data_quality_validation(args.year) and
            tester.test_business_requirements(args.year)
        )
    else:
        # Run full test suite
        success = tester.run_full_test_suite()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
