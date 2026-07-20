"""Shared fixtures for Feature 119 (#470) compiled-execution tests."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[2]
DBT_DIR = ROOT / "dbt"
SHARED_DEV_DB = DBT_DIR / "simulation.duckdb"
TINY_CENSUS_CSV = ROOT / "tests" / "fixtures" / "invariant_census.csv"
TINY_CONFIG_YAML = ROOT / "tests" / "fixtures" / "invariant_config.yaml"


class FakeDbManager:
    """Minimal stand-in exposing the db_path/close_all surface the engine uses."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.closed = 0

    def close_all(self) -> None:
        self.closed += 1


@pytest.fixture()
def isolated_db(tmp_path) -> Path:
    return tmp_path / "engine_test.duckdb"


@pytest.fixture()
def fake_db_manager(isolated_db) -> FakeDbManager:
    return FakeDbManager(isolated_db)


@pytest.fixture()
def seeded_db(isolated_db) -> Path:
    """A DuckDB file with a probe table, for write/rollback assertions."""
    with duckdb.connect(str(isolated_db)) as conn:
        conn.execute("CREATE TABLE probe_existing (id INTEGER)")
        conn.execute("INSERT INTO probe_existing VALUES (1), (2)")
    return isolated_db


def table_names(db_path: Path) -> set:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    return {r[0] for r in rows}
