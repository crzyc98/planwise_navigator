#!/usr/bin/env python3
"""
Enhanced Multi-Year Simulation Runner with Production Observability

Enterprise-grade multi-year simulation runner with structured logging,
performance monitoring, and comprehensive run tracking.

Features:
- Structured JSON logging with run correlation
- Performance monitoring and resource tracking
- Comprehensive error handling and reporting
- Audit trail generation
- Integration with backup systems
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import duckdb
import yaml

from navigator_orchestrator import ObservabilityManager, observability_session
from shared_utils import ExecutionMutex, print_execution_warning


def load_config() -> Dict[str, Any]:
    """Load simulation configuration from YAML file."""
    config_path = Path("config/simulation_config.yaml")

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Extract simulation parameters
    simulation = config.get("simulation", {})
    start_year = simulation.get("start_year", 2025)
    end_year = simulation.get("end_year", 2029)
    random_seed = simulation.get("random_seed", 42)

    # Extract compensation parameters
    compensation = config.get("compensation", {})
    cola_rate = compensation.get("cola_rate", 0.005)
    merit_budget = compensation.get("merit_budget", 0.025)

    return {
        "start_year": start_year,
        "end_year": end_year,
        "random_seed": random_seed,
        "cola_rate": cola_rate,
        "merit_budget": merit_budget,
        "full_config": config,
    }


def run_dbt_command(
    command: List[str], obs: ObservabilityManager, operation_name: str, **context
) -> bool:
    """
    Run dbt command with observability tracking

    Args:
        command: dbt command as list of strings
        obs: ObservabilityManager instance
        operation_name: Name for tracking this operation
        **context: Additional context for logging

    Returns:
        True if command succeeded, False otherwise
    """
    with obs.track_operation(
        operation_name, command=" ".join(command), **context
    ) as metrics:
        try:
            obs.log_info(f"Running dbt command: {' '.join(command)}", **context)

            result = subprocess.run(
                command, cwd="dbt", capture_output=True, text=True, check=True
            )

            # Log successful completion
            obs.log_info(
                f"dbt command completed successfully",
                stdout_lines=len(result.stdout.splitlines()),
                stderr_lines=len(result.stderr.splitlines()),
                **context,
            )

            return True

        except subprocess.CalledProcessError as e:
            obs.log_error(
                f"dbt command failed: {e}",
                returncode=e.returncode,
                stdout=e.stdout,
                stderr=e.stderr,
                **context,
            )
            return False
        except Exception as e:
            obs.log_exception(f"Unexpected error running dbt command: {e}", **context)
            return False


def validate_database_state(obs: ObservabilityManager, year: int) -> bool:
    """
    Validate database state after year processing

    Args:
        obs: ObservabilityManager instance
        year: Year that was just processed

    Returns:
        True if validation passed, False otherwise
    """
    with obs.track_operation("database_validation", year=year) as metrics:
        try:
            conn = duckdb.connect("simulation.duckdb")

            # Check workforce snapshot
            workforce_result = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                [year],
            ).fetchone()
            workforce_count = workforce_result[0] if workforce_result else 0

            # Check yearly events
            events_result = conn.execute(
                "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ?",
                [year],
            ).fetchone()
            events_count = events_result[0] if events_result else 0

            # Log data quality checks
            obs.log_data_quality_check(
                year, "workforce_snapshot_count", workforce_count, 50000
            )
            obs.log_data_quality_check(
                year, "yearly_events_count", events_count, 100000
            )

            # Add metrics
            obs.add_metric(f"workforce_count_year_{year}", workforce_count)
            obs.add_metric(f"events_count_year_{year}", events_count)

            # Basic validation
            if workforce_count == 0:
                obs.log_error(
                    f"No workforce snapshot records found for year {year}", year=year
                )
                return False

            if events_count == 0:
                obs.log_warning(f"No yearly events found for year {year}", year=year)

            obs.log_info(
                f"Database validation passed for year {year}",
                workforce_count=workforce_count,
                events_count=events_count,
                year=year,
            )

            return True

        except Exception as e:
            obs.log_exception(
                f"Database validation failed for year {year}: {e}", year=year
            )
            return False
        finally:
            conn.close()


def create_backup(obs: ObservabilityManager) -> str:
    """
    Create database backup with observability tracking

    Args:
        obs: ObservabilityManager instance

    Returns:
        Path to backup file
    """
    with obs.track_operation("database_backup") as metrics:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"backups/simulation_backup_{timestamp}.sql"

            # Ensure backup directory exists
            Path("backups").mkdir(exist_ok=True)

            # Create backup using DuckDB export
            conn = duckdb.connect("simulation.duckdb")
            conn.execute(f"EXPORT DATABASE '{backup_path}' (FORMAT PARQUET)")
            conn.close()

            # Verify backup was created
            backup_file = Path(backup_path)
            if backup_file.exists():
                backup_size_mb = backup_file.stat().st_size / (1024 * 1024)
                obs.log_info(
                    "Database backup created successfully",
                    backup_path=backup_path,
                    backup_size_mb=round(backup_size_mb, 2),
                )
                obs.add_metric("backup_size_mb", backup_size_mb)
                return backup_path
            else:
                obs.log_error("Backup file was not created", backup_path=backup_path)
                return None

        except Exception as e:
            obs.log_exception(f"Failed to create database backup: {e}")
            return None


def run_simulation_year(
    year: int, config: Dict[str, Any], obs: ObservabilityManager
) -> bool:
    """
    Run simulation for a single year with comprehensive observability

    Args:
        year: Year to simulate
        config: Configuration dictionary
        obs: ObservabilityManager instance

    Returns:
        True if year completed successfully, False otherwise
    """
    with obs.track_operation(f"simulate_year_{year}", year=year) as year_metrics:
        obs.log_info(f"Starting simulation for year {year}", year=year)

        # Build dbt variables
        dbt_vars = {
            "simulation_year": year,
            "cola_rate": config["cola_rate"],
            "merit_budget": config["merit_budget"],
        }

        vars_json = json.dumps(dbt_vars)

        # Define the sequence of models to run for this year
        model_sequence = [
            ("staging_and_baseline", ["stg_census_data", "int_baseline_workforce"]),
            ("compensation_calculation", ["int_employee_compensation_by_year"]),
            (
                "workforce_needs",
                ["int_workforce_needs", "int_workforce_needs_by_level"],
            ),
            (
                "event_generation",
                [
                    "int_hiring_events",
                    "int_termination_events",
                    "int_new_hire_termination_events",
                    "int_promotion_events",
                    "int_merit_events",
                    "int_enrollment_events",
                ],
            ),
            ("event_consolidation", ["fct_yearly_events"]),
            ("workforce_snapshot", ["fct_workforce_snapshot"]),
        ]

        # Run each model group
        for group_name, models in model_sequence:
            model_list = " ".join(models)
            command = ["dbt", "run", "--select", model_list, "--vars", vars_json]

            success = run_dbt_command(
                command,
                obs,
                f"run_{group_name}",
                year=year,
                group=group_name,
                models=models,
            )

            if not success:
                obs.log_error(
                    f"Failed to run {group_name} for year {year}",
                    year=year,
                    group=group_name,
                    models=models,
                )
                return False

        # Validate results
        if not validate_database_state(obs, year):
            obs.log_error(f"Database validation failed for year {year}", year=year)
            return False

        obs.log_info(f"Year {year} simulation completed successfully", year=year)
        return True


def main():
    """Main execution function with comprehensive observability"""
    parser = argparse.ArgumentParser(
        description="Enhanced Multi-Year Simulation Runner"
    )
    parser.add_argument("--run-id", help="Custom run ID for tracking")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    parser.add_argument(
        "--create-backup",
        action="store_true",
        help="Create database backup before simulation",
    )
    parser.add_argument("--years", help="Specific years to run (e.g., '2025,2026')")
    args = parser.parse_args()

    # Start observability session
    with observability_session(run_id=args.run_id, log_level=args.log_level) as obs:
        try:
            obs.log_info("Starting enhanced multi-year simulation")

            # Load configuration
            with obs.track_operation("load_configuration") as config_metrics:
                config = load_config()
                obs.set_configuration(config["full_config"])
                obs.log_info("Configuration loaded successfully", **config)

            # Determine years to process
            if args.years:
                years = [int(y.strip()) for y in args.years.split(",")]
                obs.log_info(f"Running specific years: {years}", years=years)
            else:
                years = list(range(config["start_year"], config["end_year"] + 1))
                obs.log_info(f"Running full range: {years}", years=years)

            # Create backup if requested
            backup_path = None
            if args.create_backup:
                backup_path = create_backup(obs)
                if backup_path:
                    obs.set_backup_path(backup_path)
                else:
                    obs.log_warning("Backup creation failed, continuing without backup")

            # Use execution mutex to prevent concurrent runs
            with ExecutionMutex():
                # Run simulation for each year
                successful_years = []
                failed_years = []

                for year in years:
                    obs.log_info(
                        f"Processing year {year} ({years.index(year) + 1}/{len(years)})",
                        year=year,
                        progress=f"{years.index(year) + 1}/{len(years)}",
                    )

                    if run_simulation_year(year, config, obs):
                        successful_years.append(year)
                        obs.add_metric(f"year_{year}_status", "success")
                    else:
                        failed_years.append(year)
                        obs.add_metric(f"year_{year}_status", "failed")
                        obs.log_error(f"Year {year} simulation failed", year=year)

                # Final summary
                obs.add_metric("total_years_attempted", len(years))
                obs.add_metric("successful_years", len(successful_years))
                obs.add_metric("failed_years", len(failed_years))

                if failed_years:
                    final_status = "partial" if successful_years else "failed"
                    obs.log_error(
                        f"Simulation completed with failures",
                        successful_years=successful_years,
                        failed_years=failed_years,
                    )
                else:
                    final_status = "success"
                    obs.log_info(
                        "All years completed successfully",
                        successful_years=successful_years,
                    )

                # Generate final summary
                summary = obs.finalize_run(final_status)

                # Return appropriate exit code
                return 0 if final_status == "success" else 1

        except Exception as e:
            obs.log_exception(f"Simulation failed with unhandled exception: {e}")
            obs.finalize_run("failed")
            return 1


if __name__ == "__main__":
    sys.exit(main())
