"""Applying a reviewed parameter pack to a NEW Studio scenario (#588, US3)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from planalign_api.services.simulation.run_execution import (
    scenario_pack_seeds,
    write_seeds,
)
from planalign_fit import load_pack
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


@pytest.fixture
def commands(fixture_pack) -> StubCommands:
    return StubCommands(fixture_pack=fixture_pack)


@pytest.fixture
def harness(tmp_path, commands):
    return make_harness(tmp_path, commands)


@pytest.fixture
def completed(harness, history) -> dict:
    history_id = harness.upload(history).json()["history_id"]
    job = harness.wait(harness.start(history_id).json()["job_id"])
    assert job["status"] == "completed", job.get("error")
    return job


def _preview(harness, job_id: str, source: str | None = None):
    return harness.client.get(
        harness.url(f"/param-fits/{job_id}/apply-preview"),
        params={"source_scenario_id": source or harness.scenario_id},
    )


def _apply(harness, job_id: str, preview: dict, **overrides):
    body = {
        "source_scenario_id": preview["source_scenario_id"],
        "name": preview["suggested_name"],
        "pack_fingerprint": preview["pack_fingerprint"],
        "source_config_fingerprint": preview["source_config_fingerprint"],
        "acknowledgements": preview["required_acknowledgements"],
    }
    body.update(overrides)
    return harness.client.post(harness.url(f"/param-fits/{job_id}/apply"), json=body)


def _job_pack(harness, job_id: str) -> Path:
    return (
        harness.storage.workspaces_root
        / harness.workspace_id
        / "param_fits"
        / job_id
        / "pack"
    )


def _source_files(harness) -> dict[str, bytes]:
    root = harness.storage._scenario_path(harness.workspace_id, harness.scenario_id)
    return {
        name: (root / name).read_bytes() for name in ("scenario.json", "overrides.yaml")
    }


def test_preview_lists_fingerprints_acknowledgements_and_diff(harness, completed):
    response = _preview(harness, completed["job_id"])

    assert response.status_code == 200, response.text
    preview = response.json()
    manifest = load_pack(_job_pack(harness, completed["job_id"])).manifest
    assert preview["pack_fingerprint"] == manifest.fingerprint
    assert len(preview["source_config_fingerprint"]) == 64
    assert "no_backtest" in preview["required_acknowledgements"]
    thin = completed["result"]["summary"]["thin_count"]
    assert ("thin_cells" in preview["required_acknowledgements"]) == bool(thin)
    assert ("unfittable" in preview["required_acknowledgements"]) == bool(
        manifest.unfittable
    )
    paths = {delta["path"] for delta in preview["diff"]}
    assert any(path.startswith("promotion_hazard") for path in paths)
    assert not any(path.startswith("param_pack") for path in paths)
    assert preview["suggested_name"] == "Baseline — fitted 2022–2024"
    assert "config_termination_hazard_base.csv" in preview["seed_files"]


def test_apply_creates_a_new_scenario_and_preserves_the_source(harness, completed):
    before = _source_files(harness)
    preview = _preview(harness, completed["job_id"]).json()

    response = _apply(harness, completed["job_id"], preview)

    assert response.status_code == 201, response.text
    scenario = response.json()
    assert scenario["id"] != harness.scenario_id
    assert _source_files(harness) == before
    provenance = scenario["provenance"]
    assert provenance["source"] == "param_pack"
    assert provenance["param_fit_job_id"] == completed["job_id"]
    assert provenance["pack_fingerprint"] == preview["pack_fingerprint"]
    assert provenance["source_scenario_id"] == harness.scenario_id
    assert provenance["backtest_verdict"] is None
    assert provenance["acknowledgements"] == sorted(
        preview["required_acknowledgements"]
    )


def test_new_scenario_carries_the_pack_into_its_runs(harness, completed, tmp_path):
    preview = _preview(harness, completed["job_id"]).json()
    scenario_id = _apply(harness, completed["job_id"], preview).json()["id"]
    pack = load_pack(_job_pack(harness, completed["job_id"]))

    merged = harness.storage.get_merged_config(harness.workspace_id, scenario_id)
    scenario_dir = harness.storage._scenario_path(harness.workspace_id, scenario_id)
    write_seeds(merged, tmp_path / "run", scenario_pack_seeds(scenario_dir))

    assert merged["param_pack"]["fingerprint"] == pack.manifest.fingerprint
    seeds = tmp_path / "run" / "seeds"
    for name, text in pack.seed_files.items():
        written = (seeds / name).read_text(encoding="utf-8")
        if name.startswith("config_promotion_hazard"):
            # Rewritten from the scenario's promotion_hazard section, so it is
            # numerically — not byte — identical to the pack's seed.
            assert _numbers(written) == pytest.approx(_numbers(text))
        else:
            assert written == text


def _numbers(csv_text: str) -> list[float]:
    values = []
    for line in csv_text.strip().splitlines()[1:]:
        for cell in line.split(","):
            try:
                values.append(float(cell))
            except ValueError:
                continue
    return values


def test_pack_fragment_reaches_the_new_scenario(harness, completed):
    preview = _preview(harness, completed["job_id"]).json()
    scenario_id = _apply(harness, completed["job_id"], preview).json()["id"]
    pack = load_pack(_job_pack(harness, completed["job_id"]))

    merged = harness.storage.get_merged_config(harness.workspace_id, scenario_id)

    fitted = pack.config_fragment["workforce"]["total_termination_rate"]
    assert merged["workforce"]["total_termination_rate"] == pytest.approx(fitted)


def test_later_studio_edits_win_over_the_pack(harness, completed, tmp_path):
    preview = _preview(harness, completed["job_id"]).json()
    scenario = _apply(harness, completed["job_id"], preview).json()
    overrides = dict(scenario["config_overrides"])
    overrides["promotion_hazard"] = {
        **overrides["promotion_hazard"],
        "base_rate": 0.0123,
    }
    harness.storage.update_scenario(
        harness.workspace_id, scenario["id"], config_overrides=overrides
    )

    merged = harness.storage.get_merged_config(harness.workspace_id, scenario["id"])
    scenario_dir = harness.storage._scenario_path(harness.workspace_id, scenario["id"])
    write_seeds(merged, tmp_path / "run", scenario_pack_seeds(scenario_dir))

    promotion = tmp_path / "run" / "seeds" / "config_promotion_hazard_base.csv"
    assert "0.0123" in promotion.read_text()


def test_missing_acknowledgements_are_refused(harness, completed):
    preview = _preview(harness, completed["job_id"]).json()
    count = len(harness.storage.list_scenarios(harness.workspace_id))

    response = _apply(harness, completed["job_id"], preview, acknowledgements=[])

    assert response.status_code == 422
    assert set(response.json()["missing_acknowledgements"]) == set(
        preview["required_acknowledgements"]
    )
    assert len(harness.storage.list_scenarios(harness.workspace_id)) == count


def test_name_collision_suggests_a_free_name(harness, completed):
    preview = _preview(harness, completed["job_id"]).json()

    response = _apply(harness, completed["job_id"], preview, name="baseline")

    assert response.status_code == 409
    assert response.json()["suggested_name"] == "baseline (2)"


def test_edited_history_blocks_apply(harness, completed):
    preview = _preview(harness, completed["job_id"]).json()
    files = (
        harness.storage.workspaces_root
        / harness.workspace_id
        / "fit_history"
        / completed["inputs"]["history_id"]
        / "files"
    )
    target = next(files.glob("*2023*"))
    target.write_text(target.read_text() + target.read_text().splitlines()[1] + "\n")

    job = harness.client.get(harness.url(f"/param-fits/{completed['job_id']}")).json()
    response = _apply(harness, completed["job_id"], preview)

    assert [s["reason"] for s in job["result"]["stale"]] == ["history_changed"]
    assert response.status_code == 409
    assert response.json()["stale"][0]["reason"] == "history_changed"


def test_edited_pack_blocks_apply(harness, completed):
    preview = _preview(harness, completed["job_id"]).json()
    seed = _job_pack(harness, completed["job_id"]) / "seeds"
    target = seed / "config_termination_hazard_base.csv"
    target.write_text(target.read_text().replace("0.", "0.9", 1))

    response = _apply(harness, completed["job_id"], preview)

    assert response.status_code == 409
    assert response.json()["stale"][0]["reason"] == "pack_modified"


def test_source_changed_since_review_blocks_apply(harness, completed):
    preview = _preview(harness, completed["job_id"]).json()
    harness.storage.update_scenario(
        harness.workspace_id,
        harness.scenario_id,
        config_overrides={"workforce": {"total_termination_rate": 0.5}},
    )
    count = len(harness.storage.list_scenarios(harness.workspace_id))

    response = _apply(harness, completed["job_id"], preview)

    assert response.status_code == 409
    assert response.json()["stale"][0]["reason"] == "source_scenario_changed"
    assert len(harness.storage.list_scenarios(harness.workspace_id)) == count


def test_changed_base_scenario_is_informational(harness, completed):
    harness.storage.update_scenario(
        harness.workspace_id,
        harness.scenario_id,
        config_overrides={"workforce": {"total_termination_rate": 0.5}},
    )

    job = harness.client.get(harness.url(f"/param-fits/{completed['job_id']}")).json()
    preview = _preview(harness, completed["job_id"])

    assert [s["reason"] for s in job["result"]["stale"]] == ["base_scenario_changed"]
    assert preview.status_code == 200
    assert _apply(harness, completed["job_id"], preview.json()).status_code == 201


def test_only_completed_jobs_apply(harness, history, commands):
    commands.behaviour = "exit:3"
    history_id = harness.upload(history).json()["history_id"]
    job = harness.wait(harness.start(history_id).json()["job_id"])

    response = _preview(harness, job["job_id"])

    assert response.status_code == 409


def test_unknown_source_scenario_is_404(harness, completed):
    assert _preview(harness, completed["job_id"], source="missing").status_code == 404


@pytest.mark.parametrize(
    "verdict, expected, absent",
    [
        ("warn", "backtest_warn", "no_backtest"),
        ("fail", "backtest_fail", "no_backtest"),
        ("pass", None, "no_backtest"),
    ],
)
def test_backtest_verdict_drives_acknowledgements(
    harness, history, commands, fixture_pack, tmp_path, verdict, expected, absent
):
    pack = tmp_path / f"pack-{verdict}"
    shutil.copytree(fixture_pack, pack)
    add_current_scorecard(pack, verdict=verdict)
    commands.fixture_pack = pack
    history_id = harness.upload(history).json()["history_id"]
    job = harness.wait(harness.start(history_id).json()["job_id"])

    required = _preview(harness, job["job_id"]).json()["required_acknowledgements"]

    assert absent not in required
    if expected:
        assert expected in required


def test_stale_scorecard_counts_as_no_backtest(
    harness, history, commands, fixture_pack, tmp_path
):
    pack = tmp_path / "pack-stale-score"
    shutil.copytree(fixture_pack, pack)
    add_current_scorecard(pack, verdict="pass")
    score = pack / "backtest" / "scorecard.json"
    payload = json.loads(score.read_text())
    payload["provenance"]["pack_fingerprint"] = "0" * 64
    score.write_text(json.dumps(payload))
    commands.fixture_pack = pack
    history_id = harness.upload(history).json()["history_id"]
    job = harness.wait(harness.start(history_id).json()["job_id"])

    required = _preview(harness, job["job_id"]).json()["required_acknowledgements"]

    assert job["result"]["scorecard_current"] is False
    assert "no_backtest" in required


def test_runs_record_the_pack_even_after_studio_drops_the_block(
    harness, completed, tmp_path
):
    """A Config Studio save rebuilds overrides and drops ``param_pack``; the
    run must still record the pack whose seeds it layers in."""
    import yaml
    from unittest.mock import patch

    from planalign_api.services.simulation.service import SimulationService

    preview = _preview(harness, completed["job_id"]).json()
    scenario = _apply(harness, completed["job_id"], preview).json()
    overrides = {
        key: value
        for key, value in scenario["config_overrides"].items()
        if key != "param_pack"
    }
    harness.storage.update_scenario(
        harness.workspace_id, scenario["id"], config_overrides=overrides
    )
    config = harness.storage.get_merged_config(harness.workspace_id, scenario["id"])
    assert "param_pack" not in config
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    service = SimulationService(harness.storage)
    with patch("planalign_api.services.simulation.service.validate_census"):
        service._prepare_simulation(
            harness.workspace_id, scenario["id"], config, run_dir
        )

    written = yaml.safe_load((run_dir / "config.yaml").read_text())
    assert written["param_pack"]["fingerprint"] == preview["pack_fingerprint"]


def test_hand_edited_verdict_cannot_soften_the_review(
    harness, history, commands, fixture_pack, tmp_path
):
    """Verdicts are re-derived from the comparisons, so editing one is inert."""
    pack = tmp_path / "pack-edited-verdict"
    shutil.copytree(fixture_pack, pack)
    add_current_scorecard(pack, verdict="fail")
    score = pack / "backtest" / "scorecard.json"
    payload = json.loads(score.read_text())
    payload["verdict"] = "pass"
    score.write_text(json.dumps(payload))
    commands.fixture_pack = pack
    history_id = harness.upload(history).json()["history_id"]
    job = harness.wait(harness.start(history_id).json()["job_id"])

    required = _preview(harness, job["job_id"]).json()["required_acknowledgements"]

    assert job["result"]["scorecard"]["verdict"] == "fail"
    assert "backtest_fail" in required


def test_tampered_comparisons_do_not_count_as_a_backtest(
    harness, history, commands, fixture_pack, tmp_path
):
    pack = tmp_path / "pack-edited-numbers"
    shutil.copytree(fixture_pack, pack)
    add_current_scorecard(pack, verdict="fail")
    score = pack / "backtest" / "scorecard.json"
    payload = json.loads(score.read_text())
    payload["comparisons"][0]["percent_error"] = 0.001
    score.write_text(json.dumps(payload))
    commands.fixture_pack = pack
    history_id = harness.upload(history).json()["history_id"]
    job = harness.wait(harness.start(history_id).json()["job_id"])

    required = _preview(harness, job["job_id"]).json()["required_acknowledgements"]

    assert job["result"]["scorecard_current"] is False
    assert "no_backtest" in required
