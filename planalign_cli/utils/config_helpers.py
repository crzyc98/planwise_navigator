"""
Configuration helper utilities for Fidelity PlanAlign Engine CLI

Functions to find, validate, and work with configuration files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple


def find_default_config() -> Path:
    """Find the default simulation configuration file."""
    default_paths = [
        Path("config/simulation_config.yaml"),
        Path("simulation_config.yaml"),
        Path("config.yaml"),
    ]

    for config_path in default_paths:
        if config_path.exists():
            return config_path

    # Return the most likely path even if it doesn't exist
    return Path("config/simulation_config.yaml")


def find_default_database() -> Path:
    """Find the default database file."""
    default_paths = [
        Path("dbt/simulation.duckdb"),
        Path("simulation.duckdb"),
        Path("database.duckdb"),
    ]

    for db_path in default_paths:
        if db_path.exists():
            return db_path

    # Return the standard location even if it doesn't exist
    return Path("dbt/simulation.duckdb")


def parse_years(years_str: str) -> Tuple[int, int]:
    """
    Parse year range string into start and end years.

    Args:
        years_str: Year string in format "2025-2027" or "2025"

    Returns:
        Tuple of (start_year, end_year)

    Raises:
        ValueError: If the format is invalid
    """
    try:
        if "-" in years_str:
            start_str, end_str = years_str.split("-", 1)
            return int(start_str), int(end_str)
        else:
            # Single year - assume one year simulation
            year = int(years_str)
            return year, year
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid year format: {years_str}. Expected 'YYYY' or 'YYYY-YYYY'") from e


def validate_year_range(start_year: int, end_year: int) -> None:
    """
    Validate that the year range makes sense.

    Args:
        start_year: Starting year
        end_year: Ending year

    Raises:
        ValueError: If the year range is invalid
    """
    current_year = 2024  # Base year for validation

    if start_year > end_year:
        raise ValueError(f"Start year {start_year} cannot be after end year {end_year}")

    if start_year < current_year:
        raise ValueError(f"Start year {start_year} cannot be before {current_year}")

    if end_year > current_year + 50:
        raise ValueError(f"End year {end_year} is too far in the future (max: {current_year + 50})")

    if (end_year - start_year) > 20:
        raise ValueError(f"Year range too large: {end_year - start_year + 1} years (max: 20)")


def find_scenarios_directory() -> Path:
    """Find the scenarios directory."""
    default_paths = [
        Path("scenarios"),
        Path("scenario_configs"),
        Path("configs/scenarios"),
    ]

    for scenarios_path in default_paths:
        if scenarios_path.exists() and scenarios_path.is_dir():
            return scenarios_path

    # Return the standard location
    return Path("scenarios")


def find_comp_levers_file() -> Path:
    """Find the compensation levers CSV file."""
    default_paths = [
        Path("comp_levers.csv"),
        Path("config/comp_levers.csv"),
        Path("data/comp_levers.csv"),
    ]

    for comp_levers_path in default_paths:
        if comp_levers_path.exists():
            return comp_levers_path

    # Return the standard location
    return Path("comp_levers.csv")


def get_default_paths() -> dict:
    """Get all default paths for the application."""
    return {
        "config": find_default_config(),
        "database": find_default_database(),
        "scenarios": find_scenarios_directory(),
        "comp_levers": find_comp_levers_file(),
    }


def ensure_directory_exists(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path = path.resolve()
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    elif not path.is_dir():
        raise ValueError(f"Path exists but is not a directory: {path}")
    return path


def get_output_directory(base_name: str = "outputs") -> Path:
    """Get a timestamped output directory."""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(base_name) / f"batch_{timestamp}"
    return ensure_directory_exists(output_dir)


def check_required_files() -> dict:
    """Check for existence of required files and directories."""
    checks = {}

    # Configuration file
    config_path = find_default_config()
    checks["config_exists"] = config_path.exists()
    checks["config_path"] = str(config_path)

    # Database file (optional - created on first run)
    db_path = find_default_database()
    checks["database_exists"] = db_path.exists()
    checks["database_path"] = str(db_path)

    # dbt directory
    dbt_dir = Path("dbt")
    checks["dbt_exists"] = dbt_dir.exists() and dbt_dir.is_dir()
    checks["dbt_path"] = str(dbt_dir)

    # dbt_project.yml
    dbt_project = Path("dbt/dbt_project.yml")
    checks["dbt_project_exists"] = dbt_project.exists()
    checks["dbt_project_path"] = str(dbt_project)

    # Scenarios directory (optional)
    scenarios_dir = find_scenarios_directory()
    checks["scenarios_exists"] = scenarios_dir.exists() and scenarios_dir.is_dir()
    checks["scenarios_path"] = str(scenarios_dir)

    # Overall readiness
    checks["ready_for_simulation"] = (
        checks["config_exists"] and
        checks["dbt_exists"] and
        checks["dbt_project_exists"]
    )

    checks["ready_for_batch"] = checks["ready_for_simulation"] and checks["scenarios_exists"]

    return checks
