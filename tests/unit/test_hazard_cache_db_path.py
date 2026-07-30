"""Hazard cache currency must be read from the run's own database (#516).

``HazardCacheManager`` writes ``hazard_cache_metadata`` through dbt into whatever
database the run targets, but the currency check used to read it back from the
*global* path (``DATABASE_PATH`` or ``dbt/simulation.duckdb``). ``--database`` does
not set that env var — it is threaded through ``DbtRunner.database_path`` — so on
every isolated-DB run (Studio, ``planalign batch``, calibration) the stored hash
never matched and the caches were rebuilt once per simulation year.
"""

from pathlib import Path
from unittest.mock import MagicMock

import duckdb

from planalign_orchestrator.hazard_cache_manager import HazardCacheManager


RUN_HASH = "e" * 64
OTHER_HASH = "9" * 64


def _write_metadata(db_path: Path, params_hash: str) -> None:
    """Create a minimal hazard_cache_metadata table holding one current hash."""
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE hazard_cache_metadata (
                cache_name VARCHAR,
                params_hash VARCHAR,
                built_at TIMESTAMP,
                is_current BOOLEAN
            )
            """
        )
        conn.execute(
            "INSERT INTO hazard_cache_metadata VALUES "
            "('dim_termination_hazards', ?, now(), TRUE)",
            [params_hash],
        )


def _make_manager(database_path):
    dbt_runner = MagicMock()
    dbt_runner.database_path = database_path
    manager = HazardCacheManager(config=MagicMock(), dbt_runner=dbt_runner)
    manager.compute_hazard_params_hash = MagicMock(return_value=RUN_HASH)
    manager._log_cache_statistics = MagicMock()
    return manager


def test_metadata_db_path_prefers_the_runners_database(tmp_path):
    """The run's own DB wins over the global resolver."""
    run_db = tmp_path / "scenario.duckdb"
    manager = _make_manager(str(run_db))

    assert manager._metadata_db_path() == str(run_db)


def test_metadata_db_path_falls_back_to_global_resolver(monkeypatch, tmp_path):
    """A runner without a database_path (in-process/default runs) still resolves."""
    global_db = tmp_path / "simulation.duckdb"
    monkeypatch.setenv("DATABASE_PATH", str(global_db))
    manager = _make_manager(None)

    assert manager._metadata_db_path() == str(global_db)


def test_cached_hash_comes_from_the_run_db_not_the_global_one(monkeypatch, tmp_path):
    """The regression: two DBs with different hashes, only the run's may be read."""
    run_db = tmp_path / "scenario.duckdb"
    global_db = tmp_path / "simulation.duckdb"
    _write_metadata(run_db, RUN_HASH)
    _write_metadata(global_db, OTHER_HASH)
    monkeypatch.setenv("DATABASE_PATH", str(global_db))

    manager = _make_manager(str(run_db))

    assert manager.get_cached_params_hash() == RUN_HASH


def test_caches_are_current_when_the_run_db_hash_matches(monkeypatch, tmp_path):
    """No rebuild on year 2+ of an isolated-DB run — this is the 22% win in #516."""
    run_db = tmp_path / "scenario.duckdb"
    global_db = tmp_path / "simulation.duckdb"
    _write_metadata(run_db, RUN_HASH)
    _write_metadata(global_db, OTHER_HASH)
    monkeypatch.setenv("DATABASE_PATH", str(global_db))

    manager = _make_manager(str(run_db))

    assert manager.should_rebuild_caches() is False


def test_changed_parameters_still_force_a_rebuild(monkeypatch, tmp_path):
    """Invalidation must survive the fix: a different hash still rebuilds."""
    run_db = tmp_path / "scenario.duckdb"
    _write_metadata(run_db, OTHER_HASH)
    monkeypatch.setenv("DATABASE_PATH", str(run_db))

    manager = _make_manager(str(run_db))  # computes RUN_HASH, stored is OTHER_HASH

    assert manager.should_rebuild_caches() is True


def test_missing_metadata_table_rebuilds(tmp_path):
    """A fresh isolated DB has no metadata table yet — build on year 1."""
    run_db = tmp_path / "scenario.duckdb"
    duckdb.connect(str(run_db)).close()

    manager = _make_manager(str(run_db))

    assert manager.get_cached_params_hash() is None
    assert manager.should_rebuild_caches() is True
