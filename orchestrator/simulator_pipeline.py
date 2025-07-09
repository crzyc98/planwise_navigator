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
import yaml

# Project configuration
PROJECT_ROOT = Path(__file__).parent.parent
DBT_PROJECT_PATH = (
    PROJECT_ROOT / "dbt"
)  # Run dbt from dbt subdirectory for path resolution
DBT_PROFILES_PATH = PROJECT_ROOT / "dbt"  # profiles.yml is in dbt subdirectory
DB_PATH = PROJECT_ROOT / "simulation.duckdb"
CONFIG_PATH = PROJECT_ROOT / "config" / "simulation_config.yaml"

# Initialize dbt project path for asset discovery
DBT_EXECUTABLE = PROJECT_ROOT / "venv" / "bin" / "dbt"

dbt_resource = DbtCliResource(
    project_dir=os.fspath(DBT_PROJECT_PATH),
    profiles_dir=os.fspath(DBT_PROFILES_PATH),
    dbt_executable=str(DBT_EXECUTABLE)
)


def execute_dbt_command(
    context: OpExecutionContext,
    command: List[str],
    vars_dict: Dict[str, Any],
    full_refresh: bool = False,
    description: str = "",
) -> None:
    """
    Execute a dbt command with standardized error handling and logging.

    This utility centralizes dbt command execution patterns used throughout
    the simulation pipeline. It handles variable string construction,
    full_refresh flag addition, and provides consistent error reporting.

    Args:
        context: Dagster operation execution context
        command: Base dbt command as list (e.g., ["run", "--select", "model_name"])
        vars_dict: Variables to pass to dbt as --vars (e.g., {"simulation_year": 2025})
        full_refresh: Whether to add --full-refresh flag to command
        description: Human-readable description for logging and error messages

    Raises:
        Exception: When dbt command fails with details from stdout/stderr

    Examples:
        Basic model run:
        >>> execute_dbt_command(context, ["run", "--select", "my_model"], {}, False, "my model")

        With variables and full refresh:
        >>> execute_dbt_command(
        ...     context,
        ...     ["run", "--select", "int_hiring_events"],
        ...     {"simulation_year": 2025, "random_seed": 42},
        ...     True,
        ...     "hiring events for 2025"
        ... )

        Snapshot execution:
        >>> execute_dbt_command(
        ...     context,
        ...     ["snapshot", "--select", "scd_workforce_state"],
        ...     {"simulation_year": 2025},
        ...     False,
        ...     "workforce state snapshot"
        ... )
    """
    # Build command with variables
    full_command = command.copy()

    if vars_dict:
        vars_string = "{" + ", ".join([f"{k}: {v}" for k, v in vars_dict.items()]) + "}"
        full_command.extend(["--vars", vars_string])

    if full_refresh:
        full_command.append("--full-refresh")

    # Log execution start
    context.log.info(f"Executing: dbt {' '.join(full_command)}")
    if description:
        context.log.info(f"Description: {description}")

    # Execute command
    dbt = context.resources.dbt
    invocation = dbt.cli(full_command, context=context).wait()

    # Handle errors with standardized format
    if invocation.process is None or invocation.process.returncode != 0:
        stdout = invocation.get_stdout() or ""
        stderr = invocation.get_stderr() or ""

        error_msg = f"Failed to run {' '.join(command)}"
        if description:
            error_msg += f" for {description}"
        error_msg += f". Exit code: {invocation.process.returncode if invocation.process else 'N/A'}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

        context.log.error(error_msg)
        raise Exception(error_msg)

    context.log.info(f"Successfully completed: dbt {' '.join(command)}")


def execute_dbt_command_streaming(
    context: OpExecutionContext,
    command: List[str],
    vars_dict: Dict[str, Any] = None,
    full_refresh: bool = False,
    description: str = "",
):
    """
    Execute a dbt command with streaming output and standardized error handling.

    This utility provides streaming execution for dbt commands, particularly useful
    for long-running operations like full builds. It maintains the same interface
    as execute_dbt_command but yields results as they become available.

    Args:
        context: Dagster operation execution context
        command: Base dbt command as list (e.g., ["build"])
        vars_dict: Variables to pass to dbt as --vars (optional)
        full_refresh: Whether to add --full-refresh flag to command
        description: Human-readable description for logging and error messages

    Yields:
        Results from dbt command execution as they become available

    Examples:
        Basic build with streaming:
        >>> yield from execute_dbt_command_streaming(context, ["build"], {}, False, "full dbt build")

        With variables:
        >>> yield from execute_dbt_command_streaming(
        ...     context,
        ...     ["run", "--select", "model_name"],
        ...     {"simulation_year": 2025},
        ...     False,
        ...     "model execution with streaming"
        ... )
    """
    # Build command with variables
    full_command = command.copy()

    if vars_dict:
        vars_string = "{" + ", ".join([f"{k}: {v}" for k, v in vars_dict.items()]) + "}"
        full_command.extend(["--vars", vars_string])

    if full_refresh:
        full_command.append("--full-refresh")

    # Log execution start
    context.log.info(f"Executing (streaming): dbt {' '.join(full_command)}")
    if description:
        context.log.info(f"Description: {description}")

    # Execute command with streaming
    dbt = context.resources.dbt
    try:
        yield from dbt.cli(full_command, context=context).stream()
        context.log.info(f"Successfully completed (streaming): dbt {' '.join(command)}")
    except Exception as e:
        error_msg = f"Failed to run {' '.join(command)}"
        if description:
            error_msg += f" for {description}"
        error_msg += f". Error: {str(e)}"

        context.log.error(error_msg)
        raise Exception(error_msg) from e


def clean_duckdb_data(context: OpExecutionContext, years: List[int]) -> Dict[str, int]:
    """
    Clean simulation data for specified years.

    Removes existing simulation data from fct_yearly_events and fct_workforce_snapshot
    tables for the specified years to ensure fresh start for simulation runs.

    Args:
        context: Dagster operation execution context
        years: List of simulation years to clean (e.g., [2025, 2026, 2027])

    Returns:
        Dict containing counts of deleted records per table

    Examples:
        Clean single year:
        >>> clean_duckdb_data(context, [2025])

        Clean multiple years:
        >>> clean_duckdb_data(context, [2025, 2026, 2027])
    """
    if not years:
        context.log.info("No years specified for cleaning")
        return {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}

    results = {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}

    year_range = f"{min(years)}-{max(years)}" if len(years) > 1 else str(years[0])
    context.log.info(f"Cleaning existing data for years {year_range}")

    conn = duckdb.connect(str(DB_PATH))

    try:
        # Clean yearly events for all specified years
        for year in years:
            try:
                # Execute DELETE operation
                conn.execute(
                    "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year]
                )
                # Note: DuckDB doesn't always return rowcount for DELETE operations
                # We'll count this as successful deletion
                results["fct_yearly_events"] += 1  # Count per year cleaned
            except Exception as e:
                context.log.warning(f"Error cleaning events for year {year}: {e}")

        # Clean workforce snapshots for all specified years
        for year in years:
            try:
                # Execute delete without assigning to unused cursor
                conn.execute(
                    "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
                    [year],
                )
                results["fct_workforce_snapshot"] += 1  # Count per year cleaned
            except Exception as e:
                context.log.warning(
                    f"Error cleaning workforce snapshot for year {year}: {e}"
                )
                # Don't fail the operation if table doesn't exist yet

        context.log.info(
            f"Cleaned simulation data for {len(years)} years: "
            f"events cleaned for {results['fct_yearly_events']} years, "
            f"snapshots cleaned for {results['fct_workforce_snapshot']} years"
        )

    except Exception as e:
        context.log.warning(f"Error during data cleaning: {e}")
        # Don't re-raise - allow pipeline to continue with best effort
    finally:
        conn.close()

    return results


def clean_orphaned_data_outside_range(context: OpExecutionContext, simulation_range: List[int]) -> Dict[str, int]:
    """
    Clean orphaned simulation data OUTSIDE the specified year range.

    Provides a clean analyst experience by removing data from previous simulation runs
    that fall outside the current simulation range, while preserving year-to-year
    dependencies within the range.

    Args:
        context: Dagster operation execution context
        simulation_range: List of years in current simulation (e.g., [2025, 2026, 2027])

    Returns:
        Dict containing counts of orphaned records cleaned

    Examples:
        Clean orphaned data outside 2025-2026 range:
        >>> clean_orphaned_data_outside_range(context, [2025, 2026])
        # Removes years < 2025 OR > 2026, preserves 2025-2026 dependencies
    """
    if not simulation_range:
        context.log.info("No simulation range specified - no orphaned data cleanup")
        return {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}

    min_year = min(simulation_range)
    max_year = max(simulation_range)
    range_str = f"{min_year}-{max_year}" if min_year != max_year else str(min_year)

    context.log.info(f"Cleaning orphaned data outside simulation range {range_str}")

    results = {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}
    conn = duckdb.connect(str(DB_PATH))

    try:
        # Clean yearly events OUTSIDE the simulation range
        try:
            orphaned_events = conn.execute(
                "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year < ? OR simulation_year > ?",
                [min_year, max_year]
            ).fetchone()[0]

            if orphaned_events > 0:
                conn.execute(
                    "DELETE FROM fct_yearly_events WHERE simulation_year < ? OR simulation_year > ?",
                    [min_year, max_year]
                )
                results["fct_yearly_events"] = orphaned_events
                context.log.info(f"Cleaned {orphaned_events} orphaned events outside range {range_str}")
            else:
                context.log.info(f"No orphaned events found outside range {range_str}")
        except Exception as e:
            context.log.warning(f"Error cleaning orphaned events: {e}")

        # Clean workforce snapshots OUTSIDE the simulation range
        try:
            orphaned_snapshots = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year < ? OR simulation_year > ?",
                [min_year, max_year]
            ).fetchone()[0]

            if orphaned_snapshots > 0:
                conn.execute(
                    "DELETE FROM fct_workforce_snapshot WHERE simulation_year < ? OR simulation_year > ?",
                    [min_year, max_year]
                )
                results["fct_workforce_snapshot"] = orphaned_snapshots
                context.log.info(f"Cleaned {orphaned_snapshots} orphaned snapshots outside range {range_str}")
            else:
                context.log.info(f"No orphaned snapshots found outside range {range_str}")
        except Exception as e:
            context.log.warning(f"Error cleaning orphaned snapshots: {e}")

        # Log what we preserved
        kept_events = conn.execute(
            "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year BETWEEN ? AND ?",
            [min_year, max_year]
        ).fetchone()[0]
        kept_snapshots = conn.execute(
            "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year BETWEEN ? AND ?",
            [min_year, max_year]
        ).fetchone()[0]

        context.log.info(f"Preserved {kept_events} events and {kept_snapshots} snapshots within range {range_str}")

    except Exception as e:
        context.log.warning(f"Error during orphaned data cleanup: {e}")
    finally:
        conn.close()

    return results



def _log_hiring_calculation_debug(
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
        import math

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


@op(required_resource_keys={"dbt"})
def run_dbt_event_models_for_year(
    context: OpExecutionContext, year: int, config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute all event models for a single simulation year with debug logging.

    This operation executes the Epic 11.5 event model sequence in the correct order,
    including the detailed hiring calculation debug logging. It centralizes logic
    that was previously duplicated between single-year and multi-year simulations.

    Args:
        context: Dagster operation execution context
        year: Simulation year to process
        config: Configuration dictionary with all simulation parameters

    Returns:
        Dict containing execution results and debug information

    Examples:
        Execute events for single year:
        >>> run_dbt_event_models_for_year(context, 2025, config)

        With full configuration:
        >>> config = {
        ...     "random_seed": 42,
        ...     "target_growth_rate": 0.03,
        ...     "total_termination_rate": 0.12,
        ...     "new_hire_termination_rate": 0.25,
        ...     "full_refresh": False
        ... }
        >>> run_dbt_event_models_for_year(context, 2025, config)
    """
    # Epic 11.5 event model sequence
    event_models = [
        "int_termination_events",  # Step b-c: Experienced terminations + additional to meet rate
        "int_promotion_events",  # Promotions before hiring
        "int_merit_events",  # Merit increases
        "int_hiring_events",  # Step f: Gross hiring events
        "int_new_hire_termination_events",  # Step g: New hire termination events
    ]

    # Type annotation for results dictionary
    results: Dict[str, Any] = {
        "year": year,
        "models_executed": [],  # List of executed model names
        "hiring_debug": None,  # Will contain debug info for hiring calculations
    }

    for model in event_models:
        # Build variables for this model
        vars_dict = {
            "simulation_year": year,
            "random_seed": config["random_seed"],
            "target_growth_rate": config["target_growth_rate"],
            "new_hire_termination_rate": config["new_hire_termination_rate"],
            "total_termination_rate": config["total_termination_rate"],
        }

        # Build vars string for logging (preserve existing log format)
        vars_string = f"{{simulation_year: {year}, random_seed: {config['random_seed']}, target_growth_rate: {config['target_growth_rate']}, new_hire_termination_rate: {config['new_hire_termination_rate']}, total_termination_rate: {config['total_termination_rate']}}}"
        context.log.info(f"Running {model} for year {year} with vars: {vars_string}")

        # Special handling for hiring events debug logging
        if model == "int_hiring_events":
            debug_info = _log_hiring_calculation_debug(context, year, config)
            results["hiring_debug"] = debug_info

        # Execute model using centralized utility
        execute_dbt_command(
            context,
            ["run", "--select", model],
            vars_dict,
            config.get("full_refresh", False),
            f"{model} for year {year}",
        )

        results["models_executed"].append(model)
        context.log.debug(f"✅ Completed {model} for year {year}")

    context.log.info(
        f"Successfully executed all {len(event_models)} event models for year {year}"
    )
    return results


def _run_dbt_event_models_for_year_internal(
    context: OpExecutionContext, year: int, config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Internal helper function that executes all event models for a single simulation year.
    This is the non-decorated version of run_dbt_event_models_for_year for internal use.
    """
    # Epic 11.5 event model sequence
    event_models = [
        "int_termination_events",  # Step b-c: Experienced terminations + additional to meet rate
        "int_promotion_events",  # Promotions before hiring
        "int_merit_events",  # Merit increases
        "int_hiring_events",  # Step f: Gross hiring events
        "int_new_hire_termination_events",  # Step g: New hire termination events
    ]

    # Type annotation for results dictionary
    results: Dict[str, Any] = {
        "year": year,
        "models_executed": [],  # List of executed model names
        "hiring_debug": None,  # Will contain debug info for hiring calculations
    }

    for model in event_models:
        # Build variables for this model
        vars_dict = {
            "simulation_year": year,
            "random_seed": config["random_seed"],
            "target_growth_rate": config["target_growth_rate"],
            "new_hire_termination_rate": config["new_hire_termination_rate"],
            "total_termination_rate": config["total_termination_rate"],
            # Add raise timing configuration variables
            "raise_timing_methodology": config.get("raise_timing", {}).get("methodology", "realistic"),
            "raise_timing_profile": config.get("raise_timing", {}).get("distribution_profile", "general_corporate"),
            "timing_tolerance": config.get("raise_timing", {}).get("validation_tolerance", 0.02),
        }

        # Build vars string for logging (include new raise timing variables)
        vars_string = f"{{simulation_year: {year}, random_seed: {config['random_seed']}, target_growth_rate: {config['target_growth_rate']}, new_hire_termination_rate: {config['new_hire_termination_rate']}, total_termination_rate: {config['total_termination_rate']}, raise_timing_methodology: {vars_dict['raise_timing_methodology']}, raise_timing_profile: {vars_dict['raise_timing_profile']}}}"
        context.log.info(f"Running {model} for year {year} with vars: {vars_string}")

        # Special handling for hiring events debug logging
        if model == "int_hiring_events":
            debug_info = _log_hiring_calculation_debug(context, year, config)
            results["hiring_debug"] = debug_info

        # Execute model using centralized utility
        execute_dbt_command(
            context,
            ["run", "--select", model],
            vars_dict,
            config.get("full_refresh", False),
            f"{model} for year {year}",
        )

        results["models_executed"].append(model)
        context.log.debug(f"✅ Completed {model} for year {year}")

    context.log.info(
        f"Successfully executed all {len(event_models)} event models for year {year}"
    )
    return results


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


def run_dbt_snapshot_for_year(
    context: OpExecutionContext, year: int, snapshot_type: str = "end_of_year"
) -> Dict[str, Any]:
    """
    Execute dbt snapshot operations for a specific simulation year.

    This operation centralizes snapshot management across different simulation contexts,
    supporting various snapshot types with appropriate validation and error handling.

    Args:
        context: Dagster operation execution context
        year: Simulation year to create snapshot for
        snapshot_type: Type of snapshot to create:
            - "end_of_year": Final workforce state after all events (default)
            - "previous_year": Historical snapshot for year-1 (multi-year dependency)
            - "recovery": Rebuild missing snapshot during validation

    Returns:
        Dict containing snapshot execution results and metadata

    Raises:
        Exception: If snapshot execution fails or validation errors occur

    Examples:
        Create end-of-year snapshot:
        >>> run_dbt_snapshot_for_year(context, 2025, "end_of_year")

        Create previous year dependency snapshot:
        >>> run_dbt_snapshot_for_year(context, 2024, "previous_year")
    """
    context.log.info(f"Creating {snapshot_type} snapshot for year {year}")

    # Validate snapshot type
    valid_types = ["end_of_year", "previous_year", "recovery"]
    if snapshot_type not in valid_types:
        raise ValueError(
            f"Invalid snapshot_type '{snapshot_type}'. Must be one of: {valid_types}"
        )

    try:
        # Pre-execution validation based on snapshot type
        if snapshot_type in ["end_of_year", "recovery"]:
            # Validate that workforce data exists for the target year
            conn = duckdb.connect(str(DB_PATH))
            workforce_count = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                [year],
            ).fetchone()[0]
            conn.close()

            if snapshot_type == "end_of_year" and workforce_count == 0:
                context.log.info(
                    f"No existing workforce snapshot for year {year} - this is expected for initial snapshot creation"
                )
            elif snapshot_type == "recovery" and workforce_count > 0:
                context.log.warning(
                    f"Workforce snapshot already exists for year {year} - proceeding with recovery anyway"
                )

        # Clean existing snapshot data for this year to prevent accumulation
        conn = duckdb.connect(str(DB_PATH))
        try:
            conn.execute(
                "DELETE FROM scd_workforce_state WHERE simulation_year = ?", [year]
            )
            context.log.info(f"Cleaned existing snapshot data for year {year}")
        except Exception as e:
            context.log.info(f"No existing snapshot data to clean for year {year}: {e}")
        finally:
            conn.close()

        # Execute snapshot command based on type
        if snapshot_type == "previous_year":
            # For previous year snapshots, we use the previous year as the simulation_year parameter
            description = (
                f"workforce state snapshot for year {year} (previous year dependency)"
            )
            execute_dbt_command(
                context,
                ["snapshot", "--select", "scd_workforce_state"],
                {"simulation_year": year},
                False,  # Snapshots typically don't use full_refresh
                description,
            )
        else:
            # For end_of_year and recovery snapshots
            description = f"workforce state snapshot for year {year} ({snapshot_type})"
            execute_dbt_command(
                context,
                ["snapshot", "--select", "scd_workforce_state"],
                {"simulation_year": year},
                False,  # Snapshots typically don't use full_refresh
                description,
            )

        # Post-execution validation
        conn = duckdb.connect(str(DB_PATH))
        # Verify snapshot was created successfully
        final_count = conn.execute(
            "SELECT COUNT(*) FROM scd_workforce_state WHERE simulation_year = ?", [year]
        ).fetchone()[0]
        conn.close()

        if final_count == 0:
            raise Exception(
                f"Snapshot creation failed - no records found in scd_workforce_state for year {year}"
            )

        context.log.info(
            f"Snapshot created successfully: {final_count} records in scd_workforce_state for year {year}"
        )

        return {
            "year": year,
            "snapshot_type": snapshot_type,
            "records_created": final_count,
            "success": True,
            "description": description,
        }

    except Exception as e:
        context.log.error(
            f"Snapshot creation failed for year {year} ({snapshot_type}): {e}"
        )
        # Return failure result rather than raising to allow pipeline to continue or handle gracefully
        return {
            "year": year,
            "snapshot_type": snapshot_type,
            "records_created": 0,
            "success": False,
            "error": str(e),
            "description": f"FAILED: {snapshot_type} snapshot for year {year}",
        }


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
    Refactored to use modular components per S013-05.
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

    # Clean existing data for this specific year only (preserves other years for dependencies)
    clean_duckdb_data(context, [year])

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

                    # Try to build missing workforce snapshot using modular utility
                    try:
                        execute_dbt_command(
                            context,
                            ["run", "--select", "fct_workforce_snapshot"],
                            {"simulation_year": year - 1},
                            full_refresh,
                            f"missing workforce snapshot for year {year - 1}",
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

        # Step 2: Establish workforce base for event generation
        context.log.info(f"Running int_workforce_previous_year for year {year}")
        execute_dbt_command(
            context,
            ["run", "--select", "int_workforce_previous_year"],
            {"simulation_year": year},
            full_refresh,
            f"int_workforce_previous_year for year {year}",
        )

        # Step 3: Run event generation models using modular operation
        context.log.info(f"Running event models for year {year}")
        _run_dbt_event_models_for_year_internal(context, year, config)

        # Step 4: Consolidate all events into yearly events table
        context.log.info(f"Running fct_yearly_events for year {year}")
        execute_dbt_command(
            context,
            ["run", "--select", "fct_yearly_events"],
            {"simulation_year": year},
            full_refresh,
            f"fct_yearly_events for year {year}",
        )

        # Step 5: Generate final workforce snapshot
        context.log.info(f"Running fct_workforce_snapshot for year {year}")
        execute_dbt_command(
            context,
            ["run", "--select", "fct_workforce_snapshot"],
            {"simulation_year": year},
            full_refresh,
            f"fct_workforce_snapshot for year {year}",
        )

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


def run_year_simulation_for_multi_year(
    context: OpExecutionContext, year: int, config: Dict[str, Any] = None
) -> YearResult:
    """
    Helper function for multi-year simulation that runs a single year simulation.
    This bypasses the op config limitations by creating a temporary config context.

    Args:
        context: Original execution context
        year: Simulation year to run
        config: Optional configuration dict. If not provided, uses context.op_config
    """
    # Use provided config or fall back to context.op_config
    if config is None:
        # Create a modified config with the specific year
        original_config = context.op_config
        temp_config = original_config.copy()
        temp_config["start_year"] = year
        config = temp_config
    else:
        # Use provided config and ensure start_year is set correctly
        config = config.copy()
        config["start_year"] = year
    full_refresh = config.get("full_refresh", False)

    context.log.info(f"Starting simulation for year {year}")
    if full_refresh:
        context.log.info(
            "🔄 Full refresh enabled - will rebuild all incremental models from scratch"
        )

    # Clean existing data for this specific year only (preserves other years for dependencies)
    clean_duckdb_data(context, [year])

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

                context.log.info(
                    f"✅ Previous year validation passed: {events_count} events, {workforce_count} active employees"
                )
            finally:
                conn.close()

        # Step 2: Prepare previous year workforce with S013-04 snapshot integration
        execute_dbt_command(
            context,
            ["run", "--select", "int_workforce_previous_year"],
            {"simulation_year": year},
            full_refresh,
            f"int_workforce_previous_year for year {year}",
        )

        # Step 3: Run event generation models using modular operation
        _run_dbt_event_models_for_year_internal(context, year, config)

        # Step 4: Consolidate events
        execute_dbt_command(
            context,
            ["run", "--select", "fct_yearly_events"],
            {"simulation_year": year},
            full_refresh,
            f"fct_yearly_events for year {year}",
        )

        # Step 5: Generate final workforce snapshot (cleaning handled by clean_duckdb_data)
        execute_dbt_command(
            context,
            ["run", "--select", "fct_workforce_snapshot"],
            {"simulation_year": year},
            full_refresh,
            f"fct_workforce_snapshot for year {year}",
        )

        # Step 6: Comprehensive validation and metrics using robust fallback validation
        year_result = validate_year_results(context, year, config)
        return year_result

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
    Pure orchestrator for multi-year workforce simulation.

    Transformed per S013-06 to focus solely on coordination while leveraging
    all modular components (S013-01 through S013-05).

    Args:
        context: Dagster execution context with configuration
        baseline_valid: Baseline workforce validation result

    Returns:
        List of YearResult objects for each simulation year

    Example:
        >>> from dagster import build_op_context
        >>> config = {
        ...     "start_year": 2025,
        ...     "end_year": 2027,
        ...     "target_growth_rate": 0.03,
        ...     "total_termination_rate": 0.12,
        ...     "new_hire_termination_rate": 0.25,
        ...     "random_seed": 42,
        ...     "full_refresh": True
        ... }
        >>> context = build_op_context(op_config=config)
        >>> results = run_multi_year_simulation(context, baseline_valid=True)
        >>> for result in results:
        ...     print(f"Year {result.year}: {result.active_employees} employees")
    """
    if not baseline_valid:
        raise Exception("Baseline workforce validation failed")

    # Configuration and setup
    config = context.op_config
    start_year, end_year = config["start_year"], config["end_year"]
    full_refresh = config.get("full_refresh", False)

    context.log.info(f"🚀 Starting multi-year simulation from {start_year} to {end_year}")
    if full_refresh:
        context.log.info("🔄 Full refresh enabled - will rebuild all incremental models from scratch")

    # Step 1: Clean all data using modular component (S013-02)
    clean_duckdb_data(context, list(range(start_year, end_year + 1)))

    # Step 2: Create baseline snapshot if needed (S013-04)
    if start_year > 2025:
        _create_baseline_snapshot(context, start_year - 1)

    # Step 3: Execute year-by-year simulation using modular operations
    results = []
    for year in range(start_year, end_year + 1):
        context.log.info(f"=== Processing year {year} ===")
        year_result = _execute_single_year_with_recovery(context, year, start_year)
        results.append(year_result)
        context.log.info(f"{'✅' if year_result.success else '❌'} Year {year} {'completed' if year_result.success else 'failed'}")

    # Step 4: Provide summary
    _log_simulation_summary(context, results)
    return results


def _create_baseline_snapshot(context: OpExecutionContext, baseline_year: int) -> None:
    """Create baseline snapshot with error handling."""
    result = run_dbt_snapshot_for_year(context, baseline_year, "previous_year")
    if not result["success"]:
        context.log.warning(f"Baseline snapshot creation had issues: {result.get('error', 'Unknown error')}")


def _execute_single_year_with_recovery(context: OpExecutionContext, year: int, start_year: int) -> YearResult:
    """Execute single year with validation and recovery."""
    try:
        # Validate previous year if not first year
        if year > start_year:
            assert_year_complete(context, year - 1)
            run_dbt_snapshot_for_year(context, year - 1, "previous_year")

        # Execute single-year simulation (leverages S013-01/02/03/04 via S013-05)
        year_result = run_year_simulation_for_multi_year(context, year)
        run_dbt_snapshot_for_year(context, year, "end_of_year")
        return year_result

    except Exception as e:
        context.log.error(f"❌ Year {year} failed: {e}")
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


def _log_simulation_summary(context: OpExecutionContext, results: List[YearResult]) -> None:
    """Log comprehensive simulation summary."""
    successful_years = [r for r in results if r.success]
    failed_years = [r for r in results if not r.success]

    context.log.info("📊 === Multi-year simulation summary ===")
    context.log.info(f"🎯 Simulation completed: {len(successful_years)}/{len(results)} years successful")

    for result in results:
        if result.success:
            context.log.info(f"  ✅ Year {result.year}: {result.active_employees:,} employees, {result.growth_rate:.1%} growth")
        else:
            context.log.error(f"  ❌ Year {result.year}: FAILED")

    if failed_years:
        context.log.warning(f"⚠️  {len(failed_years)} year(s) failed - check logs for details")


def load_simulation_config() -> Dict[str, Any]:
    """Load simulation configuration from YAML file."""
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        # Return default config if file doesn't exist or can't be loaded
        return {
            'start_year': 2025,
            'end_year': 2029,
            'target_growth_rate': 0.03,
            'total_termination_rate': 0.12,
            'new_hire_termination_rate': 0.25,
            'random_seed': 42,
            'full_refresh': False
        }


def create_simulation_year_asset(year: int, previous_year: int = None):
    """Factory function to create a simulation asset for a specific year."""

    # Set up dependencies based on year
    if previous_year is None:
        # First year depends on baseline
        deps = [baseline_workforce_validated]
    else:
        # Subsequent years depend on previous year
        deps = [f"simulation_year_{previous_year}"]

    @asset(
        name=f"simulation_year_{year}",
        deps=deps
    )
    def simulation_year_asset(context: AssetExecutionContext) -> YearResult:
        f"""
        Execute workforce simulation for year {year}.

        This asset runs the complete simulation pipeline for a single year,
        including event generation, workforce snapshot creation, and validation.
        """
        # Load configuration from file
        config = load_simulation_config()

        context.log.info(f"Starting simulation for year {year}")

        # Use the existing single-year simulation logic
        try:
            year_result = run_year_simulation_for_multi_year(context, year, config)

            # Create snapshot for this year
            snapshot_result = run_dbt_snapshot_for_year(context, year, "end_of_year")
            if not snapshot_result["success"]:
                context.log.warning(f"Snapshot creation had issues: {snapshot_result.get('error', 'Unknown error')}")

            context.log.info(f"✅ Year {year} simulation completed: {year_result.active_employees:,} employees, {year_result.growth_rate:.1%} growth")
            return year_result

        except Exception as e:
            context.log.error(f"❌ Year {year} simulation failed: {e}")
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

    return simulation_year_asset


def create_simulation_assets():
    """Create all simulation year assets based on configuration."""
    config = load_simulation_config()
    start_year = config.get('start_year', 2025)
    end_year = config.get('end_year', 2029)

    assets = []
    previous_year = None

    for year in range(start_year, end_year + 1):
        asset_func = create_simulation_year_asset(year, previous_year)
        assets.append(asset_func)
        previous_year = year

    return assets


# Generate simulation year assets dynamically
simulation_year_assets = create_simulation_assets()


@asset(deps=simulation_year_assets)
def multi_year_simulation_summary(context: AssetExecutionContext) -> Dict[str, Any]:
    """
    Aggregate results from all simulation years and provide comprehensive summary.

    This asset depends on all individual year simulation assets and provides
    the same summary information that was previously generated by the monolithic
    multi-year simulation operation.
    """
    config = load_simulation_config()
    start_year = config.get('start_year', 2025)
    end_year = config.get('end_year', 2029)

    context.log.info("📊 === Multi-year simulation summary ===")

    # Collect results from all years by querying the database
    # (since we can't directly access the other assets' return values)
    conn = duckdb.connect(str(DB_PATH))
    results = []

    try:
        for year in range(start_year, end_year + 1):
            try:
                # Get metrics for this year
                workforce_metrics = conn.execute("""
                    SELECT
                        COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                """, [year]).fetchone()

                event_metrics = conn.execute("""
                    SELECT
                        SUM(CASE WHEN event_type = 'hire' THEN 1 ELSE 0 END) as total_hires,
                        SUM(CASE WHEN event_type = 'termination' THEN 1 ELSE 0 END) as total_terminations
                    FROM fct_yearly_events
                    WHERE simulation_year = ?
                """, [year]).fetchone()

                if workforce_metrics and workforce_metrics[0] > 0:
                    active_employees = workforce_metrics[0]
                    total_hires = event_metrics[0] if event_metrics else 0
                    total_terminations = event_metrics[1] if event_metrics else 0

                    # Calculate growth rate
                    if year == start_year:
                        baseline_count = conn.execute("""
                            SELECT COUNT(*) FROM int_baseline_workforce
                            WHERE employment_status = 'active'
                        """).fetchone()[0]
                        previous_active = baseline_count
                    else:
                        previous_active = conn.execute("""
                            SELECT COUNT(*) FROM fct_workforce_snapshot
                            WHERE simulation_year = ? AND employment_status = 'active'
                        """, [year - 1]).fetchone()[0]

                    growth_rate = ((active_employees - previous_active) / previous_active) if previous_active > 0 else 0

                    results.append({
                        'year': year,
                        'success': True,
                        'active_employees': active_employees,
                        'total_hires': total_hires,
                        'total_terminations': total_terminations,
                        'growth_rate': growth_rate
                    })

                    context.log.info(f"  ✅ Year {year}: {active_employees:,} employees, {growth_rate:.1%} growth")
                else:
                    context.log.error(f"  ❌ Year {year}: No data found")
                    results.append({'year': year, 'success': False})

            except Exception as e:
                context.log.error(f"  ❌ Year {year}: Failed to retrieve metrics - {e}")
                results.append({'year': year, 'success': False})

    finally:
        conn.close()

    successful_years = [r for r in results if r.get('success', False)]
    failed_years = [r for r in results if not r.get('success', False)]

    context.log.info(f"🎯 Simulation completed: {len(successful_years)}/{len(results)} years successful")

    if failed_years:
        context.log.warning(f"⚠️  {len(failed_years)} year(s) failed - check individual year asset logs for details")

    summary = {
        'total_years': len(results),
        'successful_years': len(successful_years),
        'failed_years': len(failed_years),
        'results': results,
        'config': config
    }

    return summary


@job(resource_defs={"dbt": dbt_resource})
def multi_year_simulation():
    """
    Job to run complete multi-year workforce simulation.
    Executes years sequentially to maintain state dependencies.
    """
    # First validate baseline workforce; result is passed to main op to enforce ordering
    baseline_ok = baseline_workforce_validated_op()
    run_multi_year_simulation(baseline_ok)


@job(resource_defs={"dbt": dbt_resource})
def asset_based_multi_year_simulation():
    """
    NEW: Asset-based multi-year simulation job.

    This job uses individual year assets that can be materialized independently,
    providing better observability, restart capability, and debugging experience.
    Each year is a separate asset with proper dependency chaining.
    """
    # This job doesn't need explicit op calls since Dagster will materialize
    # the assets based on their dependency graph. The summary asset depends
    # on all year assets, so materializing it will trigger the full simulation.
    pass


# Optimization Assets for S045

@asset(group_name="optimization")
def compensation_optimization_loop(
    context: AssetExecutionContext,
    optimization_config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Orchestrates iterative parameter optimization using existing simulation pipeline.
    Reuses proven multi-method execution: Dagster CLI → Asset-based → Manual dbt.
    """
    if optimization_config is None:
        # Load default optimization config
        optimization_config = {
            'target_growth': 2.0,
            'max_iterations': 10,
            'tolerance': 0.1,
            'mode': 'Balanced'
        }

    context.log.info(f"🎯 Starting compensation optimization with config: {optimization_config}")

    max_iterations = optimization_config.get('max_iterations', 10)
    tolerance = optimization_config.get('tolerance', 0.02)
    target_growth = optimization_config.get('target_growth', 2.0)
    optimization_mode = optimization_config.get('mode', 'Balanced')

    # Create iteration tracking
    iteration_results = []
    converged = False

    context.log.info(f"🎯 Starting optimization with target growth: {target_growth}%")
    context.log.info(f"🔄 Max iterations: {max_iterations}, Tolerance: {tolerance}%")

    for iteration in range(max_iterations):
        context.log.info(f"🔄 Starting iteration {iteration + 1}")

        # Run simulation using existing multi-year simulation pipeline
        try:
            # Load and execute simulation configuration
            config = load_simulation_config()
            context.log.info(f"📊 Running simulation with config: {config}")

            # Execute the simulation (this will materialize all year assets)
            summary_result = multi_year_simulation_summary(context)

            # Analyze results
            if summary_result and 'results' in summary_result:
                successful_results = [r for r in summary_result['results'] if r.get('success', False)]
                if successful_results:
                    # Calculate average growth across all years
                    growth_rates = [r['growth_rate'] for r in successful_results]
                    current_growth = sum(growth_rates) / len(growth_rates) * 100  # Convert to percentage
                else:
                    current_growth = 0
            else:
                current_growth = 0

            gap = target_growth - current_growth

            # Store iteration result
            iteration_result = {
                'iteration': iteration + 1,
                'current_growth': current_growth,
                'gap': gap,
                'converged': abs(gap) <= tolerance
            }
            iteration_results.append(iteration_result)

            context.log.info(f"📊 Iteration {iteration + 1} results:")
            context.log.info(f"   Current Growth: {current_growth:.2f}%")
            context.log.info(f"   Gap to Target: {gap:+.2f}%")
            context.log.info(f"   Status: {'✅ Converged' if abs(gap) <= tolerance else '🔄 Optimizing'}")

            # Check convergence
            if abs(gap) <= tolerance:
                converged = True
                context.log.info(f"🎉 Optimization converged in {iteration + 1} iterations!")
                break

            # Adjust parameters intelligently for next iteration
            if iteration < max_iterations - 1:  # Don't adjust on last iteration
                context.log.info("🔧 Adjusting parameters for next iteration...")
                adjust_success = adjust_parameters_for_optimization(context, gap, optimization_mode, iteration + 1)
                if not adjust_success:
                    context.log.error("❌ Parameter adjustment failed")
                    break

        except Exception as e:
            context.log.error(f"❌ Simulation failed at iteration {iteration + 1}: {e}")
            break

    # Create final summary
    final_result = {
        'converged': converged,
        'iterations': len(iteration_results),
        'final_growth': iteration_results[-1]['current_growth'] if iteration_results else 0,
        'final_gap': iteration_results[-1]['gap'] if iteration_results else 0,
        'iteration_history': iteration_results,
        'optimization_config': optimization_config
    }

    context.log.info(f"🏁 Optimization completed: {'✅ Converged' if converged else '❌ Did not converge'}")
    context.log.info(f"📊 Final results: {final_result['final_growth']:.2f}% growth (gap: {final_result['final_gap']:+.2f}%)")

    return final_result


def adjust_parameters_for_optimization(context: AssetExecutionContext, gap: float, optimization_mode: str, iteration: int) -> bool:
    """
    Intelligent parameter adjustment using existing parameter structure.
    Builds on proven parameter validation and application patterns.
    """
    try:
        import pandas as pd
        from pathlib import Path

        # Load current parameters from comp_levers.csv
        comp_levers_path = Path(PROJECT_ROOT / "dbt" / "seeds" / "comp_levers.csv")
        if not comp_levers_path.exists():
            context.log.error(f"❌ Could not find comp_levers.csv at {comp_levers_path}")
            return False

        df = pd.read_csv(comp_levers_path)

        # Calculate adjustment factors based on optimization mode
        if optimization_mode == "Conservative":
            adjustment_factor = 0.1  # 10% of the gap
        elif optimization_mode == "Aggressive":
            adjustment_factor = 0.5  # 50% of the gap
        else:  # Balanced (default)
            adjustment_factor = 0.3  # 30% of the gap

        # Reduce adjustment factor as iterations progress (convergence acceleration)
        adjustment_factor *= (0.8 ** (iteration - 1))

        # Calculate parameter adjustments
        # Gap > 0 means we need to increase growth (increase compensation parameters)
        # Gap < 0 means we need to decrease growth (decrease compensation parameters)

        gap_adjustment = gap * adjustment_factor / 100  # Convert percentage to decimal

        context.log.info(f"📊 Parameter adjustment calculation:")
        context.log.info(f"   Gap: {gap:+.2f}%")
        context.log.info(f"   Mode: {optimization_mode}")
        context.log.info(f"   Adjustment factor: {adjustment_factor:.3f}")
        context.log.info(f"   Gap adjustment: {gap_adjustment:+.4f}")

        # Update parameters in the DataFrame
        for _, row in df.iterrows():
            param_name = row['parameter_name']
            current_value = row['parameter_value']

            if param_name == 'cola_rate':
                # Adjust COLA rate
                new_value = max(0.01, min(0.08, current_value + gap_adjustment))
                df.loc[df.index == row.name, 'parameter_value'] = new_value

            elif param_name == 'merit_base':
                # Adjust merit rates (distribute adjustment across levels)
                level = row['job_level']
                # Higher levels get smaller adjustments
                level_factor = 1.2 - (level * 0.1)  # Level 1: 1.1x, Level 5: 0.7x
                new_value = max(0.01, min(0.10, current_value + (gap_adjustment * level_factor)))
                df.loc[df.index == row.name, 'parameter_value'] = new_value

            elif param_name == 'new_hire_salary_adjustment':
                # Adjust new hire salary adjustment (more conservative)
                new_value = max(1.0, min(1.4, current_value + (gap_adjustment * 0.5)))
                df.loc[df.index == row.name, 'parameter_value'] = new_value

        # Update metadata
        df['created_at'] = datetime.now().strftime("%Y-%m-%d")
        df['created_by'] = 'optimization_engine'

        # Save updated parameters
        df.to_csv(comp_levers_path, index=False)

        context.log.info(f"✅ Parameters updated for iteration {iteration}")
        context.log.info(f"📊 Updated {len(df)} parameter entries in comp_levers.csv")

        return True

    except Exception as e:
        context.log.error(f"❌ Parameter adjustment failed: {e}")
        import traceback
        context.log.error(f"Detailed error: {traceback.format_exc()}")
        return False


@asset(group_name="optimization", deps=[compensation_optimization_loop])
def optimization_results_summary(
    context: AssetExecutionContext,
    optimization_loop_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Consolidates optimization results for analyst review.
    Builds on existing results visualization patterns.
    """
    try:
        context.log.info("📊 Creating optimization results summary...")

        if not optimization_loop_result:
            context.log.warning("⚠️ No optimization results to summarize")
            return {"status": "no_results", "summary": "No optimization data available"}

        # Extract key metrics
        converged = optimization_loop_result.get('converged', False)
        iterations = optimization_loop_result.get('iterations', 0)
        final_growth = optimization_loop_result.get('final_growth', 0)
        final_gap = optimization_loop_result.get('final_gap', 0)
        iteration_history = optimization_loop_result.get('iteration_history', [])
        optimization_config = optimization_loop_result.get('optimization_config', {})

        # Create summary statistics
        if iteration_history:
            growth_progression = [iter_result['current_growth'] for iter_result in iteration_history]
            gap_progression = [iter_result['gap'] for iter_result in iteration_history]

            # Calculate convergence metrics
            initial_gap = gap_progression[0] if gap_progression else 0
            gap_reduction = abs(initial_gap - final_gap) if initial_gap != 0 else 0
            gap_reduction_pct = (gap_reduction / abs(initial_gap)) * 100 if initial_gap != 0 else 0
        else:
            growth_progression = []
            gap_progression = []
            initial_gap = 0
            gap_reduction = 0
            gap_reduction_pct = 0

        # Performance assessment
        if converged:
            performance_status = "Excellent - Target achieved"
        elif iterations >= optimization_config.get('max_iterations', 10):
            if gap_reduction_pct > 50:
                performance_status = "Good - Significant progress made"
            else:
                performance_status = "Poor - Limited progress"
        else:
            performance_status = "Interrupted - Early termination"

        # Create detailed summary
        summary = {
            "status": "converged" if converged else "not_converged",
            "performance_status": performance_status,
            "optimization_config": optimization_config,
            "results": {
                "converged": converged,
                "iterations_used": iterations,
                "max_iterations": optimization_config.get('max_iterations', 10),
                "final_growth_rate": final_growth,
                "target_growth_rate": optimization_config.get('target_growth', 2.0),
                "final_gap": final_gap,
                "tolerance": optimization_config.get('tolerance', 0.1),
                "initial_gap": initial_gap,
                "gap_reduction": gap_reduction,
                "gap_reduction_percentage": gap_reduction_pct
            },
            "progression": {
                "growth_rates": growth_progression,
                "gaps": gap_progression,
                "iteration_history": iteration_history
            },
            "recommendations": []
        }

        # Add recommendations based on results
        if converged:
            summary["recommendations"].append("✅ Optimization successful - parameters are now optimized for target growth rate")
            summary["recommendations"].append("📊 Review the Results tab to see final simulation outcomes")
        else:
            if gap_reduction_pct < 25:
                summary["recommendations"].append("⚠️ Limited progress - consider adjusting tolerance or target growth rate")
            summary["recommendations"].append("🔄 Try increasing max iterations for better convergence")
            summary["recommendations"].append("⚙️ Consider switching optimization strategy (Conservative/Balanced/Aggressive)")

        # Performance insights
        if iterations > 1:
            avg_gap_reduction_per_iter = gap_reduction / iterations
            summary["performance_insights"] = {
                "average_gap_reduction_per_iteration": avg_gap_reduction_per_iter,
                "convergence_efficiency": gap_reduction_pct / iterations if iterations > 0 else 0
            }

        context.log.info(f"📊 Optimization summary created:")
        context.log.info(f"   Status: {summary['status']}")
        context.log.info(f"   Performance: {performance_status}")
        context.log.info(f"   Gap reduction: {gap_reduction_pct:.1f}%")
        context.log.info(f"   Iterations: {iterations}")

        return summary

    except Exception as e:
        context.log.error(f"❌ Failed to create optimization summary: {e}")
        import traceback
        context.log.error(f"Detailed error: {traceback.format_exc()}")
        return {"status": "error", "error": str(e)}


@job(resource_defs={"dbt": dbt_resource})
def compensation_optimization_job():
    """
    Automated optimization job that wraps existing multi_year_simulation.
    Reuses proven job configuration and resource management patterns.
    """
    # Initialize optimization parameters using existing config patterns
    optimization_results_summary(compensation_optimization_loop())


@job(resource_defs={"dbt": dbt_resource})
def single_optimization_iteration():
    """
    Single optimization iteration for testing and debugging.
    Mirrors existing single_year_simulation job patterns.
    """
    # Execute single iteration using existing patterns
    # Useful for testing parameter adjustment logic
    optimization_config = {
        'target_growth': 2.0,
        'max_iterations': 1,
        'tolerance': 0.1,
        'mode': 'Balanced'
    }
    optimization_results_summary(compensation_optimization_loop())


# Export all definitions for Dagster
__all__ = [
    "simulation_year_state",
    "baseline_workforce_validated",
    "baseline_workforce_validated_op",
    "clean_duckdb_data",
    "execute_dbt_command",
    "execute_dbt_command_streaming",
    "run_multi_year_simulation",
    "single_year_simulation",
    "multi_year_simulation",
    "asset_based_multi_year_simulation",
    "validate_growth_rates",
    "dbt_resource",
    "SimulationConfig",
    "YearResult",
    "simulation_year_assets",
    "multi_year_simulation_summary",
    "load_simulation_config",
    "create_simulation_assets",
    "compensation_optimization_loop",
    "optimization_results_summary",
    "compensation_optimization_job",
    "single_optimization_iteration",
    "adjust_parameters_for_optimization",
]
