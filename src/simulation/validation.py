"""
Simulation Validation and Testing Functions

This module contains pure business logic functions for validating simulation
results, testing data quality, and ensuring acceptance criteria compliance.
These functions are independent of the Dagster orchestration framework.

Functions:
    validate_year_results: Comprehensive validation of single year simulation results
    assert_year_complete: Strict validation that simulation data exists
    log_hiring_calculation_debug: Detailed hiring calculation debug information

Classes:
    YearResult: Data structure for simulation year results
"""

from typing import Dict, Any
import duckdb
from pathlib import Path
import math
from pydantic import BaseModel
from dagster import OpExecutionContext

# Database path configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "simulation.duckdb"


class YearResult(BaseModel):
    """Results from simulating a single year"""

    year: int
    success: bool
    active_employees: int
    total_terminations: int
    experienced_terminations: int
    new_hire_terminations: int
    total_hires: int
    growth_rate: float
    validation_passed: bool


def assert_year_complete(context: OpExecutionContext, year: int) -> None:
    """
    Strict validation that both snapshot AND events exist before proceeding.
    Per Epic June 19 E1: Both the year-N snapshot and year-N events must exist.
    No silent recovery - hard fail on missing data.
    """
    conn = duckdb.connect(str(DB_PATH))

    try:
        # Check events count
        events_count = conn.execute(
            """
            SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ?
        """,
            [year],
        ).fetchone()[0]

        # Check snapshot count
        snapshot_count = conn.execute(
            """
            SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?
        """,
            [year],
        ).fetchone()[0]

        if snapshot_count < 1 or events_count < 1:
            raise Exception(
                f"Year {year} incomplete "
                f"(snapshot={snapshot_count}, events={events_count}). Aborting."
            )

        context.log.info(
            f"Year {year} validation passed: snapshot={snapshot_count}, events={events_count}"
        )
    finally:
        conn.close()


def log_hiring_calculation_debug(
    context: OpExecutionContext, year: int, config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Log detailed hiring calculation debug information.

    This helper function extracts and logs the detailed hiring calculation
    debug information that was previously embedded in event processing loops.
    It maintains the exact same mathematical calculations and logging format.

    Args:
        context: Dagster operation execution context
        year: Simulation year for calculation
        config: Configuration dictionary with simulation parameters

    Returns:
        Dict containing calculated hiring metrics for validation
    """
    context.log.info("🔍 HIRING CALCULATION DEBUG:")

    conn = duckdb.connect(str(DB_PATH))
    try:
        # Calculate workforce count using same logic as validate_year_results
        # This ensures consistency between debug output and validation metrics
        if year == 2025:
            # For first simulation year, use baseline workforce
            workforce_count = conn.execute(
                "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'"
            ).fetchone()[0]
        else:
            # For subsequent years, use previous year's workforce snapshot
            workforce_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM fct_workforce_snapshot
                WHERE simulation_year = ? AND employment_status = 'active'
            """,
                [year - 1],
            ).fetchone()[0]

        # Extract formula inputs
        target_growth_rate = config["target_growth_rate"]
        total_termination_rate = config["total_termination_rate"]
        new_hire_termination_rate = config["new_hire_termination_rate"]

        # Apply exact formula from int_hiring_events.sql
        experienced_terms = math.ceil(workforce_count * total_termination_rate)
        growth_amount = workforce_count * target_growth_rate
        total_hires_needed = math.ceil(
            (experienced_terms + growth_amount) / (1 - new_hire_termination_rate)
        )
        expected_new_hire_terms = round(total_hires_needed * new_hire_termination_rate)

        # Log all debug information (preserve exact format)
        context.log.info(f"  📊 Starting workforce: {workforce_count} active employees")
        context.log.info(f"  📊 Target growth rate: {target_growth_rate:.1%}")
        context.log.info(f"  📊 Total termination rate: {total_termination_rate:.1%}")
        context.log.info(
            f"  📊 New hire termination rate: {new_hire_termination_rate:.1%}"
        )
        context.log.info(f"  📊 Expected experienced terminations: {experienced_terms}")
        context.log.info(f"  📊 Growth amount needed: {growth_amount:.1f}")
        context.log.info(f"  🎯 TOTAL HIRES CALLING FOR: {total_hires_needed}")
        context.log.info(
            f"  📊 Expected new hire terminations: {expected_new_hire_terms}"
        )
        context.log.info(
            f"  📊 Net hiring impact: {total_hires_needed - expected_new_hire_terms}"
        )
        context.log.info(
            f"  📊 Formula: CEIL(({experienced_terms} + {growth_amount:.1f}) / (1 - {new_hire_termination_rate})) = {total_hires_needed}"
        )

        return {
            "year": year,
            "workforce_count": workforce_count,
            "experienced_terms": experienced_terms,
            "growth_amount": growth_amount,
            "total_hires_needed": total_hires_needed,
            "expected_new_hire_terms": expected_new_hire_terms,
            "net_hiring_impact": total_hires_needed - expected_new_hire_terms,
        }

    except Exception as e:
        context.log.warning(f"Error calculating hiring debug info: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


def validate_year_results(
    context: OpExecutionContext, year: int, config: Dict[str, Any]
) -> YearResult:
    """
    Validates simulation results for Epic 11.5 acceptance criteria.
    Enhanced with strict validation per Epic June 19 E1.
    """
    try:
        # Apply strict validation first
        assert_year_complete(context, year)

        conn = duckdb.connect(str(DB_PATH))

        # Force a fresh connection and ensure we see the latest data
        conn.execute("PRAGMA enable_progress_bar=false")

        # DIAGNOSTIC: List all available simulation_year values in fct_workforce_snapshot
        context.log.info("🔍 DIAGNOSTIC: Checking available years in fct_workforce_snapshot")
        available_years = conn.execute(
            """
            SELECT DISTINCT simulation_year, COUNT(*) as record_count
            FROM fct_workforce_snapshot
            GROUP BY simulation_year
            ORDER BY simulation_year
            """
        ).fetchall()
        context.log.info(f"  Available years in fct_workforce_snapshot: {available_years}")

        # DIAGNOSTIC: Also check for specific employment statuses in previous year
        if year > 2025:
            prev_year_status_breakdown = conn.execute(
                """
                SELECT
                    employment_status,
                    COUNT(*) as count,
                    COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_count
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
                GROUP BY employment_status
                """,
                [year - 1]
            ).fetchall()
            context.log.info(f"  Year {year - 1} status breakdown: {prev_year_status_breakdown}")

        # Get workforce metrics from the snapshot table (must exist per assert_year_complete)
        workforce_metrics = conn.execute(
            """
            SELECT
                COUNT(*) as total_workforce,
                COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
                COUNT(CASE WHEN employment_status = 'terminated' THEN 1 END) as terminated_employees
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
        """,
            [year],
        ).fetchone()

        # Get event metrics
        event_metrics = conn.execute(
            """
            SELECT
                event_type,
                COUNT(*) as event_count
            FROM fct_yearly_events
            WHERE simulation_year = ?
            GROUP BY event_type
        """,
            [year],
        ).fetchall()

        # Convert to dict for easier access
        events_dict = {event_type: count for event_type, count in event_metrics}

        # Calculate growth rate (both snapshot and events guaranteed to exist)
        current_active = workforce_metrics[1]

        if year == 2025:
            # Compare to baseline
            baseline_count = conn.execute(
                """
                SELECT COUNT(*) FROM int_baseline_workforce
                WHERE employment_status = 'active'
            """
            ).fetchone()[0]
            previous_active = baseline_count
            context.log.info(f"🔍 DIAGNOSTIC: Year {year} - Using baseline as previous (count: {baseline_count})")
        else:
            # DIAGNOSTIC: Log the exact query and parameters being used
            query_year = year - 1
            context.log.info(f"🔍 DIAGNOSTIC: Querying previous year snapshot for year {query_year}")
            context.log.info(f"  Query: SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = {query_year} AND employment_status = 'active'")

            # Compare to previous year snapshot (guaranteed to exist)
            previous_active = conn.execute(
                """
                SELECT COUNT(*)
                FROM fct_workforce_snapshot
                WHERE simulation_year = ? AND employment_status = 'active'
            """,
                [year - 1],
            ).fetchone()[0]

            # DIAGNOSTIC: Additional query to understand the data
            if previous_active == 0:
                context.log.warning(f"⚠️ DIAGNOSTIC: Previous year {query_year} shows 0 active employees!")
                # Check if any data exists for previous year
                prev_year_data = conn.execute(
                    """
                    SELECT employment_status, COUNT(*) as count
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                    GROUP BY employment_status
                    """,
                    [year - 1]
                ).fetchall()
                context.log.info(f"  Previous year workforce breakdown: {prev_year_data}")

                # Check int_workforce_previous_year model
                context.log.info(f"🔍 DIAGNOSTIC: Checking int_workforce_previous_year for year {year}")
                int_prev_count = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM int_workforce_previous_year
                    WHERE simulation_year = ?
                    """,
                    [year]
                ).fetchone()[0]
                context.log.info(f"  int_workforce_previous_year count: {int_prev_count}")

                # WORKAROUND: Use int_workforce_previous_year as fallback for previous year count
                if int_prev_count > 0:
                    context.log.info(f"🔄 WORKAROUND: Using int_workforce_previous_year count ({int_prev_count}) as previous year baseline")
                    previous_active = int_prev_count
                else:
                    # If both sources show 0, there's a serious data integrity issue
                    context.log.error(f"❌ CRITICAL: Both fct_workforce_snapshot and int_workforce_previous_year show 0 employees for year transition")
                    # As a last resort, check if we can find any data at all
                    total_snapshot_records = conn.execute(
                        "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                        [year - 1]
                    ).fetchone()[0]
                    context.log.error(f"   Total records in fct_workforce_snapshot for year {year - 1}: {total_snapshot_records}")

                    if total_snapshot_records > 0:
                        # There's data but all employees are terminated - use terminated count as baseline
                        terminated_count = conn.execute(
                            "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ? AND employment_status = 'terminated'",
                            [year - 1]
                        ).fetchone()[0]
                        context.log.warning(f"   Found {terminated_count} terminated employees - using as baseline with warning")
                        previous_active = terminated_count  # This will create a growth calculation issue, but better than division by zero

        growth_rate = (
            (current_active - previous_active) / previous_active
            if previous_active > 0
            else 0
        )

        # Validation checks
        validation_passed = True

        # Check that terminations occurred (including new hire terminations)
        total_terminations = events_dict.get("termination", 0)
        if total_terminations == 0:
            context.log.warning(f"No terminations found for year {year}")
            validation_passed = False

        # Get detailed workforce breakdown
        workforce_breakdown = conn.execute(
            """
            SELECT
                detailed_status_code,
                COUNT(*) as count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
            GROUP BY detailed_status_code
            ORDER BY detailed_status_code
        """,
            [year],
        ).fetchall()

        # Get detailed event breakdown - fixed to use correct termination source
        detailed_events = conn.execute(
            """
            SELECT
                event_type,
                CASE
                    WHEN event_type = 'termination' AND event_category = 'experienced_termination' THEN 'experienced'
                    WHEN event_type = 'termination' AND event_category = 'new_hire_termination' THEN 'new_hire'
                    WHEN event_type = 'termination' AND employee_id LIKE 'NH_%' THEN 'new_hire'
                    WHEN event_type = 'hire' THEN 'new_hire'
                    ELSE 'other'
                END as employee_category,
                COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year = ?
            GROUP BY event_type, employee_category
            ORDER BY event_type, employee_category
        """,
            [year],
        ).fetchall()

        # Calculate detailed metrics
        total_hires = events_dict.get("hire", 0)
        experienced_terminations = 0
        new_hire_terminations = 0

        for event_type, category, count in detailed_events:
            if event_type == "termination":
                if category == "experienced":
                    experienced_terminations += count
                elif category == "new_hire":
                    new_hire_terminations += count

        net_new_hires = total_hires - new_hire_terminations

        # Enhanced logging with detailed breakdown
        context.log.info(f"Year {year} detailed breakdown:")
        context.log.info(f"  Starting active: {previous_active}")
        context.log.info(f"  Experienced terminations: {experienced_terminations}")
        context.log.info(f"  Total new hires: {total_hires}")
        context.log.info(f"  New hire terminations: {new_hire_terminations}")
        context.log.info(f"  Net new hires: {net_new_hires}")
        context.log.info(f"  Ending active: {current_active}")
        context.log.info(f"  Net change: {current_active - previous_active}")
        context.log.info(
            f"  Growth rate: {growth_rate:.1%} (target: {config['target_growth_rate']:.1%})"
        )

        # Log workforce status breakdown
        context.log.info("  Workforce status breakdown:")
        for status, count in workforce_breakdown:
            context.log.info(f"    {status}: {count}")

        # Log validation formula check - aligned with dbt target_ending_workforce_count
        # Use the same formula as dbt: ROUND(workforce_count * (1 + target_growth_rate))
        expected_ending_dbt = round(
            previous_active * (1 + config["target_growth_rate"])
        )

        # Allow small variance due to discrete employee counts and rounding
        variance_threshold = 2
        if abs(expected_ending_dbt - current_active) > variance_threshold:
            context.log.warning(
                f"  Growth target variance: target {expected_ending_dbt}, actual {current_active} (diff: {current_active - expected_ending_dbt})"
            )
        else:
            context.log.info(
                f"  ✅ Growth target achieved: target {expected_ending_dbt}, actual {current_active}"
            )

        conn.close()

        return YearResult(
            year=year,
            success=True,
            active_employees=current_active,
            total_terminations=total_terminations,
            experienced_terminations=experienced_terminations,
            new_hire_terminations=new_hire_terminations,
            total_hires=events_dict.get("hire", 0),
            growth_rate=growth_rate,
            validation_passed=validation_passed,
        )

    except Exception as e:
        context.log.error(f"Validation failed for year {year}: {e}")
        return YearResult(
            year=year,
            success=False,
            active_employees=0,
            total_terminations=0,
            experienced_terminations=0,
            new_hire_terminations=0,
            total_hires=0,
            growth_rate=0.0,
            validation_passed=False,
        )
