from pathlib import Path

import duckdb

from navigator_orchestrator.cli import main


def _write_config(tmp_path: Path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        """
simulation:
  start_year: 2025
  end_year: 2025
compensation:
  cola_rate: 0.005
  merit_budget: 0.025
enrollment:
  auto_enrollment:
    enabled: true
"""
    )
    return cfg


def _seed_minimal(db_path: Path):
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fct_workforce_snapshot(
            simulation_year INTEGER,
            employment_status VARCHAR,
            detailed_status_code VARCHAR,
            participation_status VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fct_yearly_events(
            employee_id VARCHAR,
            event_type VARCHAR,
            simulation_year INTEGER,
            event_date DATE
        )
        """
    )
    conn.executemany(
        "INSERT INTO fct_workforce_snapshot VALUES (?,?,?,?)",
        [(2025, "active", "active", "participating")] * 3
        + [(2025, "active", "active", "non_participating")] * 2,
    )
    conn.executemany(
        "INSERT INTO fct_yearly_events VALUES (?,?,?, DATE '2025-06-01')",
        [("E1", "hire", 2025), ("T1", "termination", 2025)],
    )
    conn.close()


def test_cli_validate_config(tmp_path: Path, capsys):
    cfg = _write_config(tmp_path)
    rc = main(["validate", "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Configuration" in out


def test_cli_run_dry_run(tmp_path: Path, capsys):
    cfg = _write_config(tmp_path)
    dbp = tmp_path / "db.duckdb"
    _seed_minimal(dbp)
    rc = main(
        ["run", "--config", str(cfg), "--database", str(dbp), "--dry-run", "--verbose"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Simulation completed" in out


def test_cli_checkpoint_listing(tmp_path: Path, capsys):
    cfg = _write_config(tmp_path)
    dbp = tmp_path / "db.duckdb"
    _seed_minimal(dbp)
    # First, run once to create a checkpoint
    rc = main(["run", "--config", str(cfg), "--database", str(dbp), "--dry-run"])
    assert rc == 0
    rc = main(["checkpoint", "--config", str(cfg), "--database", str(dbp)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Last checkpoint:" in out or "No checkpoints" in out
