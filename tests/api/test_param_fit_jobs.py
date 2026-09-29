"""Studio fit/backtest job lifecycle (#588, US1/US2/US4).

Jobs run a stub in place of the ``planalign`` CLI (tests/fixtures/
param_fit_stub.py) that speaks the real progress protocol and exit codes, so
every outcome — success, each failure class, cancellation, restart — is
exercised through the real runner and API without fitting anything.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from planalign_api.models.param_fit import JobInputs, ParamFitJob, ParamFitRequest
from planalign_api.services.param_fit.jobs import JobStore
from planalign_api.services.param_fit.runner import ProcessRegistry
from tests.fixtures.param_fit import (
    StubCommands,
    add_current_scorecard,
    build_fixture_pack,
    history_files,
    make_harness,
)

pytestmark = [pytest.mark.fast]


@pytest.fixture(scope="module")
def history(tmp_path_factory) -> list[Path]:
    return history_files(tmp_path_factory.mktemp("history") / "census", years=3)


@pytest.fixture(scope="module")
def fixture_pack(tmp_path_factory, history) -> Path:
    return build_fixture_pack(history[0].parent, tmp_path_factory.mktemp("p") / "pack")


@pytest.fixture(scope="module")
def backtest_pack(tmp_path_factory, fixture_pack) -> Path:
    pack = tmp_path_factory.mktemp("bt") / "pack"
    shutil.copytree(fixture_pack, pack)
    add_current_scorecard(pack, verdict="warn")
    return pack


@pytest.fixture
def commands(fixture_pack) -> StubCommands:
    return StubCommands(fixture_pack=fixture_pack)


@pytest.fixture
def harness(tmp_path, commands):
    return make_harness(tmp_path, commands)


@pytest.fixture
def history_id(harness, history) -> str:
    response = harness.upload(history)
    assert response.status_code == 201, response.text
    return response.json()["history_id"]


# ---------------------------------------------------------------------------
# JobStore
# ---------------------------------------------------------------------------


def _job(workspace_id: str, job_id: str, created: datetime, status="completed"):
    return ParamFitJob(
        job_id=job_id,
        workspace_id=workspace_id,
        mode="fit",
        status=status,
        created_at=created,
        request=ParamFitRequest(history_id="hist_x", base_scenario_id="s"),
        inputs=JobInputs(
            history_id="hist_x",
            source_digest="d",
            snapshots=[],
            base_scenario_id="s",
            base_scenario_name="Baseline",
            base_scenario_fingerprint="f",
        ),
    )


def test_store_round_trips_and_lists_newest_first(tmp_path):
    store = JobStore(tmp_path)
    older = _job("ws", "fit_a", datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = _job("ws", "fit_b", datetime(2026, 2, 1, tzinfo=timezone.utc))
    store.save(older)
    store.save(newer)

    assert [job.job_id for job in store.list_jobs("ws")] == ["fit_b", "fit_a"]
    assert store.load("ws", "fit_a") == older
    assert not list((tmp_path / "ws" / "param_fits" / "fit_a").glob(".job-*"))


def test_store_rejects_path_like_ids(tmp_path):
    assert JobStore(tmp_path).load("ws", "../escape") is None


def test_prune_keeps_the_newest_finished_and_every_active_job(tmp_path):
    store = JobStore(tmp_path)
    for day, job_id in enumerate(("fit_a", "fit_b", "fit_c"), start=1):
        store.save(_job("ws", job_id, datetime(2026, 1, day, tzinfo=timezone.utc)))
    store.save(
        _job("ws", "fit_old", datetime(2025, 1, 1, tzinfo=timezone.utc), "running")
    )

    removed = store.prune_finished("ws", 2, protect={"fit_old"})

    assert removed == ["fit_a"]
    assert {job.job_id for job in store.list_jobs("ws")} == {
        "fit_b",
        "fit_c",
        "fit_old",
    }


# ---------------------------------------------------------------------------
# Fit jobs (US1)
# ---------------------------------------------------------------------------


def test_launch_returns_immediately_and_completes(harness, history_id):
    started = time.monotonic()
    response = harness.start(history_id)
    elapsed = time.monotonic() - started

    assert response.status_code == 202, response.text
    assert elapsed < 2.0
    assert response.json()["status"] == "queued"
    job = harness.wait(response.json()["job_id"])
    assert job["status"] == "completed", job


def test_completed_fit_exposes_summary_diagnostics_and_provenance(
    harness, history_id, fixture_pack
):
    job = harness.wait(harness.start(history_id).json()["job_id"])
    result = job["result"]

    assert result["summary"]["snapshot_years"] == [2022, 2023, 2024]
    assert result["summary"]["fitted_count"] > 0
    rows = [row for group in result["diagnostics"].values() for row in group]
    assert rows and all("thin" in row and "exposure" in row for row in rows)
    assert result["summary"]["thin_count"] == sum(row["thin"] for row in rows)
    assert result["provenance"]["fingerprint_verified"] is True
    assert len(result["provenance"]["sources"]) == 3
    assert result["stale"] == []
    assert result["scorecard"] is None
    assert result["has_fit_report"] is True


def test_job_records_its_inputs(harness, history_id):
    job = harness.wait(
        harness.start(history_id, fit_options={"credibility_k": 7.5}).json()["job_id"]
    )
    inputs = job["inputs"]

    assert inputs["base_scenario_name"] == "Baseline"
    assert len(inputs["base_scenario_fingerprint"]) == 64
    assert [s["year"] for s in inputs["snapshots"]] == [2022, 2023, 2024]
    assert inputs["moved_settings"] == {"fit_options.credibility_k": 7.5}
    job_dir = harness.storage.workspaces_root / harness.workspace_id / "param_fits"
    inputs_dir = job_dir / job["job_id"] / "inputs"
    assert (inputs_dir / "base_config.yaml").is_file()
    assert (inputs_dir / "seeds" / "config_age_bands.csv").is_file()


def test_reports_are_served_as_markdown(harness, history_id):
    job_id = harness.wait(harness.start(history_id).json()["job_id"])["job_id"]

    fit = harness.client.get(harness.url(f"/param-fits/{job_id}/reports/fit"))
    scorecard = harness.client.get(
        harness.url(f"/param-fits/{job_id}/reports/scorecard")
    )

    assert fit.status_code == 200
    assert fit.headers["content-type"].startswith("text/markdown")
    assert fit.text.startswith("#")
    assert scorecard.status_code == 404


def test_job_list_summarizes(harness, history_id):
    job_id = harness.wait(harness.start(history_id).json()["job_id"])["job_id"]

    listed = harness.client.get(harness.url("/param-fits")).json()

    assert [item["job_id"] for item in listed] == [job_id]
    assert listed[0]["pack_id"]
    assert listed[0]["snapshot_years"] == [2022, 2023, 2024]


@pytest.mark.parametrize(
    "behaviour, kind, status",
    [
        ("exit:2", "invalid_input", 422),
        ("exit:3", "invalid_history", 422),
        ("exit:4", "output_conflict", 409),
    ],
)
def test_cli_exit_codes_classify_failures(
    harness, history_id, commands, behaviour, kind, status
):
    commands.behaviour = behaviour
    job = harness.wait(harness.start(history_id).json()["job_id"])

    assert job["status"] == "failed"
    assert job["error"]["kind"] == kind
    assert job["error"]["status"] == status
    assert "stub failure message for pack" in job["error"]["message"]
    assert str(harness.storage.workspaces_root) not in job["error"]["message"]


def test_unexpected_exit_is_sanitized(harness, history_id, commands):
    commands.behaviour = "exit:9"
    job = harness.wait(harness.start(history_id).json()["job_id"])

    assert job["error"]["kind"] == "unexpected"
    assert job["error"]["status"] == 500
    assert "stub failure" not in job["error"]["message"]


def test_failed_job_leaves_no_pack(harness, history_id, commands):
    commands.behaviour = "exit:3"
    job = harness.wait(harness.start(history_id).json()["job_id"])
    job_dir = (
        harness.storage.workspaces_root
        / harness.workspace_id
        / "param_fits"
        / job["job_id"]
    )

    assert not (job_dir / "pack").exists()
    assert (job_dir / "job.log").is_file()


@pytest.mark.parametrize(
    "overrides, status",
    [
        ({"base_scenario_id": "missing"}, 404),
        ({"history_id": "hist_missing"}, 404),
        ({"mode": "backtest", "holdout_years": 2}, 422),
        ({"mode": "backtest", "seeds": [1, 1]}, 422),
        ({"mode": "backtest", "seeds": []}, 422),
        ({"thresholds": {"headcount": {"warn": 0.05, "fail": 0.01}}}, 422),
        ({"fit_options": {"level_coverage_threshold": 1.5}}, 422),
    ],
)
def test_invalid_launch_requests_are_refused(harness, history_id, overrides, status):
    response = harness.start(history_id, **overrides)

    assert response.status_code == status, response.text
    assert harness.client.get(harness.url("/param-fits")).json() == []


def test_backtest_split_error_names_the_problem(harness, history_id):
    response = harness.start(history_id, mode="backtest", holdout_years=2)

    assert "leaves 1 year to fit" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Backtest jobs, cancellation, concurrency (US2)
# ---------------------------------------------------------------------------


def test_backtest_reports_seed_progress_and_scorecard(
    harness, history_id, commands, backtest_pack
):
    commands.behaviour = "backtest"
    commands.fixture_pack = backtest_pack
    job = harness.wait(
        harness.start(history_id, mode="backtest", seeds=[42, 43]).json()["job_id"]
    )

    assert job["status"] == "completed", job
    assert job["inputs"]["split"]["holdout_years"] == [2024]
    assert job["result"]["scorecard"]["verdict"] == "warn"
    assert job["result"]["scorecard_current"] is True
    assert job["result"]["summary"]["verdict"] == "warn"
    command = commands.calls[-1]
    assert command[2] == "backtest"


def test_backtest_command_carries_the_request(harness, history_id, fixture_pack):
    from planalign_api.services.param_fit.runner import JobPaths, build_cli_command

    job = ParamFitJob.model_validate(
        {
            **_job("ws", "fit_x", datetime.now(timezone.utc)).model_dump(),
            "mode": "backtest",
            "request": ParamFitRequest(
                history_id="h",
                base_scenario_id="s",
                mode="backtest",
                holdout_years=2,
                seeds=[7, 8],
                thresholds={"flows": {"warn": 0.2, "fail": 0.3}},
            ).model_dump(),
        }
    )
    paths = JobPaths(
        history_files=Path("/h"),
        base_config=Path("/c.yaml"),
        seeds_dir=Path("/s"),
        pack_dir=Path("/p"),
        work_dir=Path("/w"),
    )
    command = build_cli_command(job, paths)

    assert command[3:5] == ["backtest", "/h"]
    joined = " ".join(command)
    assert "--holdout 2" in joined
    assert "--seed-list 7,8" in joined
    assert "--threshold-flows 0.2,0.3" in joined
    assert "--workdir /w" in joined
    assert "--seeds-dir /s" in joined and "--config /c.yaml" in joined


def test_simulation_failure_names_seed_and_year(harness, history_id, commands):
    commands.behaviour = "simfail"
    job = harness.wait(
        harness.start(history_id, mode="backtest", seeds=[43]).json()["job_id"]
    )

    error = job["error"]
    assert error["kind"] == "simulation_failure"
    assert error["status"] == 500
    assert (error["failed_seed"], error["failed_year"]) == (43, 2025)
    assert str(harness.storage.workspaces_root) not in error["message"]


def test_cancel_stops_the_process_and_removes_artifacts(harness, history_id, commands):
    commands.behaviour = "sleep"
    job_id = harness.start(history_id).json()["job_id"]
    harness.wait_for_stage(job_id, "fitting")

    started = time.monotonic()
    response = harness.client.post(harness.url(f"/param-fits/{job_id}/cancel"))
    elapsed = time.monotonic() - started

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert elapsed < 10.0
    job_dir = harness.storage.workspaces_root / harness.workspace_id / "param_fits"
    assert not (job_dir / job_id / "pack").exists()
    assert not (job_dir / job_id / "work").exists()
    again = harness.client.post(harness.url(f"/param-fits/{job_id}/cancel"))
    assert again.status_code == 409


def test_one_backtest_per_workspace(harness, history, commands):
    history_id = harness.upload(history).json()["history_id"]
    commands.behaviour = "sleep"
    four = harness.start(history_id, mode="backtest", seeds=[42])
    assert four.status_code == 202, four.text
    job_id = four.json()["job_id"]
    try:
        second = harness.start(history_id, mode="backtest", seeds=[42])
        fit = harness.start(history_id)
        assert second.status_code == 409
        assert "already running" in second.json()["detail"]
        assert fit.status_code == 202
    finally:
        for item in harness.client.get(harness.url("/param-fits")).json():
            if item["status"] not in ("completed", "failed", "cancelled"):
                harness.client.post(harness.url(f"/param-fits/{item['job_id']}/cancel"))
    assert harness.wait(job_id)["status"] == "cancelled"


def test_history_in_use_cannot_be_deleted(harness, history_id, commands):
    commands.behaviour = "sleep"
    job_id = harness.start(history_id).json()["job_id"]
    try:
        response = harness.client.delete(harness.url(f"/fit-history/{history_id}"))
        assert response.status_code == 409
    finally:
        harness.client.post(harness.url(f"/param-fits/{job_id}/cancel"))


# ---------------------------------------------------------------------------
# Restart and retention (US4)
# ---------------------------------------------------------------------------


def test_completed_jobs_survive_a_restart(harness, history_id):
    job_id = harness.wait(harness.start(history_id).json()["job_id"])["job_id"]

    harness.registry = ProcessRegistry()  # a fresh API process owns nothing
    job = harness.client.get(harness.url(f"/param-fits/{job_id}")).json()

    assert job["status"] == "completed"
    assert job["result"]["provenance"]["fingerprint_verified"] is True


def test_running_job_from_a_dead_process_reads_as_interrupted(harness):
    store = JobStore(harness.storage.workspaces_root)
    store.save(
        _job(
            harness.workspace_id,
            "fit_orphan",
            datetime.now(timezone.utc),
            status="running",
        )
    )

    job = harness.client.get(harness.url("/param-fits/fit_orphan")).json()

    assert job["status"] == "failed"
    assert job["error"]["kind"] == "interrupted"


def test_retention_prunes_the_oldest_finished_jobs(tmp_path, commands, history):
    harness = make_harness(tmp_path, commands, max_jobs=2)
    history_id = harness.upload(history).json()["history_id"]
    finished = [
        harness.wait(harness.start(history_id).json()["job_id"])["job_id"]
        for _ in range(3)
    ]

    # Pruning runs as each job finishes; allow the last worker to get there.
    deadline = time.monotonic() + 5
    listed: list[str] = []
    while time.monotonic() < deadline:
        listed = [
            i["job_id"] for i in harness.client.get(harness.url("/param-fits")).json()
        ]
        if len(listed) == 2:
            break
        time.sleep(0.05)
    assert listed == list(reversed(finished[1:]))


def test_request_defaults_match_the_cli_engine():
    from planalign_api.models.param_fit import FitOptionsModel, ThresholdsModel
    from planalign_backtest.models import MetricThresholds
    from planalign_fit import FitOptions

    thresholds = ThresholdsModel().model_dump()
    engine = MetricThresholds().model_dump()
    assert thresholds == {
        family: {"warn": engine[family]["warn"], "fail": engine[family]["fail"]}
        for family in engine
    }
    options = FitOptionsModel()
    cli = FitOptions()
    assert options.credibility_k == cli.credibility_k
    assert options.min_exposure == cli.min_exposure
    assert options.level_coverage_threshold == cli.level_coverage_threshold
    assert options.separation_exposure_gate == cli.separation_exposure_gate
