"""Pytest fixtures for isolated edge-configuration simulations."""

from __future__ import annotations

import hashlib
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb
import pandas as pd
import pytest

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import load_simulation_config
from tests.edge_config.catalog import CATALOG, EdgeConfigScenario, ScenarioRun

ROOT = Path(__file__).resolve().parents[2]
SHARED_DEV_DB = ROOT / "dbt/simulation.duckdb"
ARTIFACT_DIR = ROOT / "var/test-artifacts/124"


def file_signature(path: Path) -> tuple[int, str] | None:
    if not path.exists():
        return None
    return path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()


def load_case_frame(case: EdgeConfigScenario) -> pd.DataFrame:
    frame = pd.read_csv(case.census_path)
    missing = set(case.expected_groups) - set(frame.get("boundary_group", ()))
    if missing:
        raise ValueError(
            f"{case.name}: fixture is missing boundary groups {sorted(missing)}"
        )
    counts = frame["boundary_group"].value_counts()
    empty = [group for group in case.expected_groups if counts.get(group, 0) == 0]
    if empty:
        raise ValueError(f"{case.name}: declared boundary groups are empty: {empty}")
    return frame


def effective_config_identity(config: object) -> str:
    payload = repr(
        config.model_dump(mode="json") if hasattr(config, "model_dump") else config
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


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


def run_case(case: EdgeConfigScenario, database: Path) -> ScenarioRun:
    """Run one case through the canonical construction path and retain errors."""
    config = None
    try:
        load_case_frame(case)
        config = load_simulation_config(case.config_path, env_overrides=False)
        census_parquet = database.with_suffix(".census.parquet")
        with duckdb.connect() as connection:
            connection.read_csv(str(case.census_path)).write_parquet(
                str(census_parquet)
            )
        config.setup["census_parquet_path"] = str(census_parquet)
        with _database_environment(database):
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
                start_year=case.start_year, end_year=case.end_year
            )
    except BaseException as error:  # preserve complete context for pytest diagnostics
        return ScenarioRun(
            case,
            database,
            effective_config_identity(config) if config else "setup-failed",
            error,
        )
    return ScenarioRun(case, database, effective_config_identity(config))


def preserve_failed_run(run: ScenarioRun) -> None:
    if run.completed or not run.database.exists():
        return
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run.database, ARTIFACT_DIR / run.database.name)


def require_completed(run: ScenarioRun) -> Path:
    if run.error is not None:
        pytest.fail(
            f"{run.scenario.name}: simulation failed; assertions not evaluated: {run.error!r}"
        )
    if not run.database.exists():
        pytest.fail(
            f"{run.scenario.name}: completed run did not produce {run.database}"
        )
    return run.database


@pytest.fixture(scope="session")
def edge_catalog() -> tuple[EdgeConfigScenario, ...]:
    return CATALOG


@pytest.fixture(scope="session")
def shared_edge_db_signature() -> tuple[int, str] | None:
    return file_signature(SHARED_DEV_DB)


@pytest.fixture(params=CATALOG, ids=lambda case: case.name)
def edge_case(request: pytest.FixtureRequest) -> EdgeConfigScenario:
    return request.param


@pytest.fixture
def edge_run(edge_case: EdgeConfigScenario, tmp_path: Path) -> Iterator[ScenarioRun]:
    run = run_case(edge_case, tmp_path / f"{edge_case.name}.duckdb")
    yield run
    if run.error is not None:
        preserve_failed_run(run)
