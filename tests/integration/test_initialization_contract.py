"""End-to-end contracts for explicit fresh-database initialization."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import (
    ConstructionSpec,
    InitializationPolicy,
    build_orchestrator,
)
from planalign_orchestrator.exceptions import InitializationError


def _config(census: Path):
    config = load_simulation_config(
        Path("tests/fixtures/invariant_config.yaml"), env_overrides=False
    )
    config.setup["census_parquet_path"] = str(census)
    config.simulation.start_year = 2025
    config.simulation.end_year = 2025
    return config


def _tiny_census(path: Path) -> Path:
    with duckdb.connect() as conn:
        conn.read_csv("tests/fixtures/invariant_census.csv").write_parquet(str(path))
    return path


def _assert_multiset_equal(first: Path, second: Path, table: str) -> None:
    timestamp_columns = {"created_at", "snapshot_created_at"}
    with duckdb.connect() as conn:
        conn.execute(f"ATTACH '{first}' AS first_run (READ_ONLY)")
        conn.execute(f"ATTACH '{second}' AS second_run (READ_ONLY)")
        columns = [
            row[0]
            for row in conn.execute(f"DESCRIBE first_run.{table}").fetchall()
            if row[0] not in timestamp_columns
        ]
        projection = ", ".join(f'"{column}"' for column in columns)
        for left, right in (
            ("first_run", "second_run"),
            ("second_run", "first_run"),
        ):
            differences = conn.execute(
                f"""
                SELECT COUNT(*) FROM (
                    SELECT {projection} FROM {left}.{table}
                    EXCEPT ALL
                    SELECT {projection} FROM {right}.{table}
                )
                """
            ).fetchone()[0]
            assert differences == 0


@pytest.mark.parametrize("entry_point", ["cli.simulate", "batch"])
def test_forced_critical_initialization_failure_aborts_without_outputs(
    monkeypatch, tmp_path, entry_point
):
    database = tmp_path / "failed.duckdb"

    class FailingInitializer:
        def __init__(self, **_kwargs):
            pass

        def ensure_initialized(self):
            return SimpleNamespace(
                success=False,
                error="forced foundation failure",
                missing_tables_found=["int_baseline_workforce"],
            )

    monkeypatch.setattr(
        "planalign_orchestrator.construction.builder.AutoInitializer",
        FailingInitializer,
    )
    result = build_orchestrator(
        ConstructionSpec(
            config=_config(tmp_path / "unused.parquet"),
            database=database,
            initialization=InitializationPolicy.SELF_HEALING,
            entry_point=entry_point,
            validation_mode=True,
        )
    )

    with pytest.raises(InitializationError) as captured:
        result.orchestrator.execute_multi_year_simulation(
            start_year=2025, end_year=2025
        )

    error = captured.value
    assert error.context.correlation_id
    assert error.context.metadata["failed_step"] == "pre_simulation"
    assert error.resolution_hints
    if database.exists():
        with result.orchestrator.db_manager.get_connection() as conn:
            tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
            for table in ("fct_yearly_events", "fct_workforce_snapshot"):
                assert table not in tables


@pytest.mark.integration
def test_fresh_none_matches_explicitly_preinitialized_database(tmp_path):
    census = _tiny_census(tmp_path / "census.parquet")
    fresh_database = tmp_path / "fresh.duckdb"
    initialized_database = tmp_path / "initialized.duckdb"

    for database, policy, entry_point in (
        (fresh_database, InitializationPolicy.NONE, "cli.simulate"),
        (initialized_database, InitializationPolicy.SELF_HEALING, "batch"),
    ):
        result = build_orchestrator(
            ConstructionSpec(
                config=_config(census),
                database=database,
                initialization=policy,
                entry_point=entry_point,
                validation_mode=True,
            )
        )
        result.orchestrator.execute_multi_year_simulation(
            start_year=2025, end_year=2025
        )

    _assert_multiset_equal(fresh_database, initialized_database, "fct_yearly_events")
    _assert_multiset_equal(
        fresh_database, initialized_database, "fct_workforce_snapshot"
    )
