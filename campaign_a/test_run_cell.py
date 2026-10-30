"""Harness contracts only: engine execution is stubbed; no simulations run."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import duckdb
import pytest
import yaml
from fastapi import HTTPException

from campaign_a import run_cell as harness
from planalign_api.services.provenance.capture import initialize_manifest, sha256_file
from planalign_orchestrator.calibration_optimizer import AutoCalibrationResult
from planalign_orchestrator.calibration_runner import PerYearCompensationResult

pytestmark = pytest.mark.fast


@pytest.fixture
def campaign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    cell = json.loads((harness.CAMPAIGN / "matrix.json").read_text())[0]
    source = tmp_path / "synthetic.parquet"
    with duckdb.connect() as conn:
        conn.execute(
            """COPY (SELECT 'SYN' || i AS employee_id,
            DATE '1990-01-01' AS employee_birth_date,
            DATE '2025-06-01' AS employee_hire_date,
            NULL::DATE AS employee_termination_date,
            50000 + i * 2000 AS employee_gross_compensation, true AS active
            FROM range(100) t(i)) TO ? (FORMAT PARQUET)""",
            [str(source)],
        )
    (campaign / "matrix.json").write_text(json.dumps([cell]))
    (campaign / "census_manifest.json").write_text(
        json.dumps(
            {cell["shape"]: {"path": str(source), "sha256": sha256_file(source)[0]}}
        )
    )
    monkeypatch.setattr(harness, "CAMPAIGN", campaign)
    monkeypatch.setattr(harness, "RUN_ROOT", tmp_path / "runs")
    return cell


async def completed_simulation(self, workspace, scenario, run_id, config):
    """Publish a tiny completed fixture using real storage and provenance APIs."""
    run_dir = self.storage.allocate_run_directory(workspace, scenario, run_id)
    database = run_dir / "simulation.duckdb"
    assert os.environ["DATABASE_PATH"] == str(database)
    assert config["simulation"]["start_year"] == 2026
    assert config["simulation"]["end_year"] == 2030
    with duckdb.connect(str(database)) as conn:
        conn.execute("CREATE TABLE fixture(value INTEGER)")
    (run_dir / "config.yaml").write_text(yaml.safe_dump(config))
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"run_id": run_id, "status": "completed"})
    )
    recorder = initialize_manifest(
        run_dir=run_dir,
        run_id=run_id,
        workspace_id=workspace,
        scenario_id=scenario,
        config=config,
        seed_root=harness.ROOT / "dbt/seeds",
        project_root=harness.ROOT,
    )
    recorder.finalize("completed")
    self.storage.publish_current_result(workspace, scenario, run_id)


class FakeCalibrator:
    def __init__(self, run, settings, threads):
        assert threads == 1
        assert os.environ["DATABASE_PATH"] == str(run.database_path)
        assert re.fullmatch(r"[a-z0-9_]+", run.database_path.stem)
        assert settings.search_mode == "new_hire_scale"
        assert not settings.lever_fallback
        assert run.params.new_hire_age_distribution
        self.run, self.settings = run, settings

    def optimize(self):
        ranges = [
            dict(
                row,
                min_compensation=row["min_compensation"] * 1.012345,
                max_compensation=row["max_compensation"] * 1.012345,
            )
            for row in self.settings.base_job_level_compensation
        ]
        return AutoCalibrationResult(
            converged=True,
            status="converged",
            message="fixture",
            best_scale=1.012345,
            best_params=self.run.params.model_copy(
                update={"job_level_compensation": ranges}
            ),
            achieved_comp_growth_pct=1,
            target_comp_growth_pct=1,
            max_abs_error_pct=0,
            start_year=2026,
            end_year=2030,
            iterations=[],
            results=[
                PerYearCompensationResult(
                    simulation_year=year,
                    headcount=100,
                    avg_compensation=75000,
                    yoy_growth_pct=None if year == 2026 else 1,
                )
                for year in range(2026, 2031)
            ],
        )


def test_complete_contract_preserves_exact_apply_and_raw_artifacts(
    campaign, monkeypatch
):
    monkeypatch.setattr(
        harness.SimulationService, "execute_simulation", completed_simulation
    )
    monkeypatch.setattr(harness, "AutoCalibrator", FakeCalibrator)
    monkeypatch.setenv("DATABASE_PATH", "prior_database")
    record = harness.run_cell(campaign["id"], 42, "baseline")
    assert record["status"] == "completed"
    assert os.environ["DATABASE_PATH"] == "prior_database"
    baseline, applied = record["baseline"], record["applied"]
    assert baseline["database"] != applied["database"]
    assert baseline["config_fingerprint"] != applied["config_fingerprint"]
    calibration = record["calibration"]
    assert calibration["context"]["source_run_id"] == baseline["run_id"]
    assert len(calibration["annual_predictions"]) == 5
    config = yaml.safe_load(Path(applied["config_path"]).read_text())
    assert config["new_hire"]["job_level_compensation"] == calibration["ranges"]
    assert calibration["apply"]["total_applied"] == 1
    for phase in (baseline, applied, calibration):
        assert Path(phase["database"]).is_relative_to(Path(record["directory"]))
    saved = json.loads(
        (harness.CAMPAIGN / "cells" / f"{campaign['id']}.json").read_text()
    )
    assert saved["runs"]["baseline"]["42"] == record
    with pytest.raises(FileExistsError):
        harness.run_cell(campaign["id"], 42, "baseline")


def test_missing_completed_baseline_cannot_calibrate(campaign, tmp_path, monkeypatch):
    directory = tmp_path / "isolated"
    directory.mkdir()
    storage, workspace, scenario, inputs = harness.prepare_workspace(
        campaign, 42, directory
    )
    monkeypatch.setattr(
        harness, "AutoCalibrator", lambda *a, **kw: pytest.fail("guard bypassed")
    )
    with pytest.raises(HTTPException, match="409"):
        harness.calibrate_and_apply(storage, workspace, scenario, campaign, inputs, {})


def test_failure_record_and_other_seed_are_preserved(campaign, monkeypatch):
    harness.save_record(campaign, 101, "baseline", {"status": "prior"})

    def fail(*args):
        raise RuntimeError("fixture execution failure")

    monkeypatch.setattr(harness, "run_full", fail)
    with pytest.raises(RuntimeError, match="fixture execution failure"):
        harness.run_cell(campaign["id"], 42, "baseline")
    saved = json.loads(
        (harness.CAMPAIGN / "cells" / f"{campaign['id']}.json").read_text()
    )
    assert saved["runs"]["baseline"]["101"] == {"status": "prior"}
    assert saved["runs"]["baseline"]["42"]["status"] == "failed"
    with pytest.raises(ValueError):
        harness.run_cell("../escape", 42, "baseline")


def test_stale_context_fails_real_apply_and_keeps_predictions(campaign, monkeypatch):
    monkeypatch.setattr(
        harness.SimulationService, "execute_simulation", completed_simulation
    )

    class StaleCalibrator(FakeCalibrator):
        def optimize(self):
            outcome = super().optimize()
            workspaces = list(self.run.database_path.parent.glob("workspaces/*"))
            storage = harness.WorkspaceStorage(
                self.run.database_path.parent / "workspaces"
            )
            workspace = storage.get_workspace(workspaces[0].name)
            config = workspace.base_config
            config["simulation"]["random_seed"] += 1
            storage.update_workspace(workspace.id, base_config=config)
            return outcome

    monkeypatch.setattr(harness, "AutoCalibrator", StaleCalibrator)
    with pytest.raises(HTTPException, match="409"):
        harness.run_cell(campaign["id"], 42, "baseline")
    saved = json.loads(
        (harness.CAMPAIGN / "cells" / f"{campaign['id']}.json").read_text()
    )
    record = saved["runs"]["baseline"]["42"]
    assert record["calibration"]["status"] == "failed"
    assert len(record["calibration"]["annual_predictions"]) == 5
    assert record["applied"] == {}


def test_frozen_census_tampering_fails_closed(campaign, monkeypatch):
    manifest = json.loads((harness.CAMPAIGN / "census_manifest.json").read_text())
    Path(manifest[campaign["shape"]]["path"]).write_bytes(b"tampered")
    monkeypatch.setattr(
        harness, "run_full", lambda *a: pytest.fail("hash guard bypassed")
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        harness.run_cell(campaign["id"], 42, "baseline")


def test_repair_stage_preserves_baseline_and_refuses_record_overwrite(
    campaign, monkeypatch
):
    harness.save_record(
        campaign, 42, "baseline", {"status": "failed", "error": "original"}
    )
    monkeypatch.setattr(
        harness.SimulationService, "execute_simulation", completed_simulation
    )
    monkeypatch.setattr(harness, "AutoCalibrator", FakeCalibrator)
    record = harness.run_cell(campaign["id"], 42, "prerequisite_repair")
    saved = json.loads(
        (harness.CAMPAIGN / "cells" / f"{campaign['id']}.json").read_text()
    )
    assert saved["runs"]["baseline"]["42"] == {"status": "failed", "error": "original"}
    assert saved["runs"]["prerequisite_repair"]["42"] == record
    assert (
        record["applied"]["attested_config_fingerprint"]
        == record["applied"]["config_fingerprint"]
    )
    # A record alone is sufficient to block overwrite, even without the run directory.
    monkeypatch.setattr(harness, "RUN_ROOT", harness.RUN_ROOT / "unused")
    with pytest.raises(FileExistsError, match="record"):
        harness.run_cell(campaign["id"], 42, "prerequisite_repair")


def test_actual_config_drift_fails_attestation(campaign, monkeypatch):
    async def drift(self, workspace, scenario, run_id, config):
        config["simulation"]["target_growth_rate"] = 0.123
        await completed_simulation(self, workspace, scenario, run_id, config)

    monkeypatch.setattr(harness.SimulationService, "execute_simulation", drift)
    with pytest.raises(ValueError, match="config mismatch"):
        harness.run_cell(campaign["id"], 42, "prerequisite_repair")
    saved = json.loads(
        (harness.CAMPAIGN / "cells" / f"{campaign['id']}.json").read_text()
    )
    assert saved["runs"]["prerequisite_repair"]["42"]["baseline"]["status"] == "failed"


def test_census_alias_resolution_is_attested(campaign, monkeypatch, tmp_path):
    monkeypatch.setattr(
        harness.SimulationService, "execute_simulation", completed_simulation
    )
    monkeypatch.setattr(harness, "AutoCalibrator", FakeCalibrator)
    record = harness.run_cell(campaign["id"], 42, "prerequisite_repair")["applied"]
    submitted = yaml.safe_load(Path(record["config_path"]).read_text())
    alias = tmp_path / "census_alias.parquet"
    alias.symlink_to(submitted["setup"]["census_parquet_path"])
    submitted["setup"]["census_parquet_path"] = str(alias)
    record["config_fingerprint"] = harness.config_fingerprint(submitted)
    result = harness.attest_config(record, submitted)
    assert (
        result["submitted_config_fingerprint"] != result["attested_config_fingerprint"]
    )
    assert result["config_attestation"]["only_change"] == "setup.census_parquet_path"
    manifest_path = Path(record["provenance_path"])
    manifest = json.loads(manifest_path.read_text())
    manifest["configuration"]["fingerprint"] = "tampered"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="attestation mismatch"):
        harness.attest_config(record, submitted)
