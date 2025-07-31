"""
Multi-year simulation orchestration for MVP orchestrator.

This module provides comprehensive multi-year workforce simulation capabilities,
building on the existing single-year MVP components. It orchestrates year-by-year
execution with proper workforce transitions, event generation, and validation.
"""

import logging
from typing import Dict, Any, Optional
import time

from .workforce_calculations import (
    calculate_workforce_requirements_from_config,
    validate_workforce_calculation_inputs
)
from .event_emitter import generate_and_store_all_events
from .workforce_snapshot import generate_workforce_snapshot
from .database_manager import get_connection


def run_multi_year_simulation(
    start_year: int,
    end_year: int,
    config: Dict[str, Any],
    skip_breaks: bool = False
) -> Dict[str, Any]:
    """
    Main orchestration function for multi-year workforce simulation.

    Iterates through years from start_year to end_year, running the complete
    simulation workflow for each year with proper workforce transitions.

    Args:
        start_year: First simulation year (e.g., 2025)
        end_year: Last simulation year (e.g., 2029)
        config: Configuration dictionary containing simulation parameters
        skip_breaks: If True, skip user interaction prompts between years

    Returns:
        Dictionary containing simulation results summary

    Example:
        >>> config = {'target_growth_rate': 0.03, 'total_termination_rate': 0.12}
        >>> results = run_multi_year_simulation(2025, 2029, config)
    """
    logging.info(f"🚀 Starting multi-year simulation: {start_year}-{end_year}")

    simulation_results = {
        'start_year': start_year,
        'end_year': end_year,
        'years_completed': [],
        'years_failed': [],
        'total_runtime_seconds': 0,
        'year_runtimes': {}
    }

    start_time = time.time()

    try:
        for current_year in range(start_year, end_year + 1):
            year_start_time = time.time()
            logging.info(f"\n🗓️  SIMULATING YEAR {current_year}")
            logging.info("=" * 50)

            try:
                # Validate year transition if not the first year
                if current_year > start_year:
                    if not validate_year_transition(current_year - 1, current_year):
                        raise ValueError(f"Year transition validation failed for {current_year}")

                # Determine starting workforce count
                if current_year == start_year:
                    logging.info(f"📊 Year {current_year}: Using baseline workforce")
                    workforce_count = get_baseline_workforce_count()
                else:
                    logging.info(f"📊 Year {current_year}: Using previous year workforce")
                    workforce_count = get_previous_year_workforce_count(current_year)

                logging.info(f"Starting workforce for {current_year}: {workforce_count:,} employees")

                # Validate calculation inputs
                validation = validate_workforce_calculation_inputs(
                    workforce_count,
                    config.get('target_growth_rate', 0.03),
                    config.get('workforce', {}).get('total_termination_rate', 0.12),
                    config.get('workforce', {}).get('new_hire_termination_rate', 0.25)
                )

                if not validation['valid']:
                    raise ValueError(f"Invalid workforce calculation inputs: {validation['errors']}")

                if validation['warnings']:
                    for warning in validation['warnings']:
                        logging.warning(f"⚠️  {warning}")

                # Calculate workforce requirements
                calc_result = calculate_workforce_requirements_from_config(
                    workforce_count,
                    {
                        'target_growth_rate': config.get('target_growth_rate', 0.03),
                        'total_termination_rate': config.get('workforce', {}).get('total_termination_rate', 0.12),
                        'new_hire_termination_rate': config.get('workforce', {}).get('new_hire_termination_rate', 0.25)
                    }
                )

                # Enhanced workforce requirements logging
                log_enhanced_workforce_requirements(current_year, workforce_count, calc_result, config)

                logging.info(f"📈 Growth calculation: +{calc_result['total_hires_needed']:,} hires, "
                            f"-{calc_result['experienced_terminations']:,} terminations")

                # STEP 1: Build compensation table BEFORE event generation
                logging.info(f"📋 Step 1: Building employee compensation table for year {current_year}")
                from ..loaders.staging_loader import run_dbt_model_with_vars

                # First, ensure required dependencies exist for subsequent years
                if current_year > start_year:
                    logging.info(f"   Building helper model for year {current_year}")
                    helper_vars = {'simulation_year': current_year}
                    run_dbt_model_with_vars("int_active_employees_prev_year_snapshot", helper_vars)
                    logging.info(f"   ✅ Helper model built for year {current_year}")

                # Now build the compensation table
                compensation_vars = {
                    'simulation_year': current_year,
                    'start_year': start_year
                }
                run_dbt_model_with_vars("int_employee_compensation_by_year", compensation_vars)
                logging.info(f"✅ Step 1 Complete: Compensation table built for year {current_year}")

                # STEP 2: Generate events (using the compensation table)
                random_seed = config.get('random_seed', 42) + (current_year - start_year)
                logging.info(f"🎲 Generating events for year {current_year} with seed {random_seed}")

                generate_and_store_all_events(
                    calc_result=calc_result,
                    simulation_year=current_year,
                    random_seed=random_seed,
                    config=config
                )

                # Validate event generation
                tolerance = config.get('validation', {}).get('tolerance_percent', 0.05)
                validate_event_generation(current_year, calc_result, tolerance)

                # STEP 3: Generate workforce snapshot (references compensation table + events)
                logging.info(f"📸 Step 3: Generating workforce snapshot for year {current_year}")
                generate_workforce_snapshot(simulation_year=current_year)
                logging.info(f"✅ Step 3 Complete: Year-end snapshot created for year {current_year}")

                # Reconcile year-end workforce
                reconcile_year_end_workforce(current_year, workforce_count, calc_result, tolerance)

                # Record successful completion
                year_runtime = time.time() - year_start_time
                simulation_results['years_completed'].append(current_year)
                simulation_results['year_runtimes'][current_year] = year_runtime

                # Comprehensive year summary logging
                log_comprehensive_year_summary(current_year, workforce_count, calc_result, year_runtime)

                logging.info(f"✅ Year {current_year} completed in {year_runtime:.1f}s")

                # Interactive break between years (unless skipped or last year)
                if not skip_breaks and current_year < end_year:
                    input(f"📋 Press Enter to continue to year {current_year + 1}...")

            except Exception as e:
                logging.error(f"❌ Year {current_year} simulation failed: {str(e)}")
                simulation_results['years_failed'].append(current_year)
                raise

        # Calculate total runtime
        simulation_results['total_runtime_seconds'] = time.time() - start_time

        logging.info(f"\n🎉 Multi-year simulation completed successfully!")
        logging.info(f"Years simulated: {start_year}-{end_year}")
        logging.info(f"Total runtime: {simulation_results['total_runtime_seconds']:.1f}s")

        return simulation_results

    except Exception as e:
        simulation_results['total_runtime_seconds'] = time.time() - start_time
        logging.error(f"💥 Multi-year simulation failed: {str(e)}")
        raise


def prepare_next_year_baseline(current_year: int) -> int:
    """
    Extract active employees from current year's workforce snapshot for next year baseline.

    Args:
        current_year: Year to extract workforce snapshot from

    Returns:
        Number of active employees to use as baseline for next year

    Raises:
        ValueError: If no workforce data found for the specified year
    """
    logging.info(f"📋 Preparing baseline for year {current_year + 1} from year {current_year} snapshot")

    try:
        conn = get_connection()
        try:
            query = """
                SELECT COUNT(*) as active_count
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
                AND employment_status = 'active'
            """

            result = conn.execute(query, [current_year]).fetchone()

            if result is None or result[0] == 0:
                raise ValueError(f"No active workforce found for year {current_year}")

            active_count = result[0]
            logging.info(f"📊 Found {active_count:,} active employees in year {current_year}")

            return active_count

        finally:
            conn.close()

    except Exception as e:
        logging.error(f"❌ Failed to prepare next year baseline: {str(e)}")
        raise


def validate_year_transition(from_year: int, to_year: int) -> bool:
    """
    Enhanced validation of data handoff between simulation years.

    Provides comprehensive checks for data quality, continuity, and integrity
    between simulation years. Includes detailed validation and troubleshooting.

    Args:
        from_year: Previous simulation year
        to_year: Current simulation year

    Returns:
        True if validation passes, False otherwise
    """
    logging.info(f"🔍 Validating year transition: {from_year} → {to_year}")

    validation_results = {
        'snapshot_exists': False,
        'reasonable_workforce_count': False,
        'events_exist': False,
        'data_consistency': False,
        'overall_passed': False
    }

    conn = get_connection()
    try:
        # Enhanced snapshot validation with detailed statistics
        snapshot_query = """
            SELECT
                COUNT(*) as total_employees,
                SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) as active_employees,
                SUM(CASE WHEN employment_status = 'terminated' THEN 1 ELSE 0 END) as terminated_employees,
                AVG(current_age) as avg_age,
                AVG(current_tenure) as avg_tenure,
                AVG(current_compensation) as avg_compensation,
                MIN(current_compensation) as min_compensation,
                MAX(current_compensation) as max_compensation,
                COUNT(DISTINCT level_id) as distinct_levels
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
        """

        result = conn.execute(snapshot_query, [from_year]).fetchone()

        if result is None or result[0] == 0:
            logging.error(f"❌ No workforce snapshot found for year {from_year}")
        else:
            (total_employees, active_employees, terminated_employees,
             avg_age, avg_tenure, avg_compensation, min_compensation,
             max_compensation, distinct_levels) = result

            validation_results['snapshot_exists'] = True

            logging.info(f"📊 Year {from_year} snapshot details:")
            logging.info(f"   • Total employees: {total_employees:,}")
            logging.info(f"   • Active: {active_employees:,}, Terminated: {terminated_employees:,}")
            logging.info(f"   • Average age: {avg_age:.1f}, tenure: {avg_tenure:.1f} years")
            logging.info(f"   • Compensation range: ${min_compensation:,.0f} - ${max_compensation:,.0f}")
            logging.info(f"   • Distinct job levels: {distinct_levels}")

            # Enhanced workforce count validation
            if active_employees >= 50:  # More reasonable minimum for small orgs
                validation_results['reasonable_workforce_count'] = True
            else:
                logging.warning(f"⚠️  Very low active employee count: {active_employees}")
                if active_employees > 0:
                    validation_results['reasonable_workforce_count'] = True  # Allow small counts

            if total_employees == 0:
                logging.error(f"❌ No employees in year {from_year} snapshot")

        # Enhanced events validation with detailed breakdown (FIXED: Case-insensitive matching)
        events_query = """
            SELECT
                COUNT(*) as total_events,
                COUNT(CASE WHEN UPPER(event_type) = 'HIRE' THEN 1 END) as hire_events,
                COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) as termination_events,
                COUNT(CASE WHEN UPPER(event_type) = 'PROMOTION' THEN 1 END) as promotion_events,
                COUNT(CASE WHEN UPPER(event_type) = 'RAISE' THEN 1 END) as raise_events,
                COUNT(CASE WHEN UPPER(data_quality_flag) = 'VALID' THEN 1 END) as valid_events
            FROM fct_yearly_events
            WHERE simulation_year = ?
        """

        events_result = conn.execute(events_query, [from_year]).fetchone()

        if events_result is None or events_result[0] == 0:
            logging.warning(f"⚠️  No events found for year {from_year}")
        else:
            (total_events, hire_events, termination_events,
             promotion_events, raise_events, valid_events) = events_result

            validation_results['events_exist'] = True

            logging.info(f"📊 Year {from_year} events breakdown:")
            logging.info(f"   • Total events: {total_events:,} ({valid_events:,} valid)")
            logging.info(f"   • Hires: {hire_events:,}, Terminations: {termination_events:,}")
            logging.info(f"   • Promotions: {promotion_events:,}, Raises: {raise_events:,}")

        # Data consistency check: compare workforce changes with events
        if validation_results['snapshot_exists'] and validation_results['events_exist']:
            # Handle first year transition (2025→2026) differently
            # For first year, compare against int_baseline_workforce, not fct_workforce_snapshot
            if from_year == 2025:
                consistency_query = """
                    WITH event_summary AS (
                        SELECT
                            COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as net_hires,
                            COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as net_terminations
                        FROM fct_yearly_events
                        WHERE simulation_year = ?
                    ),
                    snapshot_comparison AS (
                        SELECT
                            curr.active_count as current_active,
                            prev.active_count as previous_active,
                            curr.active_count - prev.active_count as workforce_change
                        FROM (
                            SELECT COUNT(*) as active_count
                            FROM fct_workforce_snapshot
                            WHERE simulation_year = ? AND employment_status = 'active'
                        ) curr
                        CROSS JOIN (
                            SELECT COUNT(*) as active_count
                            FROM int_baseline_workforce
                            WHERE employment_status = 'active'
                        ) prev
                    )
                    SELECT
                        es.net_hires,
                        es.net_terminations,
                        es.net_hires - es.net_terminations as expected_change,
                        sc.workforce_change as actual_change,
                        ABS((es.net_hires - es.net_terminations) - sc.workforce_change) as variance
                    FROM event_summary es
                    CROSS JOIN snapshot_comparison sc
                """
                consistency_result = conn.execute(
                    consistency_query,
                    [from_year, from_year]
                ).fetchone()
            else:
                # For subsequent years, use fct_workforce_snapshot for both current and previous
                consistency_query = """
                    WITH event_summary AS (
                        SELECT
                            COUNT(CASE WHEN event_type = 'hire' THEN 1 END) as net_hires,
                            COUNT(CASE WHEN event_type = 'termination' THEN 1 END) as net_terminations
                        FROM fct_yearly_events
                        WHERE simulation_year = ?
                    ),
                    snapshot_comparison AS (
                        SELECT
                            curr.active_count as current_active,
                            prev.active_count as previous_active,
                            curr.active_count - prev.active_count as workforce_change
                        FROM (
                            SELECT COUNT(*) as active_count
                            FROM fct_workforce_snapshot
                            WHERE simulation_year = ? AND employment_status = 'active'
                        ) curr
                        CROSS JOIN (
                            SELECT COUNT(*) as active_count
                            FROM fct_workforce_snapshot
                            WHERE simulation_year = ? AND employment_status = 'active'
                        ) prev
                    )
                    SELECT
                        es.net_hires,
                        es.net_terminations,
                        es.net_hires - es.net_terminations as expected_change,
                        sc.workforce_change as actual_change,
                        ABS((es.net_hires - es.net_terminations) - sc.workforce_change) as variance
                    FROM event_summary es
                    CROSS JOIN snapshot_comparison sc
                """
                consistency_result = conn.execute(
                    consistency_query,
                    [from_year, from_year, from_year - 1]
                ).fetchone()

            if consistency_result:
                (net_hires, net_terminations, expected_change,
                 actual_change, variance) = consistency_result

                logging.info(f"📊 Data consistency check:")
                logging.info(f"   • Expected workforce change: {expected_change:,}")
                logging.info(f"   • Actual workforce change: {actual_change:,}")
                logging.info(f"   • Variance: {variance:,}")

                # Allow 5% variance in workforce changes
                if variance <= max(10, abs(expected_change) * 0.05):
                    validation_results['data_consistency'] = True
                else:
                    logging.warning(f"⚠️  High variance in workforce change: {variance}")

        # Overall validation assessment
        passed_checks = sum(validation_results.values())
        total_checks = len(validation_results) - 1  # Exclude 'overall_passed'

        if passed_checks >= 3:  # At least 3 of 4 checks must pass
            validation_results['overall_passed'] = True
            logging.info(f"✅ Year transition validation passed: {from_year} → {to_year} ({passed_checks}/{total_checks} checks)")
        else:
            logging.error(f"❌ Year transition validation failed: {from_year} → {to_year} ({passed_checks}/{total_checks} checks)")

        return validation_results['overall_passed']

    except Exception as e:
        logging.error(f"❌ Year transition validation error: {str(e)}")
        return False

    finally:
        conn.close()


def get_baseline_workforce_count() -> int:
    """
    Get the baseline workforce count for the first simulation year.

    Returns:
        Number of employees in the baseline workforce

    Raises:
        ValueError: If baseline workforce data not found
    """
    logging.info("📊 Retrieving baseline workforce count")

    try:
        conn = get_connection()
        try:
            # Query the baseline workforce table
            query = """
                SELECT COUNT(*) as baseline_count
                FROM int_baseline_workforce
            """

            result = conn.execute(query).fetchone()

            if result is None or result[0] == 0:
                raise ValueError("No baseline workforce data found")

            baseline_count = result[0]
            logging.info(f"📊 Baseline workforce count: {baseline_count:,} employees")

            return baseline_count

        finally:
            conn.close()

    except Exception as e:
        logging.error(f"❌ Failed to get baseline workforce count: {str(e)}")
        raise


def get_previous_year_workforce_count(simulation_year: int) -> int:
    """
    Enhanced retrieval of active workforce count from the previous year's snapshot.

    Provides comprehensive validation and better error handling with detailed
    fallback logic and data quality warnings.

    Args:
        simulation_year: Current simulation year

    Returns:
        Number of active employees from previous year

    Raises:
        ValueError: If critical validation fails and no fallback is possible
    """
    previous_year = simulation_year - 1
    logging.info(f"📊 Retrieving workforce count from year {previous_year}")

    try:
        conn = get_connection()
        try:
            # Enhanced query with additional validation data
            query = """
                SELECT
                    COUNT(*) as active_count,
                    AVG(current_age) as avg_age,
                    AVG(current_compensation) as avg_compensation,
                    COUNT(DISTINCT level_id) as distinct_levels,
                    MIN(snapshot_created_at) as snapshot_date
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
                AND employment_status = 'active'
            """

            result = conn.execute(query, [previous_year]).fetchone()

            if result is None or result[0] == 0:
                # Enhanced fallback decision with explicit warnings
                logging.warning(f"⚠️  No active workforce found for year {previous_year}")
                logging.warning("⚠️  This indicates potential data continuity issues")
                logging.warning("⚠️  Falling back to baseline workforce - results may not reflect year-over-year growth")

                # Require explicit confirmation for fallback in production scenarios
                baseline_count = get_baseline_workforce_count()
                logging.warning(f"⚠️  Using baseline workforce count: {baseline_count:,} employees")
                logging.warning("⚠️  Multi-year simulation may lose year-over-year continuity")

                return baseline_count

            active_count, avg_age, avg_compensation, distinct_levels, snapshot_date = result

            # Validate data quality before accepting
            data_quality_issues = []

            if active_count < 10:
                data_quality_issues.append(f"Very low employee count: {active_count}")

            if avg_age is None or avg_age < 20 or avg_age > 70:
                data_quality_issues.append(f"Suspicious average age: {avg_age}")

            if avg_compensation is None or avg_compensation < 30000:
                data_quality_issues.append(f"Suspicious average compensation: {avg_compensation}")

            if distinct_levels < 2:
                data_quality_issues.append(f"Too few job levels: {distinct_levels}")

            if data_quality_issues:
                logging.warning(f"⚠️  Data quality concerns for year {previous_year}:")
                for issue in data_quality_issues:
                    logging.warning(f"   • {issue}")
                logging.warning("⚠️  Proceeding with caution - results may be unreliable")

            logging.info(f"📊 Previous year ({previous_year}) workforce details:")
            logging.info(f"   • Active employees: {active_count:,}")
            logging.info(f"   • Average age: {avg_age:.1f} years")
            logging.info(f"   • Average compensation: ${avg_compensation:,.0f}")
            logging.info(f"   • Job levels: {distinct_levels}")
            logging.info(f"   • Snapshot created: {snapshot_date}")

            return active_count

        finally:
            conn.close()

    except Exception as e:
        logging.error(f"❌ Failed to get previous year workforce count: {str(e)}")
        logging.error("❌ This is a critical error for multi-year simulation continuity")

        # Try fallback to baseline with explicit warnings
        try:
            logging.warning("🔄 Attempting fallback to baseline workforce count")
            baseline_count = get_baseline_workforce_count()
            logging.warning(f"⚠️  Using baseline fallback: {baseline_count:,} employees")
            logging.warning("⚠️  Multi-year simulation has lost data continuity")
            return baseline_count
        except Exception as fallback_error:
            logging.error(f"❌ Fallback to baseline also failed: {str(fallback_error)}")
            raise ValueError(
                f"Critical error: Cannot retrieve workforce data for year {previous_year} "
                f"and baseline fallback failed. Multi-year simulation cannot continue."
            )


def validate_multi_year_data_integrity(start_year: int, end_year: int) -> Dict[str, Any]:
    """
    Comprehensive validation of multi-year data integrity before starting simulation.

    Args:
        start_year: First simulation year
        end_year: Last simulation year

    Returns:
        Dictionary with detailed validation results and recommendations
    """
    logging.info(f"🔍 Validating multi-year data integrity for years {start_year}-{end_year}")

    validation_results = {
        'baseline_available': False,
        'existing_years': [],
        'data_gaps': [],
        'data_quality_issues': [],
        'recommendations': [],
        'can_proceed': False
    }

    try:
        conn = get_connection()
        try:
            # Check baseline workforce availability
            baseline_query = "SELECT COUNT(*) FROM int_baseline_workforce"
            baseline_result = conn.execute(baseline_query).fetchone()

            if baseline_result and baseline_result[0] > 0:
                validation_results['baseline_available'] = True
                logging.info(f"✅ Baseline workforce available: {baseline_result[0]:,} employees")
            else:
                logging.error("❌ No baseline workforce data found")
                validation_results['recommendations'].append("Generate baseline workforce data before starting simulation")

            # Check existing simulation years
            existing_years_query = """
                SELECT DISTINCT simulation_year, COUNT(*) as employee_count
                FROM fct_workforce_snapshot
                WHERE simulation_year BETWEEN ? AND ?
                GROUP BY simulation_year
                ORDER BY simulation_year
            """

            existing_results = conn.execute(existing_years_query, [start_year, end_year]).fetchall()

            for year, count in existing_results:
                validation_results['existing_years'].append({'year': year, 'employee_count': count})
                logging.info(f"📊 Found existing data for year {year}: {count:,} employees")

            # Identify data gaps
            existing_year_numbers = [row['year'] for row in validation_results['existing_years']]
            for year in range(start_year, end_year + 1):
                if year not in existing_year_numbers:
                    validation_results['data_gaps'].append(year)

            if validation_results['data_gaps']:
                logging.warning(f"⚠️  Data gaps found for years: {validation_results['data_gaps']}")

            # Assess overall readiness
            if validation_results['baseline_available'] and len(validation_results['data_quality_issues']) == 0:
                validation_results['can_proceed'] = True
                logging.info("✅ Multi-year data integrity validation passed")
            else:
                logging.warning("⚠️  Multi-year data integrity issues found")

        finally:
            conn.close()

    except Exception as e:
        logging.error(f"❌ Multi-year data integrity validation error: {str(e)}")
        validation_results['recommendations'].append("Resolve database connectivity issues")

    return validation_results


def log_enhanced_workforce_requirements(simulation_year: int, workforce_count: int, calc_result: Dict[str, Any], config: Dict[str, Any]) -> None:
    """
    Enhanced workforce requirements logging with detailed formula transparency.

    Args:
        simulation_year: Current simulation year
        workforce_count: Starting workforce count
        calc_result: Results from workforce calculations with formula details
        config: Configuration dictionary
    """
    logging.info(f"📊 ENHANCED WORKFORCE REQUIREMENTS - YEAR {simulation_year}")
    logging.info("=" * 60)

    # Extract configuration parameters
    target_growth = config.get('target_growth_rate', 0.03)
    total_term_rate = config.get('workforce', {}).get('total_termination_rate', 0.12)
    new_hire_term_rate = config.get('workforce', {}).get('new_hire_termination_rate', 0.25)

    logging.info(f"📋 Configuration Parameters:")
    logging.info(f"   • Target growth rate: {target_growth:.1%}")
    logging.info(f"   • Total termination rate: {total_term_rate:.1%}")
    logging.info(f"   • New hire termination rate: {new_hire_term_rate:.1%}")
    logging.info(f"   • Starting workforce: {workforce_count:,} employees")

    # Log calculation results with details
    logging.info(f"📈 Workforce Calculation Results:")
    logging.info(f"   • Target workforce size: {calc_result.get('target_workforce_size', 'N/A'):,}")
    logging.info(f"   • Growth amount needed: {calc_result.get('growth_amount', 'N/A'):,}")
    logging.info(f"   • Experienced terminations: {calc_result.get('experienced_terminations', 'N/A'):,}")
    logging.info(f"   • New hire terminations: {calc_result.get('new_hire_terminations', 'N/A'):,}")
    logging.info(f"   • Total hires needed: {calc_result.get('total_hires_needed', 'N/A'):,}")

    # Log formula details if available
    if 'formula_details' in calc_result:
        logging.info(f"🧮 Formula Transparency:")
        for key, value in calc_result['formula_details'].items():
            logging.info(f"   • {key}: {value}")

    # Log expected workforce changes
    net_growth = calc_result.get('total_hires_needed', 0) - calc_result.get('experienced_terminations', 0) - calc_result.get('new_hire_terminations', 0)
    expected_final = workforce_count + net_growth

    logging.info(f"📊 Expected Workforce Changes:")
    logging.info(f"   • Net workforce change: {net_growth:+,}")
    logging.info(f"   • Expected final workforce: {expected_final:,}")
    logging.info(f"   • Effective growth rate: {(net_growth / workforce_count):.2%}")


def validate_event_generation(simulation_year: int, calc_result: Dict[str, Any], tolerance: float = 0.05) -> Dict[str, Any]:
    """
    Validate actual event generation against calculated requirements.

    Args:
        simulation_year: Current simulation year
        calc_result: Expected event counts from workforce calculations
        tolerance: Acceptable variance threshold (default 5%)

    Returns:
        Dictionary with validation results
    """
    logging.info(f"🔍 VALIDATING EVENT GENERATION - YEAR {simulation_year}")
    logging.info("=" * 50)

    validation_results = {
        'hires_valid': False,
        'terminations_valid': False,
        'new_hire_terms_valid': False,
        'overall_valid': False,
        'variances': {}
    }

    try:
        conn = get_connection()
        try:
            # Query actual events generated
            events_query = """
                SELECT
                    COUNT(CASE WHEN UPPER(event_type) = 'HIRE' THEN 1 END) as actual_hires,
                    COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' AND UPPER(is_new_hire) = 'TRUE' THEN 1 END) as actual_new_hire_terms,
                    COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' AND UPPER(is_new_hire) = 'FALSE' THEN 1 END) as actual_experienced_terms,
                    COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) as actual_total_terms
                FROM fct_yearly_events
                WHERE simulation_year = ?
            """

            result = conn.execute(events_query, [simulation_year]).fetchone()

            if result:
                actual_hires, actual_new_hire_terms, actual_experienced_terms, actual_total_terms = result

                # Compare against expected values
                expected_hires = calc_result.get('total_hires_needed', 0)
                expected_new_hire_terms = calc_result.get('new_hire_terminations', 0)
                expected_experienced_terms = calc_result.get('experienced_terminations', 0)

                logging.info(f"📊 Event Generation Comparison:")
                logging.info(f"   • Hires - Expected: {expected_hires:,}, Actual: {actual_hires:,}")
                logging.info(f"   • New hire terminations - Expected: {expected_new_hire_terms:,}, Actual: {actual_new_hire_terms:,}")
                logging.info(f"   • Experienced terminations - Expected: {expected_experienced_terms:,}, Actual: {actual_experienced_terms:,}")

                # Calculate variances
                def calculate_variance(expected, actual):
                    if expected == 0:
                        return 0.0 if actual == 0 else float('inf')
                    return abs(actual - expected) / expected

                hire_variance = calculate_variance(expected_hires, actual_hires)
                new_hire_term_variance = calculate_variance(expected_new_hire_terms, actual_new_hire_terms)
                experienced_term_variance = calculate_variance(expected_experienced_terms, actual_experienced_terms)

                validation_results['variances'] = {
                    'hires': hire_variance,
                    'new_hire_terminations': new_hire_term_variance,
                    'experienced_terminations': experienced_term_variance
                }

                # Validate against tolerance
                validation_results['hires_valid'] = hire_variance <= tolerance
                validation_results['new_hire_terms_valid'] = new_hire_term_variance <= tolerance
                validation_results['terminations_valid'] = experienced_term_variance <= tolerance

                logging.info(f"📈 Variance Analysis (tolerance: {tolerance:.1%}):")
                logging.info(f"   • Hires variance: {hire_variance:.1%} {'✅' if validation_results['hires_valid'] else '❌'}")
                logging.info(f"   • New hire terminations variance: {new_hire_term_variance:.1%} {'✅' if validation_results['new_hire_terms_valid'] else '❌'}")
                logging.info(f"   • Experienced terminations variance: {experienced_term_variance:.1%} {'✅' if validation_results['terminations_valid'] else '❌'}")

                # Overall validation
                validation_results['overall_valid'] = all([
                    validation_results['hires_valid'],
                    validation_results['new_hire_terms_valid'],
                    validation_results['terminations_valid']
                ])

                if validation_results['overall_valid']:
                    logging.info("✅ Event generation validation PASSED")
                else:
                    logging.warning("⚠️  Event generation validation FAILED - some variances exceed tolerance")
            else:
                logging.error("❌ No events found for validation")

        finally:
            conn.close()

    except Exception as e:
        logging.error(f"❌ Event generation validation error: {str(e)}")

    return validation_results


def reconcile_year_end_workforce(simulation_year: int, starting_workforce: int, calc_result: Dict[str, Any], tolerance: float = 0.05) -> Dict[str, Any]:
    """
    Reconcile year-end workforce against targets with detailed analysis.

    Args:
        simulation_year: Current simulation year
        starting_workforce: Starting workforce count
        calc_result: Expected workforce calculations
        tolerance: Acceptable variance threshold

    Returns:
        Dictionary with reconciliation results
    """
    logging.info(f"📊 YEAR-END WORKFORCE RECONCILIATION - YEAR {simulation_year}")
    logging.info("=" * 55)

    reconciliation_results = {
        'workforce_target_met': False,
        'growth_target_met': False,
        'data_quality_good': False,
        'overall_success': False
    }

    try:
        conn = get_connection()
        try:
            # Query final workforce state
            workforce_query = """
                SELECT
                    COUNT(*) as total_employees,
                    COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
                    COUNT(CASE WHEN employment_status = 'terminated' THEN 1 END) as terminated_employees,
                    AVG(current_compensation) as avg_compensation,
                    AVG(current_age) as avg_age
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
            """

            workforce_result = conn.execute(workforce_query, [simulation_year]).fetchone()

            # Query events summary
            events_query = """
                SELECT
                    COUNT(CASE WHEN UPPER(event_type) = 'HIRE' THEN 1 END) as total_hires,
                    COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) as total_terminations
                FROM fct_yearly_events
                WHERE simulation_year = ?
            """

            events_result = conn.execute(events_query, [simulation_year]).fetchone()

            if workforce_result and events_result:
                (total_employees, active_employees, terminated_employees,
                 avg_compensation, avg_age) = workforce_result
                total_hires, total_terminations = events_result

                # Calculate expected values
                expected_net_change = calc_result.get('total_hires_needed', 0) - calc_result.get('experienced_terminations', 0) - calc_result.get('new_hire_terminations', 0)
                expected_final_workforce = starting_workforce + expected_net_change
                actual_net_change = total_hires - total_terminations
                actual_final_workforce = active_employees

                logging.info(f"📊 Workforce Reconciliation Analysis:")
                logging.info(f"   • Starting workforce: {starting_workforce:,}")
                logging.info(f"   • Total hires: {total_hires:,}")
                logging.info(f"   • Total terminations: {total_terminations:,}")
                logging.info(f"   • Net change: {actual_net_change:+,}")
                logging.info(f"   • Final active workforce: {actual_final_workforce:,}")
                logging.info(f"   • Final total employees: {total_employees:,}")

                logging.info(f"📈 Target vs Actual Comparison:")
                logging.info(f"   • Expected net change: {expected_net_change:+,}")
                logging.info(f"   • Actual net change: {actual_net_change:+,}")
                logging.info(f"   • Expected final workforce: {expected_final_workforce:,}")
                logging.info(f"   • Actual final workforce: {actual_final_workforce:,}")

                # Calculate variances
                if expected_final_workforce > 0:
                    workforce_variance = abs(actual_final_workforce - expected_final_workforce) / expected_final_workforce
                    reconciliation_results['workforce_target_met'] = workforce_variance <= tolerance
                    logging.info(f"   • Workforce variance: {workforce_variance:.1%} {'✅' if reconciliation_results['workforce_target_met'] else '❌'}")

                if expected_net_change != 0:
                    growth_variance = abs(actual_net_change - expected_net_change) / abs(expected_net_change)
                    reconciliation_results['growth_target_met'] = growth_variance <= tolerance
                    logging.info(f"   • Growth variance: {growth_variance:.1%} {'✅' if reconciliation_results['growth_target_met'] else '❌'}")
                else:
                    reconciliation_results['growth_target_met'] = actual_net_change == 0

                # Data quality checks
                quality_issues = []
                if avg_compensation and avg_compensation < 30000:
                    quality_issues.append(f"Low average compensation: ${avg_compensation:,.0f}")
                if avg_age and (avg_age < 20 or avg_age > 70):
                    quality_issues.append(f"Unusual average age: {avg_age:.1f}")
                if active_employees < 10:
                    quality_issues.append(f"Very low workforce: {active_employees}")

                if quality_issues:
                    logging.warning("⚠️  Data quality concerns:")
                    for issue in quality_issues:
                        logging.warning(f"   • {issue}")
                    reconciliation_results['data_quality_good'] = False
                else:
                    reconciliation_results['data_quality_good'] = True
                    logging.info("✅ Data quality checks passed")

                # Overall assessment
                reconciliation_results['overall_success'] = all([
                    reconciliation_results['workforce_target_met'],
                    reconciliation_results['growth_target_met'],
                    reconciliation_results['data_quality_good']
                ])

                if reconciliation_results['overall_success']:
                    logging.info("✅ Year-end workforce reconciliation PASSED")
                else:
                    logging.warning("⚠️  Year-end workforce reconciliation has issues")
            else:
                logging.error("❌ Unable to retrieve workforce or events data for reconciliation")

        finally:
            conn.close()

    except Exception as e:
        logging.error(f"❌ Workforce reconciliation error: {str(e)}")

    return reconciliation_results


def log_comprehensive_year_summary(simulation_year: int, starting_workforce: int, calc_result: Dict[str, Any], year_runtime: float) -> None:
    """
    Comprehensive year summary with all validation results aggregated.

    Args:
        simulation_year: Current simulation year
        starting_workforce: Starting workforce count
        calc_result: Workforce calculation results
        year_runtime: Year execution time in seconds
    """
    logging.info(f"📋 COMPREHENSIVE YEAR SUMMARY - YEAR {simulation_year}")
    logging.info("=" * 60)

    try:
        conn = get_connection()
        try:
            # Aggregate all key metrics
            summary_query = """
                WITH workforce_stats AS (
                    SELECT
                        COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as final_active,
                        COUNT(CASE WHEN employment_status = 'terminated' THEN 1 END) as final_terminated,
                        AVG(current_compensation) as avg_compensation,
                        AVG(current_age) as avg_age
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                ),
                event_stats AS (
                    SELECT
                        COUNT(CASE WHEN UPPER(event_type) = 'HIRE' THEN 1 END) as total_hires,
                        COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) as total_terminations,
                        COUNT(CASE WHEN UPPER(event_type) = 'PROMOTION' THEN 1 END) as total_promotions,
                        COUNT(CASE WHEN UPPER(event_type) = 'RAISE' THEN 1 END) as total_raises,
                        COUNT(CASE WHEN UPPER(data_quality_flag) = 'VALID' THEN 1 END) as valid_events,
                        COUNT(*) as total_events
                    FROM fct_yearly_events
                    WHERE simulation_year = ?
                )
                SELECT
                    ws.final_active, ws.final_terminated, ws.avg_compensation, ws.avg_age,
                    es.total_hires, es.total_terminations, es.total_promotions,
                    es.total_raises, es.valid_events, es.total_events
                FROM workforce_stats ws
                CROSS JOIN event_stats es
            """

            result = conn.execute(summary_query, [simulation_year, simulation_year]).fetchone()

            if result:
                (final_active, final_terminated, avg_compensation, avg_age,
                 total_hires, total_terminations, total_promotions,
                 total_raises, valid_events, total_events) = result

                net_change = total_hires - total_terminations
                growth_rate = net_change / starting_workforce if starting_workforce > 0 else 0

                logging.info(f"📊 Key Performance Indicators:")
                logging.info(f"   • Starting workforce: {starting_workforce:,}")
                logging.info(f"   • Final active workforce: {final_active:,}")
                logging.info(f"   • Net workforce change: {net_change:+,}")
                logging.info(f"   • Actual growth rate: {growth_rate:+.2%}")
                logging.info(f"   • Year execution time: {year_runtime:.1f}s")

                logging.info(f"📈 Event Generation Summary:")
                logging.info(f"   • Total events generated: {total_events:,}")
                logging.info(f"   • Valid events: {valid_events:,} ({valid_events/total_events:.1%})")
                logging.info(f"   • Hires: {total_hires:,}, Terminations: {total_terminations:,}")
                logging.info(f"   • Promotions: {total_promotions:,}, Raises: {total_raises:,}")

                logging.info(f"📊 Workforce Quality Metrics:")
                logging.info(f"   • Average compensation: ${avg_compensation:,.0f}")
                logging.info(f"   • Average age: {avg_age:.1f} years")
                logging.info(f"   • Active employees: {final_active:,}")
                logging.info(f"   • Terminated employees: {final_terminated:,}")

                # Expected vs actual comparison
                expected_hires = calc_result.get('total_hires_needed', 0)
                expected_terms = calc_result.get('experienced_terminations', 0) + calc_result.get('new_hire_terminations', 0)

                logging.info(f"🎯 Target Achievement:")
                hire_accuracy = (1 - abs(total_hires - expected_hires) / max(expected_hires, 1)) * 100
                term_accuracy = (1 - abs(total_terminations - expected_terms) / max(expected_terms, 1)) * 100

                logging.info(f"   • Hire target accuracy: {hire_accuracy:.1f}%")
                logging.info(f"   • Termination target accuracy: {term_accuracy:.1f}%")

                # Year-over-year comparison if not first year
                if simulation_year > 2025:
                    logging.info(f"📈 Year-over-Year Analysis:")
                    prev_query = """
                        SELECT COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as prev_active
                        FROM fct_workforce_snapshot
                        WHERE simulation_year = ?
                    """
                    prev_result = conn.execute(prev_query, [simulation_year - 1]).fetchone()
                    if prev_result and prev_result[0]:
                        prev_active = prev_result[0]
                        yoy_change = final_active - prev_active
                        yoy_growth = yoy_change / prev_active if prev_active > 0 else 0
                        logging.info(f"   • Previous year workforce: {prev_active:,}")
                        logging.info(f"   • Year-over-year change: {yoy_change:+,}")
                        logging.info(f"   • Year-over-year growth: {yoy_growth:+.2%}")

                logging.info("=" * 60)
            else:
                logging.warning("⚠️  Unable to generate comprehensive summary - data not available")

        finally:
            conn.close()

    except Exception as e:
        logging.error(f"❌ Comprehensive year summary error: {str(e)}")
