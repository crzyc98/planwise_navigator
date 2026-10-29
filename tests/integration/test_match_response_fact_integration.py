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
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "target"))
    monkeypatch.setenv("DBT_LOG_PATH", str(tmp_path / "logs"))
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
        events = connection.execute("""
            SELECT simulation_year, employee_id, event_category, event_details
            FROM fct_yearly_events
            WHERE event_type = 'deferral_match_response'
            ORDER BY employee_id
            """).fetchall()

    # The invariant census has 21 eligible below-threshold enrolled employees;
    # the model's deterministic hash selects these nine responders at the
    # configured 40% rate.
    assert len(events) == 9
    assert {event[0] for event in events} == {2025}
    assert all(event[2] == "match_response" for event in events)
    assert all(event[3].startswith("Match response:") for event in events)
    assert all(not event[1].startswith("NH_2025_") for event in events)


@pytest.mark.integration
@pytest.mark.parametrize(
    "escalation_enabled,per_design",
    [(True, False), (False, False), (True, True)],
    ids=["escalation_on", "escalation_off", "per_design"],
)
def test_full_match_response_exceeds_annual_escalation_cap(
    tmp_path, monkeypatch, escalation_enabled, per_design
):
    """An 8% match response survives a 6% escalation ceiling across years."""
    census_path = tmp_path / "census.parquet"
    database = tmp_path / "match_above_escalation.duckdb"
    with duckdb.connect() as connection:
        connection.read_csv(str(INVARIANT_CENSUS)).write_parquet(str(census_path))

    raw = _studio_config(census_path).model_dump(mode="json")
    raw["deferral_match_response"].update(
        enabled=True,
        upward_participation_rate=1.0,
        upward_maximize_rate=1.0,
        upward_partial_increase_rate=0.0,
        downward_enabled=False,
    )
    raw["deferral_auto_escalation"].update(
        enabled=escalation_enabled,
        maximum_rate=0.06,
    )
    # Isolates the response and escalation cap: Easy Enroll escalates to its
    # own 10% cap and voluntary rate changes move responders off 8%.
    raw["easy_enroll"]["enabled"] = False
    raw["deferral_rate_changes"]["enabled"] = False
    raw["dc_plan"].update(
        match_template="tiered",
        match_tiers=[{"employee_min": 0, "employee_max": 0.08, "match_rate": 1.0}],
        match_cap_percent=0.08,
    )
    if per_design:
        raw["plan_design_parameters"] = {
            raw["plan_design_id"]: {
                "match": {
                    "cap_percent": 0.08,
                    "tiers": [
                        {"employee_min": 0, "employee_max": 0.08, "match_rate": 1},
                    ],
                },
                "employer_core": {"contribution_rate": 0.03},
                "auto_enrollment": {
                    "default_deferral_rate": 0.04,
                    "window_days": 45,
                    "scope": "all_eligible_employees",
                },
                "deferral_escalation": {"increment": 0.01, "cap": 0.06},
                "eligibility": {"waiting_period_days": 0},
            },
        }
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "target"))
    monkeypatch.setenv("DBT_LOG_PATH", str(tmp_path / "logs"))
    orchestrator = build_orchestrator(
        ConstructionSpec(
            config=SimulationConfig.model_validate(raw),
            database=database,
            threads=1,
            entry_point="studio",
            validation_mode=True,
        )
    ).orchestrator
    orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2026)

    with duckdb.connect(str(database), read_only=True) as connection:
        responders = connection.execute("""
            SELECT employee_id, employee_deferral_rate
            FROM fct_yearly_events
            WHERE event_type = 'deferral_match_response'
              AND employee_deferral_rate = 0.08
        """).fetchall()
        assert responders, "Full-match responders must be allowed to reach 8%"
        retained = connection.execute("""
            SELECT snapshot.simulation_year, snapshot.current_deferral_rate
            FROM fct_workforce_snapshot snapshot
            JOIN fct_yearly_events response USING (employee_id)
            WHERE response.event_type = 'deferral_match_response'
              AND response.employee_deferral_rate = 0.08
              AND snapshot.employment_status = 'active'
              AND snapshot.is_enrolled_flag
        """).fetchall()
        assert {row[0] for row in retained} == {2025, 2026}
        assert all(float(row[1]) == pytest.approx(0.08) for row in retained)
        simultaneous = connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events response
            JOIN fct_yearly_events escalation USING (employee_id, simulation_year)
            WHERE response.event_type = 'deferral_match_response'
              AND response.employee_deferral_rate = 0.08
              AND escalation.event_type = 'deferral_escalation'
        """).fetchone()[0]
        assert (simultaneous > 0) == escalation_enabled
        assert connection.execute("""
            SELECT COUNT(*) FROM fct_yearly_events
            WHERE event_type = 'deferral_escalation'
              AND employee_deferral_rate > 0.0601
        """).fetchone()[0] == 0
