"""End-to-end Studio fit & backtest through the real ``planalign`` CLI (#588).

Slow: the fit test spawns the real CLI; the backtest test first simulates a
four-year history and then backtests it. Both run in temp workspaces and must
leave the shared dev database untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from planalign_api.services.param_fit.runner import build_cli_command
from tests.fixtures.backtest_history import generate_backtest_history
from tests.fixtures.param_fit import history_files, make_harness

pytestmark = [pytest.mark.integration, pytest.mark.slow]

SHARED_DB = Path("dbt/simulation.duckdb")


def _shared_db_state():
    if not SHARED_DB.exists():
        return None
    stat = SHARED_DB.stat()
    return stat.st_size, stat.st_mtime_ns


def test_real_cli_fit_through_studio(tmp_path):
    history = history_files(tmp_path / "census", years=3, headcount=1_500)
    harness = make_harness(tmp_path / "studio", build_cli_command)
    history_id = harness.upload(history).json()["history_id"]
    before = _shared_db_state()

    job = harness.wait(harness.start(history_id).json()["job_id"], timeout=300)

    assert job["status"] == "completed", job
    pack = (
        harness.storage.workspaces_root
        / harness.workspace_id
        / "param_fits"
        / job["job_id"]
        / "pack"
    )
    diagnostics = json.loads((pack / "diagnostics.json").read_text())
    assert diagnostics["summary"]["snapshot_years"] == [2022, 2023, 2024]
    assert job["result"]["provenance"]["fingerprint_verified"] is True
    manifest = json.loads((pack / "manifest.json").read_text())
    assert manifest["base_seeds"].endswith("inputs/seeds")
    assert _shared_db_state() == before


def test_real_backtest_through_studio_and_apply(tmp_path):
    history = generate_backtest_history(tmp_path / "history" / "census")
    files = sorted(Path(history.directory).glob("*"))
    harness = make_harness(tmp_path / "studio", build_cli_command)
    upload = harness.upload(files)
    assert upload.status_code == 201, upload.text
    history_id = upload.json()["history_id"]
    before = _shared_db_state()

    job = harness.wait(
        harness.start(history_id, mode="backtest", seeds=[42]).json()["job_id"],
        timeout=1800,
    )

    assert job["status"] == "completed", job
    assert job["result"]["scorecard"]["verdict"] in {"pass", "warn", "fail"}
    assert job["result"]["scorecard_current"] is True
    assert job["result"]["has_fit_report"] is True
    work = (
        harness.storage.workspaces_root
        / harness.workspace_id
        / "param_fits"
        / job["job_id"]
        / "work"
    )
    assert not work.exists()
    assert _shared_db_state() == before

    preview = harness.client.get(
        harness.url(f"/param-fits/{job['job_id']}/apply-preview"),
        params={"source_scenario_id": harness.scenario_id},
    ).json()
    assert "no_backtest" not in preview["required_acknowledgements"]
    created = harness.client.post(
        harness.url(f"/param-fits/{job['job_id']}/apply"),
        json={
            "source_scenario_id": harness.scenario_id,
            "name": preview["suggested_name"],
            "pack_fingerprint": preview["pack_fingerprint"],
            "source_config_fingerprint": preview["source_config_fingerprint"],
            "acknowledgements": preview["required_acknowledgements"],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["provenance"]["backtest_verdict"] == (
        job["result"]["scorecard"]["verdict"]
    )
