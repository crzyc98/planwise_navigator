"""Isolated fixtures for two-scenario comparison tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


SNAPSHOT_DDL = """
CREATE TABLE fct_workforce_snapshot (
  employee_id VARCHAR,
  simulation_year INTEGER,
  employment_status VARCHAR,
  is_enrolled_flag BOOLEAN,
  current_deferral_rate DOUBLE,
  prorated_annual_contributions DOUBLE,
  employer_match_amount DOUBLE,
  employer_core_amount DOUBLE,
  prorated_annual_compensation DOUBLE
)
"""

EVENTS_DDL = """
CREATE TABLE fct_yearly_events (
  employee_id VARCHAR,
  simulation_year INTEGER,
  event_type VARCHAR
)
"""

RUN_METADATA_DDL = """
CREATE TABLE run_metadata (
  run_id VARCHAR,
  run_timestamp TIMESTAMP,
  run_type VARCHAR,
  config_fingerprint VARCHAR,
  random_seed BIGINT,
  start_year INTEGER,
  end_year INTEGER,
  scenario_id VARCHAR,
  plan_design_id VARCHAR,
  planalign_version VARCHAR,
  full_reset BOOLEAN
)
"""


def create_scenario_database(
    root: Path,
    scenario_id: str,
    rows: list[dict[str, Any]] | None = None,
    metadata: list[dict[str, Any]] | None = None,
) -> Path:
    """Create a minimal scenario DuckDB under pytest's temporary directory."""
    path = root / f"{scenario_id}.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(SNAPSHOT_DDL)
        connection.execute(EVENTS_DDL)
        _insert_snapshot_rows(connection, rows or [])
        if metadata is not None:
            connection.execute(RUN_METADATA_DDL)
            _insert_metadata_rows(connection, metadata)
    return path


def _insert_snapshot_rows(connection: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        connection.execute(
            "INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                row["employee_id"],
                row["year"],
                row.get("status", "Active"),
                row.get("enrolled", False),
                row.get("deferral_rate"),
                row.get("contributions", 0.0),
                row.get("match", 0.0),
                row.get("core", 0.0),
                row.get("compensation", 0.0),
            ],
        )


def _insert_metadata_rows(connection: Any, rows: list[dict[str, Any]]) -> None:
    for index, row in enumerate(rows):
        connection.execute(
            "INSERT INTO run_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                row.get("run_id", f"run-{index}"),
                row.get("timestamp", datetime.now(timezone.utc)),
                row.get("run_type", "batch"),
                row.get("fingerprint", "a" * 64),
                row.get("seed", 42),
                row.get("start_year", 2025),
                row.get("end_year", 2026),
                row.get("scenario_id", "scenario"),
                row.get("plan_design_id", "plan"),
                row.get("version", "test"),
                row.get("full_reset", False),
            ],
        )
