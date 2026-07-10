"""Regression coverage for scenario-scoped pipeline cleanup."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.pipeline.data_cleanup import DataCleanupManager
from planalign_orchestrator.pipeline.state_manager import StateManager


class DirectConnectionManager:
    """Run cleanup callbacks against the shared in-memory DuckDB fixture."""

    def __init__(self, connection):
        self.connection = connection

    def execute_with_retry(self, callback):
        return callback(self.connection)


def _insert_scenario_rows(
    connection, scenario_id: str, plan_design_id: str = "plan-a"
) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS fct_employer_match_events (
            simulation_year INTEGER NOT NULL,
            scenario_id VARCHAR NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO fct_yearly_events VALUES
            (?, 'employee-1', 'hire', DATE '2025-01-01', 2025, ?, ?, '{}')
        """,
        [f"event-{scenario_id}-{plan_design_id}", scenario_id, plan_design_id],
    )
    connection.execute(
        """
        INSERT INTO fct_workforce_snapshot VALUES
            ('employee-1', 2025, 100000, NULL, ?, ?)
        """,
        [scenario_id, plan_design_id],
    )
    connection.execute(
        "INSERT INTO fct_employer_match_events VALUES (2025, ?)", [scenario_id]
    )


def _scenario_counts(connection, scenario_id: str) -> tuple[int, int, int]:
    events = connection.execute(
        "SELECT COUNT(*) FROM fct_yearly_events WHERE scenario_id = ?", [scenario_id]
    ).fetchone()[0]
    snapshots = connection.execute(
        "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE scenario_id = ?",
        [scenario_id],
    ).fetchone()[0]
    employer_matches = connection.execute(
        "SELECT COUNT(*) FROM fct_employer_match_events WHERE scenario_id = ?",
        [scenario_id],
    ).fetchone()[0]
    return events, snapshots, employer_matches


@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.parametrize("cleanup_method", ["clear_year_fact_rows", "clear_year_data"])
def test_data_cleanup_keeps_other_scenario_critical_fact_rows(
    in_memory_db, cleanup_method
):
    _insert_scenario_rows(in_memory_db, "scenario-a")
    _insert_scenario_rows(in_memory_db, "scenario-b")
    cleanup = DataCleanupManager(
        DirectConnectionManager(in_memory_db),
        scenario_id="scenario-a",
        plan_design_id="plan-a",
    )

    getattr(cleanup, cleanup_method)(2025)

    assert _scenario_counts(in_memory_db, "scenario-a") == (0, 0, 0)
    assert _scenario_counts(in_memory_db, "scenario-b") == (1, 1, 1)


@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.parametrize(
    "cleanup_method", ["clear_year_fact_rows", "maybe_clear_year_data"]
)
def test_state_manager_year_cleanup_keeps_other_scenario_critical_fact_rows(
    in_memory_db, cleanup_method
):
    _insert_scenario_rows(in_memory_db, "scenario-a")
    _insert_scenario_rows(in_memory_db, "scenario-b")
    config = SimpleNamespace(
        scenario_id="scenario-a",
        plan_design_id="plan-a",
        setup={
            "clear_tables": True,
            "clear_mode": "year",
            "clear_table_patterns": ["fct_"],
        },
    )
    manager = StateManager(DirectConnectionManager(in_memory_db), MagicMock(), config)

    getattr(manager, cleanup_method)(2025)

    assert _scenario_counts(in_memory_db, "scenario-a") == (0, 0, 0)
    assert _scenario_counts(in_memory_db, "scenario-b") == (1, 1, 1)


@pytest.mark.fast
@pytest.mark.unit
def test_omitted_clear_mode_defaults_to_year_scoped_cleanup(in_memory_db):
    _insert_scenario_rows(in_memory_db, "scenario-a")
    _insert_scenario_rows(in_memory_db, "scenario-b")
    manager = StateManager(
        DirectConnectionManager(in_memory_db),
        MagicMock(),
        SimpleNamespace(
            scenario_id="scenario-a",
            plan_design_id="plan-a",
            setup={"clear_tables": True, "clear_table_patterns": ["fct_"]},
        ),
    )

    manager.maybe_clear_year_data(2025)

    assert _scenario_counts(in_memory_db, "scenario-a") == (0, 0, 0)
    assert _scenario_counts(in_memory_db, "scenario-b") == (1, 1, 1)


@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.parametrize("manager_type", ["data_cleanup", "state_manager"])
def test_critical_fact_cleanup_falls_back_to_default_scenario_when_unconfigured(
    in_memory_db, manager_type
):
    """Ordinary single-scenario runs don't set scenario_id/plan_design_id in
    config (see config/simulation_config.yaml). dbt itself defaults those
    columns to 'default' (planalign_orchestrator/config/export.py,
    dbt/models/marts/fct_yearly_events.sql), so cleanup must scope to
    'default' rather than raising - raising here would break the primary
    `planalign simulate` workflow, which never sets an explicit scenario_id.
    """
    _insert_scenario_rows(in_memory_db, "default", "default")
    _insert_scenario_rows(in_memory_db, "scenario-b", "plan-a")

    if manager_type == "data_cleanup":
        manager = DataCleanupManager(DirectConnectionManager(in_memory_db))
    else:
        manager = StateManager(
            DirectConnectionManager(in_memory_db),
            MagicMock(),
            SimpleNamespace(scenario_id=None, plan_design_id=None),
        )

    manager.clear_year_fact_rows(2025)

    assert _scenario_counts(in_memory_db, "default") == (0, 0, 0)
    assert _scenario_counts(in_memory_db, "scenario-b") == (1, 1, 1)
