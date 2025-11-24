from pathlib import Path

import duckdb

from planalign_orchestrator.config import (CompensationSettings,
                                           EnrollmentSettings,
                                           SimulationConfig,
                                           SimulationSettings)
from planalign_orchestrator.dbt_runner import DbtResult, DbtRunner
from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator
from planalign_orchestrator.registries import RegistryManager
from planalign_orchestrator.utils import DatabaseConnectionManager
from planalign_orchestrator.validation import (DataValidator,
                                               HireTerminationRatioRule)


class DummyRunner(DbtRunner):
    def __init__(self, working_dir: Path):
        super().__init__(working_dir=working_dir, executable="echo")

    def execute_command(self, *args, **kwargs):
        return DbtResult(True, "ok", "", 0.0, 0, ["echo"])

    def run_models(self, models, *, parallel=False, **kwargs):
        return [DbtResult(True, m, "", 0.0, 0, ["echo", m]) for m in models]


def _seed_minimal(db_path: Path, years):
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE fct_workforce_snapshot(
            simulation_year INTEGER,
            employment_status VARCHAR,
            detailed_status_code VARCHAR,
            participation_status VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fct_yearly_events(
            employee_id VARCHAR,
            event_type VARCHAR,
            simulation_year INTEGER,
            event_date DATE
        )
        """
    )
    for y in years:
        # 5 active, 3 participating
        conn.executemany(
            "INSERT INTO fct_workforce_snapshot VALUES (?,?,?,?)",
            [(y, "active", "active", "participating")] * 3
            + [(y, "active", "active", "non_participating")] * 2,
        )
        # simple events
        conn.executemany(
            "INSERT INTO fct_yearly_events VALUES (?,?,?, DATE '" + str(y) + "-06-01')",
            [(f"E{y}{i}", "hire", y) for i in range(2)]
            + [(f"T{y}{i}", "termination", y) for i in range(1)],
        )
    conn.close()


def test_multi_year_workflow_coordination(tmp_path: Path):
    dbp = tmp_path / "p.duckdb"
    _seed_minimal(dbp, [2025, 2026])

    cfg = SimulationConfig(
        simulation=SimulationSettings(start_year=2025, end_year=2026),
        compensation=CompensationSettings(),
        enrollment=EnrollmentSettings(),
    )
    mgr = DatabaseConnectionManager(db_path=dbp)
    registries = RegistryManager(mgr)
    runner = DummyRunner(working_dir=tmp_path)
    dv = DataValidator(mgr)
    dv.register_rule(HireTerminationRatioRule())

    orchestrator = PipelineOrchestrator(
        cfg,
        mgr,
        runner,
        registries,
        dv,
        reports_dir=tmp_path / "reports",
        checkpoints_dir=tmp_path / "ckpt",
    )
    summary = orchestrator.execute_multi_year_simulation()

    # Summary spans both years and writes CSV
    assert summary.start_year == 2025 and summary.end_year == 2026
    csv_path = tmp_path / "reports" / "multi_year_summary_2025_2026.csv"
    assert csv_path.exists()

    # Checkpoints exist for both years
    assert (tmp_path / "ckpt" / "year_2025.json").exists()
    assert (tmp_path / "ckpt" / "year_2026.json").exists()
