"""Integration coverage for Studio-resolved match-response events."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest
import yaml

from planalign_api.models.scenario import Scenario
from planalign_api.models.workspace import Workspace
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.config import SimulationConfig

ROOT = Path(__file__).resolve().parents[2]
INVARIANT_CONFIG = ROOT / "tests/fixtures/invariant_config.yaml"
INVARIANT_CENSUS = ROOT / "tests/fixtures/invariant_census.csv"
STUDIO_OVERRIDE = ROOT / "tests/fixtures/match_response_workspace_config.yaml"


def _workspace(base_config: dict) -> Workspace:
    now = datetime.now(timezone.utc)
    return Workspace(
        id="match-response-workspace",
        name="Match response workspace",
        created_at=now,
        updated_at=now,
        base_config=base_config,
        storage_path="/tmp/match-response-workspace",
    )


def _scenario(overrides: dict) -> Scenario:
    return Scenario(
        id="match-response-scenario",
        workspace_id="match-response-workspace",
        name="Match response scenario",
        config_overrides=overrides,
        created_at=datetime.now(timezone.utc),
    )


def _studio_config(census_path: Path) -> SimulationConfig:
    with INVARIANT_CONFIG.open() as config_file:
        base_config = yaml.safe_load(config_file)
    with STUDIO_OVERRIDE.open() as override_file:
        overrides = yaml.safe_load(override_file)
    base_config.pop("deferral_match_response", None)
    merged = WorkspaceStorage()._merge_config(
        _workspace(base_config), _scenario(overrides)
    )
    merged["setup"]["census_parquet_path"] = str(census_path)
    return SimulationConfig.model_validate(merged)


@pytest.mark.integration
def test_studio_match_response_events_reach_yearly_facts(tmp_path, monkeypatch):
    """An enabled Studio override produces first-year-only authoritative facts."""
    census_path = tmp_path / "census.parquet"
    database = tmp_path / "studio_match_response.duckdb"
    with duckdb.connect() as connection:
        connection.read_csv(str(INVARIANT_CENSUS)).write_parquet(str(census_path))

    monkeypatch.setenv("DATABASE_PATH", str(database))
    orchestrator = build_orchestrator(
        ConstructionSpec(
            config=_studio_config(census_path),
            database=database,
            threads=1,
            entry_point="studio",
            validation_mode=True,
        )
    ).orchestrator
    orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2026)

    with duckdb.connect(str(database), read_only=True) as connection:
        events = connection.execute(
            """
            SELECT simulation_year, employee_id, event_category, event_details
            FROM fct_yearly_events
            WHERE event_type = 'deferral_match_response'
            ORDER BY employee_id
            """
        ).fetchall()

    # The invariant census has 21 eligible below-threshold enrolled employees;
    # the model's deterministic hash selects these nine responders at the
    # configured 40% rate.
    assert len(events) == 9
    assert {event[0] for event in events} == {2025}
    assert all(event[2] == "match_response" for event in events)
    assert all(event[3].startswith("Match response:") for event in events)
    assert all(not event[1].startswith("NH_2025_") for event in events)
