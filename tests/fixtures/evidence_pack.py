"""Deterministic aggregate-only fixtures for evidence-pack tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


RUN_ID = "00000000-0000-0000-0000-000000000138"
FINGERPRINT = "1" * 64

SNAPSHOT_DDL = """
CREATE TABLE fct_workforce_snapshot (
  employee_id VARCHAR NOT NULL,
  simulation_year INTEGER NOT NULL,
  employment_status VARCHAR NOT NULL,
  prorated_annual_compensation DECIMAL(18, 2),
  employer_match_amount DECIMAL(18, 2),
  total_employer_contributions DECIMAL(18, 2),
  participation_status VARCHAR,
  current_deferral_rate DECIMAL(10, 6)
)
"""

RUN_METADATA_DDL = """
CREATE TABLE run_metadata (
  run_id VARCHAR NOT NULL,
  run_timestamp TIMESTAMP NOT NULL,
  run_type VARCHAR NOT NULL,
  config_fingerprint VARCHAR NOT NULL,
  random_seed BIGINT,
  start_year INTEGER NOT NULL,
  end_year INTEGER NOT NULL,
  scenario_id VARCHAR,
  plan_design_id VARCHAR,
  planalign_version VARCHAR,
  full_reset BOOLEAN NOT NULL DEFAULT FALSE
)
"""

DEFAULT_ROWS = (
    ("a", 2025, "active", 100, 5, 8, "participating", 0.05),
    ("b", 2025, "active", 200, 0, 4, "not_participating", 0),
    ("c", 2025, "terminated", 50, 0, 0, "not_participating", 0),
    ("d", 2025, "active", 120, 6, 9, "participating", 0.06),
    ("a", 2027, "active", 110, 6, 10, "participating", 0.06),
    ("b", 2027, "terminated", 100, 0, 2, "not_participating", 0),
    ("c", 2027, "active", 70, 3, 5, "participating", 0.04),
    ("e", 2027, "active", 150, 8, 12, "participating", 0.08),
)


@dataclass(frozen=True)
class EvidenceScenario:
    root: Path
    workspace_id: str
    scenario_id: str
    scenario_path: Path
    run_id: str
    run_dir: Path
    database_path: Path

    @property
    def result_store(self) -> str:
        return f"runs/{self.run_id}/simulation.duckdb"


def create_evidence_scenario(
    root: Path,
    *,
    rows: tuple[tuple[Any, ...], ...] = DEFAULT_ROWS,
    managed: bool = True,
    scenario_id: str = "evidence-scenario",
) -> EvidenceScenario:
    """Create one contained scenario with a completed deterministic result."""
    workspace_id = "evidence-workspace"
    scenario_path = root / "workspaces" / workspace_id / "scenarios" / scenario_id
    run_dir = scenario_path / "runs" / RUN_ID if managed else scenario_path
    run_dir.mkdir(parents=True)
    database_path = run_dir / "simulation.duckdb"
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(SNAPSHOT_DDL)
        connection.executemany(
            "INSERT INTO fct_workforce_snapshot VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            list(rows),
        )
        connection.execute(RUN_METADATA_DDL)
        connection.execute(
            "INSERT INTO run_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                RUN_ID,
                datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
                "simulate",
                FINGERPRINT,
                42,
                2025,
                2027,
                scenario_id,
                "default",
                "2.4.0",
                True,
            ],
        )
    _write_scenario_files(scenario_path, run_dir, scenario_id, managed)
    return EvidenceScenario(
        root=root,
        workspace_id=workspace_id,
        scenario_id=scenario_id,
        scenario_path=scenario_path,
        run_id=RUN_ID if managed else "legacy",
        run_dir=run_dir,
        database_path=database_path,
    )


def _write_scenario_files(
    scenario_path: Path, run_dir: Path, scenario_id: str, managed: bool
) -> None:
    scenario_path.mkdir(parents=True, exist_ok=True)
    (scenario_path / "scenario.json").write_text(
        json.dumps(
            {
                "id": scenario_id,
                "workspace_id": "evidence-workspace",
                "name": "Evidence Scenario",
                "description": None,
                "config_overrides": {},
                "status": "completed",
                "created_at": "2026-08-12T11:00:00+00:00",
                "last_run_at": "2026-08-12T12:01:00+00:00",
                "last_run_id": RUN_ID if managed else None,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    if not managed:
        return
    metadata = {
        "run_id": RUN_ID,
        "status": "completed",
        "started_at": "2026-08-12T12:00:00+00:00",
        "completed_at": "2026-08-12T12:01:00+00:00",
        "start_year": 2025,
        "end_year": 2027,
    }
    (run_dir / "run_metadata.json").write_text(
        json.dumps(metadata, sort_keys=True), encoding="utf-8"
    )
    (run_dir / "config.yaml").write_text(
        "scenario_id: evidence-scenario\nplan_design_id: default\nsimulation:\n  start_year: 2025\n  end_year: 2027\n  random_seed: 42\n",
        encoding="utf-8",
    )
    (run_dir / "provenance.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": RUN_ID,
                "capture_state": "completed",
                "validation_disposition": "passed",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (scenario_path / "current_result.json").write_text(
        json.dumps({"schema_version": 1, "run_id": RUN_ID}, sort_keys=True),
        encoding="utf-8",
    )


__all__ = [
    "DEFAULT_ROWS",
    "EvidenceScenario",
    "FINGERPRINT",
    "RUN_ID",
    "create_evidence_scenario",
]
