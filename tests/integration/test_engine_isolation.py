"""#470 T016: workspace isolation — shared dev DB and shared dbt/target untouched.

A full tiny compiled run must leave `dbt/simulation.duckdb` byte-identical,
never write through shared `dbt/target/`, keep all dbt work under the run
workspace, and record zero unexpected fallbacks. An `engine=dbt` smoke
confirms default behavior is untouched by the engine's presence.
"""

import hashlib
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator import create_orchestrator
from tests.fixtures.compiled_execution import DBT_DIR, SHARED_DEV_DB
from tests.fixtures.invariant_simulation import (
    CENSUS_CSV,
    _database_environment,
    _simulation_config,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _target_mtimes():
    target = DBT_DIR / "target"
    if not target.exists():
        return {}
    return {p: p.stat().st_mtime for p in target.rglob("*") if p.is_file()}


@pytest.fixture(scope="module")
def tiny_parquet(tmp_path_factory):
    path = tmp_path_factory.mktemp("engine-iso") / "census.parquet"
    with duckdb.connect() as conn:
        conn.read_csv(str(CENSUS_CSV)).write_parquet(str(path))
    return path


def test_compiled_run_is_fully_isolated(tmp_path_factory, tiny_parquet):
    db = tmp_path_factory.mktemp("engine-iso-db") / "iso.duckdb"
    ws_root = tmp_path_factory.mktemp("engine-iso-ws")
    shared_before = _sha(SHARED_DEV_DB)
    target_before = _target_mtimes()

    config = _simulation_config(tiny_parquet)
    config.simulation.start_year = 2025
    config.simulation.end_year = 2025
    config.optimization.execution_engine = "compiled"

    import planalign_orchestrator.engine.workspace as ws_mod

    original_root = ws_mod.DEFAULT_ARTIFACT_ROOT
    ws_mod.DEFAULT_ARTIFACT_ROOT = ws_root
    try:
        with _database_environment(db):
            orchestrator = create_orchestrator(config, db_path=db, threads=1)
            orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2025)
    finally:
        ws_mod.DEFAULT_ARTIFACT_ROOT = original_root

    with duckdb.connect(str(db), read_only=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()[0] > 0

    assert _sha(SHARED_DEV_DB) == shared_before, "shared dev DB must be unchanged"
    assert _target_mtimes() == target_before, "shared dbt/target must be untouched"

    runner = orchestrator.dbt_runner
    assert runner.record_log.fallback_count == 0
    workspace_root = runner.workspace.root
    assert workspace_root.is_relative_to(ws_root)
    assert (workspace_root / "profile" / "profiles.yml").exists()
    assert any(runner.workspace.bundle_root.iterdir()), "bundles were published"


def test_dbt_engine_smoke_unaffected(tmp_path_factory, tiny_parquet):
    db = tmp_path_factory.mktemp("engine-dbt-smoke") / "dbt.duckdb"
    config = _simulation_config(tiny_parquet)
    config.simulation.start_year = 2025
    config.simulation.end_year = 2025
    config.optimization.execution_engine = "dbt"
    with _database_environment(db):
        orchestrator = create_orchestrator(config, db_path=db, threads=1)
        orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2025)
    with duckdb.connect(str(db), read_only=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()[0] > 0
    assert not hasattr(orchestrator.dbt_runner, "record_log")
