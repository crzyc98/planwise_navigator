"""Fixtures and helpers for employer contribution service-credit regressions."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb
import pandas as pd

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import SimulationConfig, load_simulation_config

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests/fixtures/employer_eligibility_tenure"
CENSUS_CSV = ROOT / "tests/fixtures/invariant_census.csv"
BASELINE_CHARACTERIZATION = FIXTURE_ROOT / "baseline_characterization.json"
WAIT_CONFIGS = {wait: FIXTURE_ROOT / f"wait_{wait}.yaml" for wait in range(4)}
DATE_COLUMNS = (
    "employee_birth_date",
    "employee_hire_date",
    "employee_termination_date",
    "eligibility_entry_date",
)
BOOLEAN_COLUMNS = ("active", "auto_escalation_opt_out", "eligibility_override")


def prepare_census_parquet(path: Path) -> Path:
    """Build a non-PII test parquet with populated 1- and 2-year boundaries."""
    frame = pd.read_csv(CENSUS_CSV)
    for column in DATE_COLUMNS:
        frame[column] = pd.to_datetime(frame[column], errors="coerce")

    one_year = frame.index[frame["employee_hire_date"].dt.year == 2024]
    two_year = one_year[:12]
    frame.loc[two_year, "employee_hire_date"] = pd.Timestamp("2023-06-30")
    frame.loc[two_year, "eligibility_entry_date"] = pd.Timestamp("2023-06-30")
    assert_boundary_coverage(frame)

    for column in DATE_COLUMNS:
        frame[column] = frame[column].dt.date
    for column in BOOLEAN_COLUMNS:
        frame[column] = pd.array(frame[column], dtype="boolean")

    path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = path.with_suffix(".csv")
    frame.to_csv(csv_path, index=False)
    try:
        with duckdb.connect() as connection:
            connection.read_csv(str(csv_path)).write_parquet(str(path))
    finally:
        csv_path.unlink(missing_ok=True)
    return path


def assert_boundary_coverage(frame: pd.DataFrame) -> None:
    """Keep the wait comparisons non-vacuous at the opening-year boundary."""
    service = (
        (pd.Timestamp("2025-12-31") - frame["employee_hire_date"]).dt.days / 365.25
    ).floordiv(1)
    counts = service.value_counts()
    assert counts.get(1, 0) >= 10
    assert counts.get(2, 0) >= 10
    assert (service >= 3).sum() >= 10
    assert (frame["employee_deferral_rate"] > 0).sum() >= 30


def load_wait_config(
    wait_years: int, census_parquet: Path, *, end_year: int = 2029
) -> SimulationConfig:
    """Load one wait case and point it at the caller's disposable census."""
    try:
        config_path = WAIT_CONFIGS[wait_years]
    except KeyError as error:
        raise ValueError(f"unsupported service wait: {wait_years}") from error
    config = load_simulation_config(config_path, env_overrides=False)
    config.simulation.end_year = end_year
    config.setup["census_parquet_path"] = str(census_parquet)
    return config


def load_termination_rate_config(
    census_parquet: Path, *, end_year: int = 2026
) -> SimulationConfig:
    """Build the allowed-termination case with a shared five-year tier boundary."""
    payload = load_wait_config(0, census_parquet, end_year=end_year).model_dump()
    payload["scenario_id"] = "service_termination_tiers"
    payload["workforce"]["total_termination_rate"] = 0.30
    payload["employer_core_contribution"] = {
        "enabled": True,
        "status": "graded_by_service",
        "contribution_rate": 0.01,
        "graded_schedule": [
            {
                "service_years_min": 0,
                "service_years_max": 5,
                "contribution_rate": 0.03,
            },
            {
                "service_years_min": 5,
                "service_years_max": None,
                "contribution_rate": 0.06,
            },
        ],
        "eligibility": {
            "minimum_tenure_years": 0,
            "require_active_at_year_end": False,
            "minimum_hours_annual": 0,
            "allow_new_hires": True,
            "allow_terminated_new_hires": True,
            "allow_experienced_terminations": True,
        },
    }
    payload["employer_match"].update(
        {
            "apply_eligibility": True,
            "employer_match_status": "tenure_graded",
            "eligibility": {
                "minimum_tenure_years": 0,
                "require_active_at_year_end": False,
                "minimum_hours_annual": 0,
                "allow_new_hires": True,
                "allow_terminated_new_hires": True,
                "allow_experienced_terminations": True,
            },
            "tenure_graded_bands": [
                {
                    "min_years": 0,
                    "max_years": 5,
                    "tiers": [
                        {
                            "employee_min": 0.0,
                            "employee_max": 0.06,
                            "match_rate": 0.5,
                        }
                    ],
                },
                {
                    "min_years": 5,
                    "max_years": None,
                    "tiers": [
                        {
                            "employee_min": 0.0,
                            "employee_max": 0.06,
                            "match_rate": 1.0,
                        }
                    ],
                },
            ],
        }
    )
    return SimulationConfig.model_validate(payload)


@contextmanager
def database_environment(database: Path) -> Iterator[None]:
    """Temporarily route every database consumer to an isolated path."""
    previous = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(database)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = previous


def run_wait_case(
    wait_years: int, database: Path, census_parquet: Path, *, end_year: int = 2029
) -> Path:
    """Execute a canonical isolated simulation for one configured wait."""
    config = load_wait_config(wait_years, census_parquet, end_year=end_year)
    with database_environment(database):
        orchestrator = build_orchestrator(
            ConstructionSpec(
                config=config,
                database=database,
                threads=1,
                entry_point="invariant_test",
                validation_mode=True,
            )
        ).orchestrator
        orchestrator.execute_multi_year_simulation(
            start_year=config.simulation.start_year,
            end_year=config.simulation.end_year,
        )
    return database


def run_termination_rate_case(
    database: Path, census_parquet: Path, *, end_year: int = 2026
) -> Path:
    """Execute the allowed-termination service-tier scenario in isolation."""
    config = load_termination_rate_config(census_parquet, end_year=end_year)
    with database_environment(database):
        orchestrator = build_orchestrator(
            ConstructionSpec(
                config=config,
                database=database,
                threads=1,
                entry_point="invariant_test",
                validation_mode=True,
            )
        ).orchestrator
        orchestrator.execute_multi_year_simulation(
            start_year=config.simulation.start_year,
            end_year=config.simulation.end_year,
        )
    return database
