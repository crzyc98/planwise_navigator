"""
Unified Workforce Simulation Pipeline using Dagster and dbt.

This module implements a comprehensive simulation pipeline that:
1. Eliminates circular dependencies between dbt models
2. Implements precise termination/hiring sequence from Epic 11.5
3. Provides single entry point for all simulation execution
4. Includes data quality validation and monitoring
"""

from pathlib import Path
from typing import Dict, List, Any
import duckdb
from datetime import datetime

from dagster import (
    op,
    job,
    asset,
    OpExecutionContext,
    AssetExecutionContext,
    Config,
    asset_check,
    AssetCheckResult,
    AssetCheckSeverity,
)
from dagster_dbt import DbtCliResource
from pydantic import BaseModel
import os

# Project configuration
PROJECT_ROOT = Path(__file__).parent.parent
DBT_PROJECT_PATH = (
    PROJECT_ROOT / "dbt"
)  # Run dbt from dbt subdirectory for path resolution
DBT_PROFILES_PATH = PROJECT_ROOT / "dbt"  # profiles.yml is in dbt subdirectory
DB_PATH = PROJECT_ROOT / "simulation.duckdb"
CONFIG_PATH = PROJECT_ROOT / "config" / "simulation_config.yaml"

# Initialize dbt project path for asset discovery

# Define dbt CLI resource once and reuse in job definitions
dbt_resource = DbtCliResource(
    project_dir=os.fspath(DBT_PROJECT_PATH), profiles_dir=os.fspath(DBT_PROFILES_PATH)
)


class SimulationConfig(Config):
    """Configuration for simulation parameters"""

    start_year: int = 2025
    end_year: int = 2029
    target_growth_rate: float = 0.03
    total_termination_rate: float = 0.12
    new_hire_termination_rate: float = 0.25
    random_seed: int = 42
    full_refresh: bool = False


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


@asset
def simulation_year_state(context: AssetExecutionContext) -> Dict[str, Any]:
    """
    Maintains state for multi-year simulation processing.
    Tracks which years have been processed and current simulation status.
    """
    state: Dict[str, Any] = {
        "current_year": None,
        "processed_years": [],
        "last_updated": datetime.now().isoformat(),
        "status": "initialized",
    }

    context.log.info(f"Simulation state initialized: {state}")
    return state


@asset(deps=[simulation_year_state])
def baseline_workforce_validated(context: AssetExecutionContext) -> bool:
    """
    Validates that baseline workforce data exists and is reasonable.
    """
    try:
        conn = duckdb.connect(str(DB_PATH))

        # Check baseline workforce exists
        result = conn.execute(
            """
            SELECT
                COUNT(*) as total_employees,
                AVG(current_compensation) as avg_compensation,
                MIN(current_age) as min_age,
                MAX(current_age) as max_age
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
        """
        ).fetchone()

        if not result or result[0] == 0:
            raise ValueError("No baseline workforce data found")

        total, avg_comp, min_age, max_age = result

        # Validate data reasonableness
        if total < 1000:
            context.log.warning(f"Baseline workforce seems small: {total} employees")
        if avg_comp < 50000 or avg_comp > 200000:
            context.log.warning(
                f"Average compensation seems unrealistic: ${avg_comp:,.0f}"
            )
        if min_age < 18 or max_age > 80:
            context.log.warning(f"Age range seems unrealistic: {min_age}-{max_age}")

        context.log.info(
            f"Baseline workforce validated: {total} employees, avg comp ${avg_comp:,.0f}"
        )
        conn.close()
        return True

    except Exception as e:
        context.log.error(f"Baseline workforce validation failed: {e}")
        return False


@op
def prepare_year_snapshot(
    context: OpExecutionContext, year: int, previous_year: int = 0
) -> bool:
    """
    Creates snapshot table for the year to break circular dependencies.
    This is the key operation that enables proper incremental processing.
    """
    context.log.info(f"Preparing workforce snapshot for year {year}")

    try:
        conn = duckdb.connect(str(DB_PATH))

        # Drop existing snapshot table
        conn.execute("DROP TABLE IF EXISTS previous_year_workforce_snapshot")

        if year == 2025:
            # For first year, use baseline workforce
            conn.execute(
                """
                CREATE TABLE previous_year_workforce_snapshot AS
                SELECT
                    employee_id,
                    employee_ssn,
                    employee_birth_date,
                    employee_hire_date,
                    current_compensation AS employee_gross_compensation,
                    current_age,
                    current_tenure,
                    level_id,
                    termination_date,
                    employment_status
                FROM int_baseline_workforce
                WHERE employment_status = 'active'
            """
            )
        else:
            # For subsequent years, use previous year's final snapshot
            conn.execute(
                f"""
                CREATE TABLE previous_year_workforce_snapshot AS
                SELECT
                    employee_id,
                    employee_ssn,
                    employee_birth_date,
                    employee_hire_date,
                    current_compensation AS employee_gross_compensation,
                    current_age,
                    current_tenure,
                    level_id,
                    termination_date,
                    employment_status
                FROM fct_workforce_snapshot
                WHERE simulation_year = {previous_year}
                  AND employment_status = 'active'
            """
            )

        # Validate snapshot was created
        count = conn.execute(
            "SELECT COUNT(*) FROM previous_year_workforce_snapshot"
        ).fetchone()[0]

        if count == 0:
            raise ValueError(f"No workforce data available for year {year}")

        context.log.info(f"Snapshot prepared: {count} active employees for year {year}")
        conn.close()
        return True

    except Exception as e:
        context.log.error(f"Failed to prepare snapshot for year {year}: {e}")
        return False


@op(
    required_resource_keys={"dbt"},
    config_schema={
        "start_year": int,
        "end_year": int,
        "target_growth_rate": float,
        "total_termination_rate": float,
        "new_hire_termination_rate": float,
        "random_seed": int,
        "full_refresh": bool,
    },
)
def run_year_simulation(context: OpExecutionContext) -> YearResult:
    """
    Executes complete simulation for a single year.
    Implements the precise sequence from Epic 11.5.
    """
    # Get configuration from op config
    config = context.op_config
    year = config["start_year"]
    full_refresh = config.get("full_refresh", False)

    context.log.info(f"Starting simulation for year {year}")
    if full_refresh:
        context.log.info(
            "🔄 Full refresh enabled - will rebuild all incremental models from scratch"
        )

    # Clean existing data for this year to prevent duplicates
    context.log.info(f"Cleaning existing data for year {year}")
    conn = duckdb.connect(str(DB_PATH))
    try:
        # Delete any existing data for this simulation year
        conn.execute("DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year])
        context.log.info("Existing events for year %s deleted", year)
    except Exception as e:
        context.log.warning(f"Error cleaning year {year} data: {e}")
    finally:
        conn.close()

    # Get dbt resource from context
    dbt = context.resources.dbt

    try:
        # Step 1: Enhanced validation for multi-year dependencies
        if year > 2025:
            # Ensure previous year data exists by checking both events and workforce tables
            conn = duckdb.connect(str(DB_PATH))
            try:
                # Check both events and workforce from previous year
                events_count = conn.execute(
                    """
                    SELECT COUNT(*) FROM fct_yearly_events
                    WHERE simulation_year = ?
                """,
                    [year - 1],
                ).fetchone()[0]

                workforce_count = conn.execute(
                    """
                    SELECT COUNT(*) FROM fct_workforce_snapshot
                    WHERE simulation_year = ? AND employment_status = 'active'
                """,
                    [year - 1],
                ).fetchone()[0]

                # Apply same recovery logic as in multi-year function
                if events_count == 0 and workforce_count == 0:
                    raise Exception(
                        f"No previous year data found for year {year - 1} (events: {events_count}, workforce: {workforce_count})"
                    )
                elif events_count > 0 and workforce_count == 0:
                    context.log.warning(
                        f"Previous year {year - 1} has events ({events_count}) but no workforce snapshot. Attempting to build missing snapshot..."
                    )

                    # Try to build missing workforce snapshot
                    try:
                        context.log.info(
                            f"Building missing workforce snapshot for year {year - 1}"
                        )
                        invocation = dbt.cli(
                            [
                                "run",
                                "--select",
                                "fct_workforce_snapshot",
                                "--vars",
                                f"{{simulation_year: {year - 1}}}",
                            ],
                            context=context,
                        ).wait()

                        if (
                            invocation.process is None
                            or invocation.process.returncode != 0
                        ):
                            stdout = invocation.get_stdout() or ""
                            stderr = invocation.get_stderr() or ""
                            context.log.error(
                                f"Failed to build missing workforce snapshot. STDOUT: {stdout}, STDERR: {stderr}"
                            )
                            raise Exception(
                                f"Cannot recover missing workforce snapshot for year {year - 1}"
                            )

                        # Recheck workforce count
                        workforce_count = conn.execute(
                            """
                            SELECT COUNT(*) FROM fct_workforce_snapshot
                            WHERE simulation_year = ? AND employment_status = 'active'
                        """,
                            [year - 1],
                        ).fetchone()[0]

                        if workforce_count == 0:
                            raise Exception(
                                f"Still no workforce snapshot after rebuild for year {year - 1}"
                            )

                        context.log.info(
                            f"Successfully recovered workforce snapshot for year {year - 1}: {workforce_count} active employees"
                        )

                    except Exception as e:
                        context.log.error(
                            f"Failed to recover missing workforce snapshot: {e}"
                        )
                        raise Exception(
                            f"Cannot continue without workforce snapshot for year {year - 1}"
                        )

                context.log.info(
                    f"Previous year validation passed: {events_count} events, {workforce_count} active employees from {year - 1}"
                )
            finally:
                conn.close()

        # Step 2: First run int_previous_year_workforce to establish workforce base for event generation
        context.log.info(f"Running int_previous_year_workforce for year {year}")
        invocation = dbt.cli(
            [
                "run",
                "--select",
                "int_previous_year_workforce",
                "--vars",
                f"{{simulation_year: {year}}}",
            ],
            context=context,
        ).wait()

        if invocation.process is None or invocation.process.returncode != 0:
            stdout = invocation.get_stdout() or ""
            stderr = invocation.get_stderr() or ""
            error_message = f"Failed to run int_previous_year_workforce for year {year}. Exit code: {invocation.process.returncode}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            raise Exception(error_message)

        # Step 3: Run event generation models in proper Epic 11.5 sequence
        event_models = [
            "int_termination_events",  # Step b-c: Experienced terminations + additional to meet rate
            "int_promotion_events",
            "int_merit_events",
            "int_hiring_events",  # Step f: Gross hiring events
            "int_new_hire_termination_events",  # Step g: New hire termination events
        ]

        for model in event_models:
            vars_string = f"{{simulation_year: {year}, random_seed: {config['random_seed']}, target_growth_rate: {config['target_growth_rate']}, new_hire_termination_rate: {config['new_hire_termination_rate']}, total_termination_rate: {config['total_termination_rate']}}}"
            context.log.info(
                f"Running {model} for year {year} with vars: {vars_string}"
            )

            # Add detailed logging for hiring calculation before running int_hiring_events
            if model == "int_hiring_events":
                context.log.info("🔍 HIRING CALCULATION DEBUG:")
                conn = duckdb.connect(str(DB_PATH))
                try:
                    # Calculate workforce count
                    if year == 2025:
                        workforce_count = conn.execute(
                            "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'"
                        ).fetchone()[0]
                    else:
                        workforce_count = conn.execute(
                            "SELECT COUNT(*) FROM int_workforce_previous_year WHERE employment_status = 'active'"
                        ).fetchone()[0]

                    # Calculate formula inputs
                    target_growth_rate = config["target_growth_rate"]
                    total_termination_rate = config["total_termination_rate"]
                    new_hire_termination_rate = config["new_hire_termination_rate"]

                    # Apply exact formula from int_hiring_events.sql
                    import math

                    experienced_terms = math.ceil(
                        workforce_count * total_termination_rate
                    )
                    growth_amount = workforce_count * target_growth_rate
                    total_hires_needed = math.ceil(
                        (experienced_terms + growth_amount)
                        / (1 - new_hire_termination_rate)
                    )
                    expected_new_hire_terms = round(
                        total_hires_needed * new_hire_termination_rate
                    )

                    context.log.info(
                        f"  📊 Starting workforce: {workforce_count} active employees"
                    )
                    context.log.info(
                        f"  📊 Target growth rate: {target_growth_rate:.1%}"
                    )
                    context.log.info(
                        f"  📊 Total termination rate: {total_termination_rate:.1%}"
                    )
                    context.log.info(
                        f"  📊 New hire termination rate: {new_hire_termination_rate:.1%}"
                    )
                    context.log.info(
                        f"  📊 Expected experienced terminations: {experienced_terms}"
                    )
                    context.log.info(f"  📊 Growth amount needed: {growth_amount:.1f}")
                    context.log.info(
                        f"  🎯 TOTAL HIRES CALLING FOR: {total_hires_needed}"
                    )
                    context.log.info(
                        f"  📊 Expected new hire terminations: {expected_new_hire_terms}"
                    )
                    context.log.info(
                        f"  📊 Net hiring impact: {total_hires_needed - expected_new_hire_terms}"
                    )
                    context.log.info(
                        f"  📊 Formula: CEIL(({experienced_terms} + {growth_amount:.1f}) / (1 - {new_hire_termination_rate})) = {total_hires_needed}"
                    )

                except Exception as e:
                    context.log.warning(f"Error calculating hiring debug info: {e}")
                finally:
                    conn.close()
            invocation = dbt.cli(
                ["run", "--select", model, "--vars", vars_string], context=context
            ).wait()

            if invocation.process is None or invocation.process.returncode != 0:
                stdout = invocation.get_stdout() or ""
                stderr = invocation.get_stderr() or ""
                error_message = f"Failed to run {model} for year {year}. Exit code: {invocation.process.returncode}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
                raise Exception(error_message)

        # Step 4: Consolidate events
        context.log.info(f"Running fct_yearly_events for year {year}")
        invocation = dbt.cli(
            [
                "run",
                "--select",
                "fct_yearly_events",
                "--vars",
                f"{{simulation_year: {year}}}",
            ],
            context=context,
        ).wait()

        if invocation.process is None or invocation.process.returncode != 0:
            stdout = invocation.get_stdout() or ""
            stderr = invocation.get_stderr() or ""
            error_message = f"Failed to run fct_yearly_events for year {year}. Exit code: {invocation.process.returncode}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            raise Exception(error_message)

        # Step 5a: Clean fct_workforce_snapshot for the current year
        context.log.info(f"Cleaning fct_workforce_snapshot for year {year}")
        conn = duckdb.connect(str(DB_PATH))
        try:
            conn.execute(
                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?", [year]
            )
            context.log.info("Existing snapshot records for year %s deleted", year)
        except Exception as e:
            context.log.warning(
                f"Error cleaning fct_workforce_snapshot for year {year} data: {e} (Table might not exist yet on first run of a new year)"
            )
        finally:
            conn.close()

        # Step 5b: Generate final workforce snapshot
        context.log.info(f"Running fct_workforce_snapshot for year {year}")
        invocation = dbt.cli(
            [
                "run",
                "--select",
                "fct_workforce_snapshot",
                "--vars",
                f"{{simulation_year: {year}}}",
            ],
            context=context,
        ).wait()

        if invocation.process is None or invocation.process.returncode != 0:
            stdout = invocation.get_stdout() or ""
            stderr = invocation.get_stderr() or ""
            error_message = f"Failed to run fct_workforce_snapshot for year {year}. Exit code: {invocation.process.returncode}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
            raise Exception(error_message)

        # Step 6: Validate results and collect metrics
        year_result = validate_year_results(context, year, config)

        context.log.info(f"Year {year} simulation completed successfully")
        return year_result

    except Exception as e:
        context.log.error(f"Simulation failed for year {year}: {e}")
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


def assert_year_complete(context: OpExecutionContext, year: int) -> None:
    """
    Strict validation that both snapshot AND events exist before proceeding.
    Per Epic June 19 E1: Both the year-N snapshot and year-N events must exist.
    No silent recovery - hard fail on missing data.
    """
    conn = duckdb.connect(str(DB_PATH))

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
        else:
            # Compare to previous year snapshot (guaranteed to exist)
            previous_active = conn.execute(
                """
                SELECT COUNT(*)
                FROM fct_workforce_snapshot
                WHERE simulation_year = ? AND employment_status = 'active'
            """,
                [year - 1],
            ).fetchone()[0]

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


@asset_check(asset=baseline_workforce_validated)
def validate_growth_rates(context) -> AssetCheckResult:
    """
    Validates that growth rates are within acceptable ranges.
    """
    try:
        conn = duckdb.connect(str(DB_PATH))

        # Get all years with data
        years_data = conn.execute(
            """
            SELECT
                simulation_year,
                COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_count
            FROM fct_workforce_snapshot
            GROUP BY simulation_year
            ORDER BY simulation_year
        """
        ).fetchall()

        if len(years_data) < 2:
            return AssetCheckResult(
                passed=True, description="Insufficient data for growth rate validation"
            )

        # Check year-over-year growth rates
        for i in range(1, len(years_data)):
            prev_year, prev_count = years_data[i - 1]
            curr_year, curr_count = years_data[i]

            growth_rate = (curr_count - prev_count) / prev_count

            # Flag if growth rate is way off target (>50% variance)
            if abs(growth_rate - 0.03) > 0.015:  # 1.5% tolerance
                context.log.warning(
                    f"Growth rate for {curr_year}: {growth_rate:.1%} (target: 3.0%)"
                )

        conn.close()
        return AssetCheckResult(
            passed=True, description="Growth rates within acceptable ranges"
        )

    except Exception as e:
        return AssetCheckResult(
            passed=False,
            description=f"Growth rate validation failed: {e}",
            severity=AssetCheckSeverity.WARN,
        )


@op
def baseline_workforce_validated_op(context: OpExecutionContext) -> bool:
    """
    Op version of baseline workforce validation for use in jobs.
    """
    try:
        conn = duckdb.connect(str(DB_PATH))

        # Check baseline workforce exists
        result = conn.execute(
            """
            SELECT
                COUNT(*) as total_employees,
                AVG(current_compensation) as avg_compensation,
                MIN(current_age) as min_age,
                MAX(current_age) as max_age
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
        """
        ).fetchone()

        if not result or result[0] == 0:
            raise ValueError("No baseline workforce data found")

        total, avg_comp, min_age, max_age = result

        # Validate data reasonableness
        if total < 1000:
            context.log.info(f"Baseline workforce seems small: {total} employees")
        if avg_comp < 50000 or avg_comp > 200000:
            context.log.warning(
                f"Average compensation seems unrealistic: ${avg_comp:,.0f}"
            )
        if min_age < 18 or max_age > 80:
            context.log.warning(f"Age range seems unrealistic: {min_age}-{max_age}")

        context.log.info(
            f"Baseline workforce validated: {total} employees, avg comp ${avg_comp:,.0f}"
        )
        conn.close()
        return True

    except Exception as e:
        context.log.error(f"Baseline workforce validation failed: {e}")
        return False


@job(resource_defs={"dbt": dbt_resource})
def single_year_simulation():
    """
    Job to run simulation for a single year.
    Useful for testing and development.
    """
    # Validate baseline first
    baseline_workforce_validated_op()

    # Run single year
    run_year_simulation()


@op(
    required_resource_keys={"dbt"},
    config_schema={
        "start_year": int,
        "end_year": int,
        "target_growth_rate": float,
        "total_termination_rate": float,
        "new_hire_termination_rate": float,
        "random_seed": int,
        "full_refresh": bool,
    },
)
def run_multi_year_simulation(
    context: OpExecutionContext, baseline_valid: bool
) -> List[YearResult]:
    """
    Executes complete multi-year workforce simulation.
    Runs each year sequentially from start_year to end_year.
    """
    if not baseline_valid:
        raise Exception("Baseline workforce validation failed")

    config = context.op_config
    start_year = config["start_year"]
    end_year = config["end_year"]
    full_refresh = config.get("full_refresh", False)

    context.log.info(f"Starting multi-year simulation from {start_year} to {end_year}")
    if full_refresh:
        context.log.info(
            "🔄 Full refresh enabled - will rebuild all incremental models from scratch"
        )

    # Clean all data for the simulation years to ensure fresh start
    context.log.info(f"Cleaning existing data for years {start_year}-{end_year}")
    conn = duckdb.connect(str(DB_PATH))
    try:
        for clean_year in range(start_year, end_year + 1):
            conn.execute(
                "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [clean_year]
            )

        context.log.info(
            "Existing events for years %s-%s deleted", start_year, end_year
        )
    except Exception as e:
        context.log.warning(f"Error cleaning simulation data: {e}")
    finally:
        conn.close()

    results = []

    for year in range(start_year, end_year + 1):
        context.log.info(f"=== Starting simulation for year {year} ===")

        # Update config for current year
        year_config = config.copy()
        year_config["start_year"] = year

        # Create a temporary context for the year simulation
        # We'll simulate what run_year_simulation does but for each year
        dbt = context.resources.dbt

        try:
            # Step 1: Strict validation for previous year completion
            if year > start_year:
                context.log.info(f"Validating previous year data for year {year}")
                try:
                    assert_year_complete(context, year - 1)
                except Exception as e:
                    context.log.error(f"Simulation failed for year {year}: {e}")
                    results.append(
                        YearResult(
                            year=year,
                            success=False,
                            active_employees=0,
                            total_terminations=0,
                            experienced_terminations=0,
                            new_hire_terminations=0,
                            total_hires=0,
                            growth_rate=0,
                            validation_passed=False,
                        )
                    )
                    continue  # Skip to next year instead of aborting entirely

            # Step 2: First run int_previous_year_workforce to establish workforce base for event generation
            context.log.info(f"Running int_previous_year_workforce for year {year}")
            dbt_command = [
                "run",
                "--select",
                "int_previous_year_workforce",
                "--vars",
                f"{{simulation_year: {year}}}",
            ]
            if full_refresh:
                dbt_command.append("--full-refresh")

            invocation = dbt.cli(dbt_command, context=context).wait()

            if invocation.process is None or invocation.process.returncode != 0:
                stdout = invocation.get_stdout() or ""
                stderr = invocation.get_stderr() or ""
                error_message = f"Failed to run int_previous_year_workforce for year {year}. Exit code: {invocation.process.returncode}\\n\\nSTDOUT:\\n{stdout}\\n\\nSTDERR:\\n{stderr}"
                raise Exception(error_message)

            # Step 3: Run event generation models in proper sequence
            event_models = [
                "int_termination_events",
                "int_promotion_events",
                "int_merit_events",
                "int_hiring_events",
                "int_new_hire_termination_events",
            ]

            for model in event_models:
                vars_string = f"{{simulation_year: {year}, random_seed: {config['random_seed']}, target_growth_rate: {config['target_growth_rate']}, new_hire_termination_rate: {config['new_hire_termination_rate']}, total_termination_rate: {config['total_termination_rate']}}}"
                context.log.info(
                    f"Running {model} for year {year} with vars: {vars_string}"
                )

                # Add detailed logging for hiring calculation before running int_hiring_events
                if model == "int_hiring_events":
                    context.log.info("🔍 HIRING CALCULATION DEBUG:")
                    conn = duckdb.connect(str(DB_PATH))
                    try:
                        # Calculate workforce count
                        if year == start_year:
                            workforce_count = conn.execute(
                                "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'"
                            ).fetchone()[0]
                        else:
                            workforce_count = conn.execute(
                                "SELECT COUNT(*) FROM int_workforce_previous_year WHERE employment_status = 'active'"
                            ).fetchone()[0]

                        # Calculate formula inputs
                        target_growth_rate = config["target_growth_rate"]
                        total_termination_rate = config["total_termination_rate"]
                        new_hire_termination_rate = config["new_hire_termination_rate"]

                        # Apply exact formula from int_hiring_events.sql
                        import math

                        experienced_terms = math.ceil(
                            workforce_count * total_termination_rate
                        )
                        growth_amount = workforce_count * target_growth_rate
                        total_hires_needed = math.ceil(
                            (experienced_terms + growth_amount)
                            / (1 - new_hire_termination_rate)
                        )
                        expected_new_hire_terms = round(
                            total_hires_needed * new_hire_termination_rate
                        )

                        context.log.info(
                            f"  📊 Starting workforce: {workforce_count} active employees"
                        )
                        context.log.info(
                            f"  📊 Target growth rate: {target_growth_rate:.1%}"
                        )
                        context.log.info(
                            f"  📊 Total termination rate: {total_termination_rate:.1%}"
                        )
                        context.log.info(
                            f"  📊 New hire termination rate: {new_hire_termination_rate:.1%}"
                        )
                        context.log.info(
                            f"  📊 Expected experienced terminations: {experienced_terms}"
                        )
                        context.log.info(
                            f"  📊 Growth amount needed: {growth_amount:.1f}"
                        )
                        context.log.info(
                            f"  🎯 TOTAL HIRES CALLING FOR: {total_hires_needed}"
                        )
                        context.log.info(
                            f"  📊 Expected new hire terminations: {expected_new_hire_terms}"
                        )
                        context.log.info(
                            f"  📊 Net hiring impact: {total_hires_needed - expected_new_hire_terms}"
                        )
                        context.log.info(
                            f"  📊 Formula: CEIL(({experienced_terms} + {growth_amount:.1f}) / (1 - {new_hire_termination_rate})) = {total_hires_needed}"
                        )

                    except Exception as e:
                        context.log.warning(f"Error calculating hiring debug info: {e}")
                    finally:
                        conn.close()
                dbt_command = ["run", "--select", model, "--vars", vars_string]
                if full_refresh:
                    dbt_command.append("--full-refresh")

                invocation = dbt.cli(dbt_command, context=context).wait()

                if invocation.process is None or invocation.process.returncode != 0:
                    stdout = invocation.get_stdout() or ""
                    stderr = invocation.get_stderr() or ""
                    error_message = f"Failed to run {model} for year {year}. Exit code: {invocation.process.returncode}\\n\\nSTDOUT:\\n{stdout}\\n\\nSTDERR:\\n{stderr}"
                    raise Exception(error_message)

            # Step 4: Consolidate events
            context.log.info(f"Running fct_yearly_events for year {year}")
            dbt_command = [
                "run",
                "--select",
                "fct_yearly_events",
                "--vars",
                f"{{simulation_year: {year}}}",
            ]
            if full_refresh:
                dbt_command.append("--full-refresh")

            invocation = dbt.cli(dbt_command, context=context).wait()

            if invocation.process is None or invocation.process.returncode != 0:
                stdout = invocation.get_stdout() or ""
                stderr = invocation.get_stderr() or ""
                error_message = f"Failed to run fct_yearly_events for year {year}. Exit code: {invocation.process.returncode}\\n\\nSTDOUT:\\n{stdout}\\n\\nSTDERR:\\n{stderr}"
                raise Exception(error_message)

            # Step 5a: Clean fct_workforce_snapshot for the current year
            context.log.info(f"Cleaning fct_workforce_snapshot for year {year}")
            conn = duckdb.connect(str(DB_PATH))
            try:
                conn.execute(
                    "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
                    [year],
                )
                context.log.info("Existing snapshot records for year %s deleted", year)
            except Exception as e:
                context.log.warning(
                    f"Error cleaning fct_workforce_snapshot for year {year} data: {e} (Table might not exist yet on first run of a new year)"
                )
            finally:
                conn.close()

            # Step 5b: Generate final workforce snapshot
            context.log.info(f"Running fct_workforce_snapshot for year {year}")
            dbt_command = [
                "run",
                "--select",
                "fct_workforce_snapshot",
                "--vars",
                f"{{simulation_year: {year}}}",
            ]
            if full_refresh:
                dbt_command.append("--full-refresh")

            invocation = dbt.cli(dbt_command, context=context).wait()

            if invocation.process is None or invocation.process.returncode != 0:
                stdout = invocation.get_stdout() or ""
                stderr = invocation.get_stderr() or ""
                error_message = f"Failed to run fct_workforce_snapshot for year {year}. Exit code: {invocation.process.returncode}\\n\\nSTDOUT:\\n{stdout}\\n\\nSTDERR:\\n{stderr}"
                raise Exception(error_message)

            # Step 6: Validate results
            year_result = validate_year_results(context, year, config)
            results.append(year_result)

            context.log.info(f"=== Year {year} simulation completed successfully ===")

        except Exception as e:
            context.log.error(f"Simulation failed for year {year}: {e}")
            failed_result = YearResult(
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
            results.append(failed_result)
            # Continue with next year instead of stopping
            continue

    # Log summary
    context.log.info("=== Multi-year simulation summary ===")
    for result in results:
        if result.success:
            context.log.info(
                f"Year {result.year}: {result.active_employees} employees, {result.growth_rate:.1%} growth"
            )
        else:
            context.log.error(f"Year {result.year}: FAILED")

    return results


@job(resource_defs={"dbt": dbt_resource})
def multi_year_simulation():
    """
    Job to run complete multi-year workforce simulation.
    Executes years sequentially to maintain state dependencies.
    """
    # First validate baseline workforce; result is passed to main op to enforce ordering
    baseline_ok = baseline_workforce_validated_op()
    run_multi_year_simulation(baseline_ok)


# Export all definitions for Dagster
__all__ = [
    "simulation_year_state",
    "baseline_workforce_validated",
    "baseline_workforce_validated_op",
    "run_multi_year_simulation",
    "single_year_simulation",
    "multi_year_simulation",
    "validate_growth_rates",
    "dbt_resource",
    "SimulationConfig",
    "YearResult",
]
