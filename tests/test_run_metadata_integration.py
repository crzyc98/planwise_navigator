"""
Integration tests for config drift detection wiring (Feature 109).

Covers:
- T007 (US1): PipelineOrchestrator stamps at run start, warns on drift before
  year execution, and never stamps on dry_run.
- T013 (US3): the run_metadata history is append-only, self-describing, and
  survives a setup.clear_tables full reset (with full_reset recorded).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.config import (
    CompensationSettings,
    EnrollmentSettings,
    SimulationConfig,
    SimulationSettings,
)
from planalign_orchestrator.dbt_runner import DbtResult, DbtRunner
from planalign_orchestrator.construction import ConstructionSpec, build_orchestrator
from planalign_orchestrator.run_metadata import RUN_METADATA_TABLE
from planalign_orchestrator.utils import DatabaseConnectionManager

pytestmark = [pytest.mark.integration, pytest.mark.slow]

LOGGER_NAME = "planalign_orchestrator.run_metadata"


class DummyRunner(DbtRunner):
    def __init__(self, working_dir: Path):
        super().__init__(working_dir=working_dir, executable="echo")

    def execute_command(self, *args, **kwargs):
        return DbtResult(True, "ok", "", 0.0, 0, ["echo"])

    def run_models(self, models, *, parallel=False, **kwargs):
        return [DbtResult(True, m, "", 0.0, 0, ["echo", m]) for m in models]


def _seed_minimal(db_path: Path, years) -> None:
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "CREATE TABLE fct_workforce_snapshot(simulation_year INTEGER, "
        "employment_status VARCHAR, detailed_status_code VARCHAR, "
        "participation_status VARCHAR)"
    )
    conn.execute(
        "CREATE TABLE fct_yearly_events(employee_id VARCHAR, event_type VARCHAR, "
        "simulation_year INTEGER, event_date DATE)"
    )
    conn.execute(
        "CREATE TABLE int_enrollment_state_accumulator(employee_id VARCHAR, "
        "simulation_year INTEGER, enrollment_date DATE)"
    )
    conn.execute(
        "CREATE TABLE int_deferral_rate_state_accumulator(employee_id VARCHAR, "
        "simulation_year INTEGER, deferral_rate DECIMAL(10,4))"
    )
    for y in years:
        conn.executemany(
            "INSERT INTO fct_workforce_snapshot VALUES (?,?,?,?)",
            [(y, "active", "active", "participating")] * 3
            + [(y, "active", "active", "non_participating")] * 2,
        )
        conn.executemany(
            "INSERT INTO fct_yearly_events VALUES (?,?,?, DATE '" + str(y) + "-06-01')",
            [(f"E{y}{i}", "hire", y) for i in range(2)],
        )
    conn.close()


def _make_config(
    *, growth: float = 0.03, seed: int = 42, setup=None
) -> SimulationConfig:
    return SimulationConfig(
        scenario_id="test-scenario",
        plan_design_id="test-plan",
        simulation=SimulationSettings(
            start_year=2025, end_year=2026, random_seed=seed, target_growth_rate=growth
        ),
        compensation=CompensationSettings(),
        enrollment=EnrollmentSettings(),
        setup=setup if setup is not None else {"clear_tables": False},
    )


def _make_orchestrator(cfg: SimulationConfig, db_path: Path, tmp_path: Path):
    mgr = DatabaseConnectionManager(db_path=db_path)
    result = build_orchestrator(
        ConstructionSpec(
            config=cfg,
            database=mgr,
            runner_override=DummyRunner(working_dir=tmp_path),
            reports_dir=tmp_path / "reports",
            entry_point="invariant_test",
        )
    )
    return (
        result.orchestrator,
        mgr,
    )


def _run(orchestrator, monkeypatch, *, dry_run: bool = False):
    """Execute the multi-year entry point with year execution stubbed out.

    Year stages need real dbt; the drift check fires before them, so a no-op
    year executor exercises the real wiring (mutex, reset, stamp) end-to-end.
    """
    monkeypatch.setattr(
        type(orchestrator),
        "_execute_year_with_monitoring",
        lambda self, year, **kw: None,
    )
    return orchestrator.execute_multi_year_simulation(dry_run=dry_run)


def _metadata_rows(db_path: Path) -> list[tuple]:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        return conn.execute(
            f"SELECT run_type, config_fingerprint, random_seed, start_year, "
            f"end_year, full_reset, run_timestamp FROM {RUN_METADATA_TABLE} "
            f"ORDER BY run_timestamp"
        ).fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# T007 (US1): orchestrator wiring
# ---------------------------------------------------------------------------


class TestOrchestratorWiring:
    def test_execution_context_run_id_is_stamped(self, tmp_path, monkeypatch):
        dbp = tmp_path / "p.duckdb"
        _seed_minimal(dbp, [2025, 2026])
        run_id = str(uuid.uuid4())
        monkeypatch.setenv("PLANALIGN_RUN_ID", run_id)
        orchestrator, manager = _make_orchestrator(_make_config(), dbp, tmp_path)
        _run(orchestrator, monkeypatch)
        manager.close_all()
        with duckdb.connect(str(dbp), read_only=True) as connection:
            assert (
                connection.execute(
                    f"SELECT run_id FROM {RUN_METADATA_TABLE}"
                ).fetchone()[0]
                == run_id
            )

    def test_second_run_with_changed_config_warns_and_completes(
        self, tmp_path, monkeypatch, caplog
    ):
        dbp = tmp_path / "p.duckdb"
        _seed_minimal(dbp, [2025, 2026])

        orch1, mgr1 = _make_orchestrator(_make_config(growth=0.03), dbp, tmp_path)
        _run(orch1, monkeypatch)
        mgr1.close_all()

        orch2, mgr2 = _make_orchestrator(_make_config(growth=0.05), dbp, tmp_path)
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            summary = _run(orch2, monkeypatch)
        mgr2.close_all()

        warnings = [
            r
            for r in caplog.records
            if r.name == LOGGER_NAME and r.levelno == logging.WARNING
        ]
        assert len(warnings) == 1
        assert "CONFIG DRIFT DETECTED" in warnings[0].getMessage()
        # Non-blocking (FR-005): the run completed despite the warning.
        assert summary is not None
        assert len(_metadata_rows(dbp)) == 2

    def test_unchanged_rerun_is_silent(self, tmp_path, monkeypatch, caplog):
        dbp = tmp_path / "p.duckdb"
        _seed_minimal(dbp, [2025, 2026])

        for _ in range(2):
            orch, mgr = _make_orchestrator(_make_config(), dbp, tmp_path)
            with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
                _run(orch, monkeypatch)
            mgr.close_all()

        assert not [
            r
            for r in caplog.records
            if r.name == LOGGER_NAME and r.levelno == logging.WARNING
        ]
        assert len(_metadata_rows(dbp)) == 2

    def test_dry_run_stamps_no_record(self, tmp_path, monkeypatch):
        dbp = tmp_path / "p.duckdb"
        _seed_minimal(dbp, [2025, 2026])

        orch, mgr = _make_orchestrator(_make_config(), dbp, tmp_path)
        _run(orch, monkeypatch, dry_run=True)
        mgr.close_all()

        conn = duckdb.connect(str(dbp), read_only=True)
        try:
            exists = conn.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='main' AND table_name=?",
                [RUN_METADATA_TABLE],
            ).fetchone()
        finally:
            conn.close()
        assert exists is None


# ---------------------------------------------------------------------------
# T013 (US3): auditable history
# ---------------------------------------------------------------------------


class TestAuditableHistory:
    def test_history_is_self_describing(self, tmp_path, monkeypatch):
        dbp = tmp_path / "p.duckdb"
        _seed_minimal(dbp, [2025, 2026])

        orch1, mgr1 = _make_orchestrator(
            _make_config(growth=0.03, seed=42), dbp, tmp_path
        )
        _run(orch1, monkeypatch)
        mgr1.close_all()
        orch2, mgr2 = _make_orchestrator(
            _make_config(growth=0.05, seed=99), dbp, tmp_path
        )
        _run(orch2, monkeypatch)
        mgr2.close_all()

        rows = _metadata_rows(dbp)
        assert len(rows) == 2
        first, second = rows
        assert first[0] == second[0] == "simulate"
        assert first[1] != second[1]  # distinct fingerprints
        assert (first[2], second[2]) == (42, 99)
        assert (first[3], first[4]) == (2025, 2026)
        assert second[6] >= first[6]  # timestamps ordered

    def test_history_survives_full_reset_and_records_flag(self, tmp_path, monkeypatch):
        dbp = tmp_path / "p.duckdb"
        _seed_minimal(dbp, [2025, 2026])

        orch1, mgr1 = _make_orchestrator(_make_config(growth=0.03), dbp, tmp_path)
        _run(orch1, monkeypatch)
        mgr1.close_all()

        reset_setup = {
            "clear_tables": True,
            "clear_mode": "all",
            "clear_table_patterns": ["int_", "fct_"],
        }
        orch2, mgr2 = _make_orchestrator(
            _make_config(growth=0.05, setup=reset_setup), dbp, tmp_path
        )
        _run(orch2, monkeypatch)

        with mgr2.get_connection() as conn:
            fct_rows = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot"
            ).fetchone()[0]
        mgr2.close_all()

        assert fct_rows == 0  # full reset wiped fact tables...
        rows = _metadata_rows(dbp)
        assert len(rows) == 2  # ...but run history survived
        assert [r[5] for r in rows] == [False, True]  # full_reset recorded
