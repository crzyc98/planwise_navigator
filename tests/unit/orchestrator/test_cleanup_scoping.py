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


# ---------------------------------------------------------------------------
# Feature 108 (issue #419): year-scoped purge is the DEFAULT, and it removes
# stale prior-run rows whose keys the current run never regenerates.
# ---------------------------------------------------------------------------


def _insert_stale_deferral_rows(connection) -> None:
    """Seed the issue #419 contamination shape: prior-run accumulator rows."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS int_deferral_rate_state_accumulator (
            employee_id VARCHAR NOT NULL,
            simulation_year INTEGER NOT NULL,
            current_deferral_rate DECIMAL(10, 4),
            rate_source VARCHAR,
            is_enrolled_flag BOOLEAN,
            scenario_id VARCHAR NOT NULL,
            plan_design_id VARCHAR NOT NULL,
            created_at TIMESTAMP
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO int_deferral_rate_state_accumulator VALUES
            (?, ?, 0.03, 'carried_forward', true, ?, ?, TIMESTAMP '2026-07-04 00:00:00')
        """,
        [
            # Never-enrolled employee: the new run emits NO row for this key,
            # so delete+insert alone can never remove it.
            ("EMP_NEVER_ENROLLED", 2027, "scenario-a", "plan-a"),
            # Same scenario, different year: must survive a 2027 purge.
            ("EMP_NEVER_ENROLLED", 2028, "scenario-a", "plan-a"),
            # Different scenario, same year: must survive a 2027 purge.
            ("EMP_OTHER_SCENARIO", 2027, "scenario-b", "plan-a"),
        ],
    )


def _accumulator_keys(connection) -> set[tuple[str, int, str]]:
    return {
        (row[0], row[1], row[2])
        for row in connection.execute(
            """
            SELECT employee_id, simulation_year, scenario_id
            FROM int_deferral_rate_state_accumulator
            """
        ).fetchall()
    }


@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.parametrize(
    "config",
    [
        # Studio-shaped config: no setup attribute at all.
        SimpleNamespace(scenario_id="scenario-a", plan_design_id="plan-a"),
        # setup present but not a dict.
        SimpleNamespace(scenario_id="scenario-a", plan_design_id="plan-a", setup=None),
        # setup dict without a clear_tables key (unset != false).
        SimpleNamespace(scenario_id="scenario-a", plan_design_id="plan-a", setup={}),
    ],
    ids=["no-setup-attr", "setup-none", "clear-tables-key-absent"],
)
def test_omitted_setup_defaults_to_year_scoped_cleanup(in_memory_db, config):
    _insert_scenario_rows(in_memory_db, "scenario-a")
    _insert_scenario_rows(in_memory_db, "scenario-b")
    manager = StateManager(DirectConnectionManager(in_memory_db), MagicMock(), config)

    manager.maybe_clear_year_data(2025)

    assert _scenario_counts(in_memory_db, "scenario-a") == (0, 0, 0)
    assert _scenario_counts(in_memory_db, "scenario-b") == (1, 1, 1)


@pytest.mark.fast
@pytest.mark.unit
def test_default_purge_removes_stale_keys_the_run_does_not_regenerate(in_memory_db):
    _insert_stale_deferral_rows(in_memory_db)
    manager = StateManager(
        DirectConnectionManager(in_memory_db),
        MagicMock(),
        SimpleNamespace(scenario_id="scenario-a", plan_design_id="plan-a"),
    )

    manager.maybe_clear_year_data(2027)

    assert _accumulator_keys(in_memory_db) == {
        ("EMP_NEVER_ENROLLED", 2028, "scenario-a"),
        ("EMP_OTHER_SCENARIO", 2027, "scenario-b"),
    }


@pytest.mark.fast
@pytest.mark.unit
def test_default_purge_noop_on_fresh_database():
    import duckdb

    fresh = duckdb.connect(":memory:")
    manager = StateManager(
        DirectConnectionManager(fresh),
        MagicMock(),
        SimpleNamespace(scenario_id="scenario-a", plan_design_id="plan-a"),
    )

    manager.maybe_clear_year_data(2025)  # must not raise

    assert (
        fresh.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()[0]
        == 0
    )


@pytest.mark.fast
@pytest.mark.unit
def test_explicit_clear_tables_false_opts_out_of_purge(in_memory_db):
    _insert_scenario_rows(in_memory_db, "scenario-a")
    manager = StateManager(
        DirectConnectionManager(in_memory_db),
        MagicMock(),
        SimpleNamespace(
            scenario_id="scenario-a",
            plan_design_id="plan-a",
            setup={"clear_tables": False},
        ),
    )

    manager.maybe_clear_year_data(2025)

    assert _scenario_counts(in_memory_db, "scenario-a") == (1, 1, 1)


@pytest.mark.fast
@pytest.mark.unit
def test_clear_mode_all_still_defers_year_purge_to_full_reset(in_memory_db):
    _insert_scenario_rows(in_memory_db, "scenario-a")
    manager = StateManager(
        DirectConnectionManager(in_memory_db),
        MagicMock(),
        SimpleNamespace(
            scenario_id="scenario-a",
            plan_design_id="plan-a",
            setup={"clear_tables": True, "clear_mode": "all"},
        ),
    )

    manager.maybe_clear_year_data(2025)

    # Year-level purge is skipped; the one-time full reset owns cleanup.
    assert _scenario_counts(in_memory_db, "scenario-a") == (1, 1, 1)


@pytest.mark.fast
@pytest.mark.unit
def test_full_reset_never_fires_without_explicit_directive(in_memory_db):
    _insert_scenario_rows(in_memory_db, "scenario-a")
    manager = StateManager(
        DirectConnectionManager(in_memory_db),
        MagicMock(),
        SimpleNamespace(scenario_id="scenario-a", plan_design_id="plan-a"),
    )

    manager.maybe_full_reset()

    assert _scenario_counts(in_memory_db, "scenario-a") == (1, 1, 1)


@pytest.mark.fast
@pytest.mark.unit
def test_explicit_patterns_honored_under_default_on_purge(in_memory_db):
    _insert_scenario_rows(in_memory_db, "scenario-a")
    _insert_stale_deferral_rows(in_memory_db)
    manager = StateManager(
        DirectConnectionManager(in_memory_db),
        MagicMock(),
        SimpleNamespace(
            scenario_id="scenario-a",
            plan_design_id="plan-a",
            # clear_tables unset (default on), but patterns narrowed to int_.
            setup={"clear_table_patterns": ["int_"]},
        ),
    )

    manager.maybe_clear_year_data(2027)

    # fct_ rows for other years untouched by pattern-narrowed purge...
    assert _scenario_counts(in_memory_db, "scenario-a") == (1, 1, 1)
    # ...while the stale int_ accumulator row for 2027 is purged.
    assert ("EMP_NEVER_ENROLLED", 2027, "scenario-a") not in _accumulator_keys(
        in_memory_db
    )


@pytest.mark.fast
@pytest.mark.unit
def test_warn_if_stale_years_beyond_end_year(in_memory_db, caplog):
    import logging

    _insert_scenario_rows(in_memory_db, "scenario-a")  # rows in 2025
    manager = StateManager(
        DirectConnectionManager(in_memory_db),
        MagicMock(),
        SimpleNamespace(scenario_id="scenario-a", plan_design_id="plan-a"),
    )

    with caplog.at_level(
        logging.WARNING, logger="planalign_orchestrator.pipeline.state_manager"
    ):
        manager.warn_if_stale_years_beyond(2024)  # run ends before seeded 2025
    assert any("2025" in r.message for r in caplog.records)
    # Warn-only policy: nothing deleted.
    assert _scenario_counts(in_memory_db, "scenario-a") == (1, 1, 1)

    caplog.clear()
    with caplog.at_level(
        logging.WARNING, logger="planalign_orchestrator.pipeline.state_manager"
    ):
        manager.warn_if_stale_years_beyond(2025)  # seeded year is in range
    assert not caplog.records


@pytest.mark.fast
@pytest.mark.unit
def test_warn_stale_years_noop_on_fresh_database(caplog):
    import logging

    import duckdb

    manager = StateManager(
        DirectConnectionManager(duckdb.connect(":memory:")),
        MagicMock(),
        SimpleNamespace(scenario_id="scenario-a", plan_design_id="plan-a"),
    )

    with caplog.at_level(
        logging.WARNING, logger="planalign_orchestrator.pipeline.state_manager"
    ):
        manager.warn_if_stale_years_beyond(2025)  # must not raise or warn
    assert not caplog.records
