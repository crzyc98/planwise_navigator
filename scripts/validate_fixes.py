#!/usr/bin/env python3
"""
Comprehensive validation script to verify that all three debugging issues have been resolved:
1. Growth Variance in termination logic
2. $25M compensation anomaly
3. "Raises: 0" reporting bug

This script runs end-to-end tests to confirm all fixes are working correctly.
"""

import duckdb
import pandas as pd
import sys
from pathlib import Path
import logging
import subprocess
from typing import Dict, List, Tuple, Optional

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def connect_to_database():
    """Connect to the simulation database"""
    db_path = project_root / "simulation.duckdb"
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        sys.exit(1)
    return duckdb.connect(str(db_path))

def run_dbt_models() -> bool:
    """Run dbt models to generate fresh test data"""
    logger.info("🔧 Running dbt models to generate fresh test data...")

    try:
        # Change to dbt directory
        dbt_dir = project_root / "dbt"

        # Run dbt models
        result = subprocess.run(
            ["dbt", "run", "--select", "fct_workforce_snapshot", "fct_yearly_events"],
            cwd=dbt_dir,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            logger.info("✅ dbt models ran successfully")
            return True
        else:
            logger.error(f"❌ dbt models failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("❌ dbt models timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"❌ Error running dbt models: {e}")
        return False

def validate_growth_variance_fix(conn, simulation_year: int = 2025) -> Dict[str, any]:
    """Validate that the Growth Variance issue has been fixed"""
    logger.info(f"📊 VALIDATING GROWTH VARIANCE FIX FOR YEAR {simulation_year}")
    logger.info("=" * 70)

    results = {
        'test_name': 'Growth Variance Fix',
        'passed': False,
        'details': {},
        'issues': []
    }

    try:
        # Count termination events
        termination_events_query = """
        SELECT COUNT(*) as termination_count
        FROM fct_yearly_events
        WHERE simulation_year = ?
            AND UPPER(event_type) = 'TERMINATION'
        """

        termination_count = conn.execute(termination_events_query, [simulation_year]).df().iloc[0]['termination_count']

        # Count terminated employees in snapshot
        terminated_employees_query = """
        SELECT COUNT(*) as terminated_count
        FROM fct_workforce_snapshot
        WHERE simulation_year = ?
            AND employment_status = 'terminated'
        """

        terminated_count = conn.execute(terminated_employees_query, [simulation_year]).df().iloc[0]['terminated_count']

        # Calculate variance
        variance = abs(termination_count - terminated_count)
        variance_pct = (variance / max(termination_count, 1)) * 100

        results['details'] = {
            'termination_events': termination_count,
            'terminated_employees': terminated_count,
            'variance': variance,
            'variance_percentage': variance_pct
        }

        logger.info(f"Termination events: {termination_count}")
        logger.info(f"Terminated employees: {terminated_count}")
        logger.info(f"Variance: {variance} ({variance_pct:.1f}%)")

        # Pass if variance is within 5%
        if variance_pct <= 5.0:
            logger.info("✅ Growth variance within acceptable bounds (<5%)")
            results['passed'] = True
        else:
            logger.error(f"❌ Growth variance too high: {variance_pct:.1f}%")
            results['issues'].append(f"High growth variance: {variance_pct:.1f}%")

        # Additional check: ensure case-insensitive termination matching is working
        case_check_query = """
        SELECT
            event_type,
            COUNT(*) as count
        FROM fct_yearly_events
        WHERE simulation_year = ?
            AND (UPPER(event_type) = 'TERMINATION' OR event_type = 'termination')
        GROUP BY event_type
        """

        case_df = conn.execute(case_check_query, [simulation_year]).df()
        if not case_df.empty:
            logger.info("Event type case variations found:")
            for _, row in case_df.iterrows():
                logger.info(f"  '{row['event_type']}': {row['count']} events")

    except Exception as e:
        logger.error(f"❌ Error validating growth variance fix: {e}")
        results['issues'].append(f"Validation error: {e}")

    return results

def validate_compensation_anomaly_fix(conn, simulation_year: int = 2025) -> Dict[str, any]:
    """Validate that the $25M compensation anomaly has been fixed"""
    logger.info(f"💰 VALIDATING COMPENSATION ANOMALY FIX FOR YEAR {simulation_year}")
    logger.info("=" * 70)

    results = {
        'test_name': 'Compensation Anomaly Fix',
        'passed': False,
        'details': {},
        'issues': []
    }

    try:
        # Check for extreme salaries
        extreme_salaries_query = """
        SELECT
            COUNT(*) as total_employees,
            COUNT(CASE WHEN current_compensation > 5000000 THEN 1 END) as above_5M,
            COUNT(CASE WHEN current_compensation > 2000000 THEN 1 END) as above_2M,
            COUNT(CASE WHEN current_compensation > 1000000 THEN 1 END) as above_1M,
            MAX(current_compensation) as max_compensation,
            AVG(current_compensation) as avg_compensation
        FROM fct_workforce_snapshot
        WHERE simulation_year = ?
        """

        comp_stats = conn.execute(extreme_salaries_query, [simulation_year]).df().iloc[0]

        results['details'] = {
            'total_employees': int(comp_stats['total_employees']),
            'above_5M': int(comp_stats['above_5M']),
            'above_2M': int(comp_stats['above_2M']),
            'above_1M': int(comp_stats['above_1M']),
            'max_compensation': float(comp_stats['max_compensation']),
            'avg_compensation': float(comp_stats['avg_compensation'])
        }

        logger.info(f"Total employees: {comp_stats['total_employees']:,}")
        logger.info(f"Above $5M: {comp_stats['above_5M']} employees")
        logger.info(f"Above $2M: {comp_stats['above_2M']} employees")
        logger.info(f"Above $1M: {comp_stats['above_1M']} employees")
        logger.info(f"Max compensation: ${comp_stats['max_compensation']:,.2f}")
        logger.info(f"Avg compensation: ${comp_stats['avg_compensation']:,.2f}")

        # Pass if no employees above $5M and max is reasonable
        if comp_stats['above_5M'] == 0 and comp_stats['max_compensation'] < 2000000:
            logger.info("✅ No extreme compensation anomalies found")
            results['passed'] = True
        else:
            if comp_stats['above_5M'] > 0:
                logger.error(f"❌ Found {comp_stats['above_5M']} employees with >$5M compensation")
                results['issues'].append(f"{comp_stats['above_5M']} employees above $5M")

            if comp_stats['max_compensation'] >= 2000000:
                logger.error(f"❌ Maximum compensation too high: ${comp_stats['max_compensation']:,.2f}")
                results['issues'].append(f"Max compensation: ${comp_stats['max_compensation']:,.2f}")

        # Check promotion and merit increase caps are working
        promotion_check_query = """
        SELECT
            COUNT(*) as total_promotions,
            MAX(compensation_amount) as max_promo_salary,
            AVG(compensation_amount) as avg_promo_salary
        FROM fct_yearly_events
        WHERE simulation_year = ?
            AND UPPER(event_type) = 'PROMOTION'
        """

        promo_stats = conn.execute(promotion_check_query, [simulation_year]).df()
        if not promo_stats.empty and promo_stats.iloc[0]['total_promotions'] > 0:
            promo_result = promo_stats.iloc[0]
            logger.info(f"Promotion stats: {promo_result['total_promotions']} promotions, "
                       f"max: ${promo_result['max_promo_salary']:,.2f}")

            if promo_result['max_promo_salary'] > 5000000:
                results['issues'].append(f"Extreme promotion salary: ${promo_result['max_promo_salary']:,.2f}")

        merit_check_query = """
        SELECT
            COUNT(*) as total_raises,
            MAX(compensation_amount) as max_raise_salary,
            AVG(compensation_amount) as avg_raise_salary
        FROM fct_yearly_events
        WHERE simulation_year = ?
            AND UPPER(event_type) = 'RAISE'
        """

        merit_stats = conn.execute(merit_check_query, [simulation_year]).df()
        if not merit_stats.empty and merit_stats.iloc[0]['total_raises'] > 0:
            merit_result = merit_stats.iloc[0]
            logger.info(f"Merit raise stats: {merit_result['total_raises']} raises, "
                       f"max: ${merit_result['max_raise_salary']:,.2f}")

            if merit_result['max_raise_salary'] > 5000000:
                results['issues'].append(f"Extreme merit salary: ${merit_result['max_raise_salary']:,.2f}")

    except Exception as e:
        logger.error(f"❌ Error validating compensation anomaly fix: {e}")
        results['issues'].append(f"Validation error: {e}")

    return results

def validate_raises_reporting_fix(conn, simulation_year: int = 2025) -> Dict[str, any]:
    """Validate that the 'Raises: 0' reporting bug has been fixed"""
    logger.info(f"📈 VALIDATING RAISES REPORTING FIX FOR YEAR {simulation_year}")
    logger.info("=" * 70)

    results = {
        'test_name': 'Raises Reporting Fix',
        'passed': False,
        'details': {},
        'issues': []
    }

    try:
        # Replicate the exact validation query from multi_year_simulation.py
        validation_query = """
        SELECT
            COUNT(CASE WHEN UPPER(event_type) = 'HIRE' THEN 1 END) as hire_events,
            COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) as termination_events,
            COUNT(CASE WHEN UPPER(event_type) = 'PROMOTION' THEN 1 END) as promotion_events,
            COUNT(CASE WHEN UPPER(event_type) = 'RAISE' THEN 1 END) as raise_events,
            COUNT(*) as total_events
        FROM fct_yearly_events
        WHERE simulation_year = ?
        """

        validation_result = conn.execute(validation_query, [simulation_year]).df().iloc[0]

        results['details'] = {
            'hire_events': int(validation_result['hire_events']),
            'termination_events': int(validation_result['termination_events']),
            'promotion_events': int(validation_result['promotion_events']),
            'raise_events': int(validation_result['raise_events']),
            'total_events': int(validation_result['total_events'])
        }

        logger.info(f"Event validation results:")
        logger.info(f"  Hire events: {validation_result['hire_events']}")
        logger.info(f"  Termination events: {validation_result['termination_events']}")
        logger.info(f"  Promotion events: {validation_result['promotion_events']}")
        logger.info(f"  Raise events: {validation_result['raise_events']}")
        logger.info(f"  Total events: {validation_result['total_events']}")

        # Check if raises are being reported correctly
        if validation_result['total_events'] > 0:
            if validation_result['raise_events'] > 0:
                logger.info("✅ Raise events are being counted correctly")
                results['passed'] = True
            else:
                # Check if merit events exist but aren't being counted
                direct_merit_query = """
                SELECT event_type, COUNT(*) as count
                FROM fct_yearly_events
                WHERE simulation_year = ?
                    AND (UPPER(event_type) LIKE '%RAISE%'
                         OR UPPER(event_type) LIKE '%MERIT%'
                         OR event_type = 'RAISE')
                GROUP BY event_type
                """

                merit_df = conn.execute(direct_merit_query, [simulation_year]).df()

                if merit_df.empty:
                    logger.warning("⚠️  No merit/raise events found - may be expected if no eligible employees")
                    results['passed'] = True  # Not an error if no eligible employees
                    results['issues'].append("No merit events generated (may be expected)")
                else:
                    logger.error("❌ Merit events exist but not counted in validation query")
                    results['issues'].append("Merit events exist but not counted")
                    logger.info("Found merit events:")
                    for _, row in merit_df.iterrows():
                        logger.info(f"  '{row['event_type']}': {row['count']} events")
        else:
            logger.warning("⚠️  No events found for validation")
            results['issues'].append("No events found")

        # Test case sensitivity variations
        case_test_query = """
        SELECT
            event_type,
            COUNT(*) as count
        FROM fct_yearly_events
        WHERE simulation_year = ?
        GROUP BY event_type
        ORDER BY count DESC
        """

        case_df = conn.execute(case_test_query, [simulation_year]).df()
        if not case_df.empty:
            logger.info("All event types found:")
            for _, row in case_df.iterrows():
                logger.info(f"  '{row['event_type']}': {row['count']} events")

    except Exception as e:
        logger.error(f"❌ Error validating raises reporting fix: {e}")
        results['issues'].append(f"Validation error: {e}")

    return results

def run_end_to_end_test(conn) -> Dict[str, any]:
    """Run comprehensive end-to-end test"""
    logger.info(f"🚀 RUNNING END-TO-END VALIDATION TEST")
    logger.info("=" * 70)

    results = {
        'test_name': 'End-to-End Validation',
        'passed': False,
        'details': {},
        'issues': []
    }

    try:
        # Check data consistency across tables
        consistency_query = """
        SELECT
            'fct_yearly_events' as table_name,
            simulation_year,
            COUNT(*) as record_count,
            COUNT(DISTINCT employee_id) as unique_employees
        FROM fct_yearly_events
        GROUP BY simulation_year

        UNION ALL

        SELECT
            'fct_workforce_snapshot' as table_name,
            simulation_year,
            COUNT(*) as record_count,
            COUNT(DISTINCT employee_id) as unique_employees
        FROM fct_workforce_snapshot
        GROUP BY simulation_year

        ORDER BY table_name, simulation_year
        """

        consistency_df = conn.execute(consistency_query).df()

        if not consistency_df.empty:
            logger.info("Data consistency check:")
            for _, row in consistency_df.iterrows():
                logger.info(f"  {row['table_name']} {row['simulation_year']}: "
                           f"{row['record_count']:,} records, {row['unique_employees']:,} unique employees")

        # Check that all major event types are represented
        event_summary_query = """
        SELECT
            UPPER(event_type) as event_type,
            COUNT(*) as count
        FROM fct_yearly_events
        GROUP BY UPPER(event_type)
        ORDER BY count DESC
        """

        event_summary_df = conn.execute(event_summary_query).df()

        expected_events = ['HIRE', 'TERMINATION', 'PROMOTION', 'RAISE']
        found_events = set(event_summary_df['event_type'].tolist())

        results['details']['event_types_found'] = list(found_events)
        results['details']['expected_event_types'] = expected_events

        missing_events = set(expected_events) - found_events
        if missing_events:
            results['issues'].append(f"Missing event types: {missing_events}")

        # Basic data quality checks
        quality_issues = 0

        # Check for NULL employee IDs
        null_check = conn.execute("SELECT COUNT(*) FROM fct_yearly_events WHERE employee_id IS NULL").fetchone()[0]
        if null_check > 0:
            quality_issues += 1
            results['issues'].append(f"{null_check} NULL employee IDs in events")

        # Check for negative compensations
        neg_comp_check = conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot WHERE current_compensation < 0").fetchone()[0]
        if neg_comp_check > 0:
            quality_issues += 1
            results['issues'].append(f"{neg_comp_check} negative compensation values")

        results['passed'] = len(missing_events) == 0 and quality_issues == 0

        if results['passed']:
            logger.info("✅ End-to-end validation passed")
        else:
            logger.error("❌ End-to-end validation failed")

    except Exception as e:
        logger.error(f"❌ Error in end-to-end test: {e}")
        results['issues'].append(f"Test error: {e}")

    return results

def generate_summary_report(all_results: List[Dict[str, any]]) -> None:
    """Generate a comprehensive summary report"""
    logger.info(f"\n📋 VALIDATION SUMMARY REPORT")
    logger.info("=" * 80)

    total_tests = len(all_results)
    passed_tests = sum(1 for r in all_results if r['passed'])
    failed_tests = total_tests - passed_tests

    logger.info(f"Total tests run: {total_tests}")
    logger.info(f"Passed: {passed_tests} ✅")
    logger.info(f"Failed: {failed_tests} ❌")

    logger.info(f"\nDetailed Results:")
    logger.info("-" * 50)

    for result in all_results:
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        logger.info(f"{result['test_name']}: {status}")

        if result['issues']:
            for issue in result['issues']:
                logger.info(f"  • {issue}")

    if failed_tests == 0:
        logger.info(f"\n🎉 ALL FIXES VALIDATED SUCCESSFULLY!")
        logger.info("All three debugging issues have been resolved:")
        logger.info("  1. ✅ Growth Variance in termination logic")
        logger.info("  2. ✅ $25M compensation anomaly")
        logger.info("  3. ✅ 'Raises: 0' reporting bug")
    else:
        logger.error(f"\n⚠️  {failed_tests} VALIDATION(S) FAILED")
        logger.error("Some issues may still need attention.")

    return failed_tests == 0

def main():
    """Main validation orchestration"""
    logger.info("🔍 COMPREHENSIVE FIX VALIDATION")
    logger.info("=" * 80)
    logger.info("Validating fixes for:")
    logger.info("  1. Growth Variance in termination logic")
    logger.info("  2. $25M compensation anomaly")
    logger.info("  3. 'Raises: 0' reporting bug")
    logger.info("")

    try:
        # Optionally run dbt models to ensure fresh data
        run_fresh_data = input("Run dbt models for fresh test data? (y/N): ").lower().startswith('y')
        if run_fresh_data:
            if not run_dbt_models():
                logger.error("❌ Failed to generate fresh test data")
                sys.exit(1)

        # Connect to database
        conn = connect_to_database()

        # Run all validation tests
        all_results = []

        # Test 1: Growth Variance Fix
        all_results.append(validate_growth_variance_fix(conn))

        # Test 2: Compensation Anomaly Fix
        all_results.append(validate_compensation_anomaly_fix(conn))

        # Test 3: Raises Reporting Fix
        all_results.append(validate_raises_reporting_fix(conn))

        # Test 4: End-to-End Validation
        all_results.append(run_end_to_end_test(conn))

        # Generate summary report
        all_passed = generate_summary_report(all_results)

        conn.close()

        if all_passed:
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Validation failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
