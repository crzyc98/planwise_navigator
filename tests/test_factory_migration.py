from pathlib import Path

from navigator_orchestrator.factory import (OrchestratorBuilder,
                                            create_orchestrator)
from navigator_orchestrator.migration import MigrationManager


def _write_config(tmp_path: Path):
    p = tmp_path / "cfg.yaml"
    p.write_text(
        """
simulation:
  start_year: 2025
  end_year: 2026
compensation:
  cola_rate: 0.005
  merit_budget: 0.025
enrollment:
  auto_enrollment:
    enabled: true
"""
    )
    return p


def test_orchestrator_builder_constructs(tmp_path: Path):
    cfg = _write_config(tmp_path)
    orch = (
        OrchestratorBuilder()
        .with_config(cfg)
        .with_database(tmp_path / "db.duckdb")
        .with_dbt_threads(2)
        .with_dbt_executable("echo")
        .build()
    )
    assert orch is not None


def test_create_orchestrator_helper(tmp_path: Path):
    cfg = _write_config(tmp_path)
    orch = create_orchestrator(
        cfg, threads=2, db_path=tmp_path / "db.duckdb", dbt_executable="echo"
    )
    assert hasattr(orch, "execute_multi_year_simulation")


def test_migration_manager_ops(tmp_path: Path):
    mm = MigrationManager(checkpoints_dir=tmp_path / ".ckpt")
    res = mm.migrate_checkpoints()
    assert res.success
    lst = mm.list_checkpoints()
    assert isinstance(lst, list)
