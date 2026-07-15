"""Session fixtures for the isolated Feature 113 simulations."""

from __future__ import annotations

import hashlib
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pandas as pd
import pytest
import duckdb

from planalign_orchestrator import create_orchestrator
from planalign_orchestrator.config import SimulationConfig, load_simulation_config

ROOT = Path(__file__).resolve().parents[2]
CENSUS_CSV = ROOT / "tests/fixtures/invariant_census.csv"
CONFIG_YAML = ROOT / "tests/fixtures/invariant_config.yaml"
ARTIFACT_DIR = ROOT / "var/test-artifacts/113"
SHARED_DEV_DB = ROOT / "dbt/simulation.duckdb"
DATE_COLUMNS = (
    "employee_birth_date",
    "employee_hire_date",
    "employee_termination_date",
    "eligibility_entry_date",
)
BOOLEAN_COLUMNS = ("active", "auto_escalation_opt_out", "eligibility_override")


@dataclass(frozen=True)
class SimulationRun:
    """Outcome of a simulation attempt, including failures for skip diagnostics."""

    database: Path
    error: BaseException | None = None


def file_signature(path: Path) -> tuple[int, str] | None:
    """Return a stable size/hash signature without opening DuckDB."""
    if not path.exists():
        return None
    return path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()


def load_census() -> pd.DataFrame:
    """Load the checked-in census with stable parquet-compatible dtypes."""
    frame = pd.read_csv(CENSUS_CSV)
    for column in DATE_COLUMNS:
        frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.date
    for column in BOOLEAN_COLUMNS:
        frame[column] = pd.array(frame[column], dtype="boolean")
    return frame


def assert_census_coverage(frame: pd.DataFrame) -> None:
    """Enforce every reference-census coverage rule from data-model.md."""
    ages = 2025 - pd.to_datetime(frame["employee_birth_date"]).dt.year
    tenures = 2025 - pd.to_datetime(frame["employee_hire_date"]).dt.year
    age_bins = pd.cut(ages, [0, 25, 35, 45, 55, 65, 999], right=False)
    tenure_bins = pd.cut(tenures, [0, 2, 5, 10, 20, 999], right=False)
    assert (age_bins.value_counts(sort=False) >= 5).all()
    assert (tenure_bins.value_counts(sort=False) >= 5).all()
    compensation = frame["employee_gross_compensation"]
    level_bins = pd.cut(
        compensation, [56_000, 81_000, 121_000, 161_000, 275_000, 500_001], right=False
    )
    assert (level_bins.value_counts(sort=False) >= 3).all()
    assert (frame["employee_deferral_rate"] > 0).sum() >= 30
    assert (frame["employee_deferral_rate"] <= 0).sum() >= 30
    cutoff = pd.Timestamp("2015-01-01")
    hire_dates = pd.to_datetime(frame["employee_hire_date"])
    assert (hire_dates < cutoff).sum() >= 5
    assert (hire_dates >= cutoff).sum() >= 5
    assert frame["employee_termination_date"].notna().sum() >= 1
    assert frame["auto_escalation_opt_out"].fillna(False).sum() >= 2
    assert (frame["scheduled_hours_per_week"] < 40).sum() >= 1


@contextmanager
def _database_environment(database: Path) -> Iterator[None]:
    previous = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(database)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = previous


def _simulation_config(census_parquet: Path) -> SimulationConfig:
    config = load_simulation_config(CONFIG_YAML, env_overrides=False)
    config.setup["census_parquet_path"] = str(census_parquet)
    return config


def _execute(database: Path, census_parquet: Path) -> SimulationRun:
    try:
        with _database_environment(database):
            orchestrator = create_orchestrator(
                _simulation_config(census_parquet), db_path=database, threads=1
            )
            orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2027)
    except BaseException as error:  # preserve full orchestrator context for pytest
        return SimulationRun(database=database, error=error)
    return SimulationRun(database=database)


def _seed_stale_snapshot(database: Path) -> None:
    """Add a prior-run row that correct per-year cleanup must remove."""
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            """
            INSERT INTO fct_workforce_snapshot
            SELECT * REPLACE ('STALE_PRIOR_RUN' AS employee_id)
            FROM fct_workforce_snapshot
            WHERE simulation_year = 2027
            LIMIT 1
            """
        )


def _preserve_on_failure(run: SimulationRun, request: pytest.FixtureRequest) -> None:
    if request.session.testsfailed == 0 or not run.database.exists():
        return
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run.database, ARTIFACT_DIR / run.database.name)


def require_successful_run(run: SimulationRun) -> Path:
    """Return the database or skip invariant evaluation after simulation failure."""
    if run.error is not None:
        pytest.skip(f"simulation failed; invariants not evaluated: {run.error!r}")
    return run.database


@pytest.fixture(scope="session")
def invariant_census_frame() -> pd.DataFrame:
    return load_census()


@pytest.fixture(scope="session")
def invariant_census_parquet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("invariant-census") / "census.parquet"
    with duckdb.connect() as connection:
        connection.read_csv(str(CENSUS_CSV)).write_parquet(str(path))
    return path


@pytest.fixture(scope="session")
def shared_dev_db_signature() -> tuple[int, str] | None:
    return file_signature(SHARED_DEV_DB)


@pytest.fixture(scope="session")
def invariant_run_a_result(
    tmp_path_factory: pytest.TempPathFactory,
    invariant_census_parquet: Path,
    shared_dev_db_signature: tuple[int, str] | None,
    request: pytest.FixtureRequest,
) -> Iterator[SimulationRun]:
    del shared_dev_db_signature
    run = _execute(
        tmp_path_factory.mktemp("invariant-run-a") / "run_a.duckdb",
        invariant_census_parquet,
    )
    yield run
    _preserve_on_failure(run, request)


@pytest.fixture(scope="session")
def invariant_run_db(invariant_run_a_result: SimulationRun) -> Path:
    return require_successful_run(invariant_run_a_result)


@pytest.fixture(scope="session")
def invariant_run_b_result(
    tmp_path_factory: pytest.TempPathFactory,
    invariant_census_parquet: Path,
    invariant_run_a_result: SimulationRun,
    shared_dev_db_signature: tuple[int, str] | None,
    request: pytest.FixtureRequest,
) -> Iterator[SimulationRun]:
    del shared_dev_db_signature
    database = tmp_path_factory.mktemp("invariant-run-b") / "run_b.duckdb"
    if invariant_run_a_result.error is not None:
        run = SimulationRun(database=database, error=invariant_run_a_result.error)
    else:
        shutil.copy2(invariant_run_a_result.database, database)
        _seed_stale_snapshot(database)
        run = _execute(database, invariant_census_parquet)
    yield run
    _preserve_on_failure(run, request)


@pytest.fixture(scope="session")
def invariant_run_db_b(invariant_run_b_result: SimulationRun) -> Path:
    return require_successful_run(invariant_run_b_result)
