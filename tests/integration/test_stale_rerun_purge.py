"""Issue #419 regression: re-running a scenario purges stale prior-run state.

Seeds an isolated DuckDB with the observed contamination shape — prior-run
``int_deferral_rate_state_accumulator`` rows carrying an old ``created_at``,
including never-enrolled employees at the 3% auto-enrollment default whose
keys a re-run with auto-enrollment disabled never regenerates — then drives
the orchestrator's per-year cleanup path and asserts no pre-run row survives
any simulated year while other scenarios and un-simulated years are untouched.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pytest

from planalign_orchestrator.pipeline.state_manager import StateManager

PRIOR_RUN_TS = "TIMESTAMP '2026-07-04 00:00:00'"
RERUN_START_TS = "TIMESTAMP '2026-07-10 00:00:00'"
SIMULATED_YEARS = [2026, 2027, 2028, 2029, 2030]


class DirectConnectionManager:
    def __init__(self, connection):
        self.connection = connection

    def execute_with_retry(self, callback, **_kwargs):
        return callback(self.connection)


@pytest.fixture
def contaminated_db():
    """Isolated DB shaped like the issue #419 workspace after the first run."""
    conn = duckdb.connect(":memory:")
    conn.execute(
        """CREATE TABLE int_deferral_rate_state_accumulator (
            employee_id VARCHAR, simulation_year INTEGER,
            current_deferral_rate DECIMAL(10, 4), rate_source VARCHAR,
            is_enrolled_flag BOOLEAN, scenario_id VARCHAR,
            plan_design_id VARCHAR, created_at TIMESTAMP)"""
    )
    conn.execute(
        """CREATE TABLE int_enrollment_state_accumulator (
            employee_id VARCHAR, simulation_year INTEGER,
            enrollment_status BOOLEAN, enrollment_source VARCHAR,
            scenario_id VARCHAR, plan_design_id VARCHAR, created_at TIMESTAMP)"""
    )
    conn.execute(
        """CREATE TABLE fct_workforce_snapshot (
            employee_id VARCHAR, simulation_year INTEGER,
            participation_status VARCHAR, participation_status_detail VARCHAR,
            scenario_id VARCHAR, plan_design_id VARCHAR)"""
    )
    # Prior AE-on run: never-enrolled census employees were auto-enrolled at
    # 3% and carried forward; a re-run with AE off never re-emits these keys.
    for year in SIMULATED_YEARS:
        conn.execute(
            f"""INSERT INTO int_deferral_rate_state_accumulator VALUES
                ('EMP_2025_0002574', {year}, 0.03, 'carried_forward', true,
                 'baseline', 'default', {PRIOR_RUN_TS}),
                ('EMP_2025_0000042', {year}, 0.03, 'ae_default', true,
                 'baseline', 'default', {PRIOR_RUN_TS})"""
        )
        conn.execute(
            f"""INSERT INTO fct_workforce_snapshot VALUES
                ('EMP_2025_0002574', {year}, 'participating',
                 'participating - census enrollment', 'baseline', 'default')"""
        )
    # A different scenario sharing the DB shape must never be touched.
    conn.execute(
        f"""INSERT INTO int_deferral_rate_state_accumulator VALUES
            ('EMP_OTHER', 2027, 0.06, 'voluntary', true,
             'other-scenario', 'default', {PRIOR_RUN_TS})"""
    )
    # A year outside the re-run range (prior run went one year further).
    conn.execute(
        f"""INSERT INTO int_deferral_rate_state_accumulator VALUES
            ('EMP_2025_0002574', 2031, 0.03, 'carried_forward', true,
             'baseline', 'default', {PRIOR_RUN_TS})"""
    )
    yield conn
    conn.close()


def _rerun_state_manager(conn) -> StateManager:
    """StateManager configured like a Studio re-run: no ``setup`` block."""
    return StateManager(
        DirectConnectionManager(conn),
        MagicMock(),
        SimpleNamespace(scenario_id="baseline", plan_design_id="default"),
    )


def _rebuild_year_like_ae_off_run(conn, year: int) -> None:
    """Mimic the re-run's sparse delete+insert: rows only for enrolled employees.

    With auto-enrollment disabled, EMP_2025_0002574 / EMP_2025_0000042 never
    enroll, so the accumulator build emits nothing for them — exactly why
    delete+insert alone cannot clean the prior run's rows.
    """
    conn.execute(
        f"""INSERT INTO int_deferral_rate_state_accumulator VALUES
            ('EMP_VOLUNTARY', {year}, 0.06, 'voluntary', true,
             'baseline', 'default', {RERUN_START_TS})"""
    )


@pytest.mark.integration
def test_rerun_purges_all_stale_prior_run_rows_per_year(contaminated_db):
    manager = _rerun_state_manager(contaminated_db)

    for year in SIMULATED_YEARS:
        # Per-year order matters: purge year N before it is rebuilt, so year
        # N+1 can only ever read current-run state (forward-propagation guard).
        manager.maybe_clear_year_data(year)
        stale_in_year = contaminated_db.execute(
            f"""SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
                WHERE simulation_year = {year} AND scenario_id = 'baseline'
                  AND created_at < {RERUN_START_TS}"""
        ).fetchone()[0]
        assert stale_in_year == 0, f"stale prior-run rows survived year {year}"
        _rebuild_year_like_ae_off_run(contaminated_db, year)

    # SC-001: nothing in the simulated range predates the re-run.
    survivors = contaminated_db.execute(
        f"""SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
            WHERE scenario_id = 'baseline'
              AND simulation_year BETWEEN {SIMULATED_YEARS[0]} AND {SIMULATED_YEARS[-1]}
              AND created_at < {RERUN_START_TS}"""
    ).fetchone()[0]
    assert survivors == 0

    # Current-run rows written after each purge are intact.
    fresh = contaminated_db.execute(
        """SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
           WHERE employee_id = 'EMP_VOLUNTARY'"""
    ).fetchone()[0]
    assert fresh == len(SIMULATED_YEARS)


@pytest.mark.integration
def test_rerun_purge_respects_scenario_and_range_boundaries(contaminated_db):
    manager = _rerun_state_manager(contaminated_db)

    for year in SIMULATED_YEARS:
        manager.maybe_clear_year_data(year)

    # FR-010: other scenarios sharing the database are untouched.
    other_scenario = contaminated_db.execute(
        """SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
           WHERE scenario_id = 'other-scenario'"""
    ).fetchone()[0]
    assert other_scenario == 1

    # Years outside the simulated range are not deleted (warn-only policy).
    beyond_range = contaminated_db.execute(
        """SELECT COUNT(*) FROM int_deferral_rate_state_accumulator
           WHERE simulation_year = 2031 AND scenario_id = 'baseline'"""
    ).fetchone()[0]
    assert beyond_range == 1


@pytest.mark.integration
def test_snapshot_year_rows_purged_including_phantom_census_labels(contaminated_db):
    manager = _rerun_state_manager(contaminated_db)

    manager.maybe_clear_year_data(2027)

    phantom = contaminated_db.execute(
        """SELECT COUNT(*) FROM fct_workforce_snapshot
           WHERE simulation_year = 2027 AND scenario_id = 'baseline'"""
    ).fetchone()[0]
    assert phantom == 0
