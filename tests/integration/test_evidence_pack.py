"""Isolated API/CLI evidence-pack parity checks."""

from typer.testing import CliRunner

from planalign_api import config as api_config
from planalign_api.services.evidence_pack_service import get_scenario_evidence_pack
from planalign_cli.main import app
from planalign_ensemble.models import CANONICAL_METRICS
from planalign_evidence.service import EvidenceTarget, build_evidence_pack
from tests.fixtures.evidence_pack import create_evidence_scenario


def test_all_metrics_are_deterministic_read_only_and_cli_text_matches_api(
    tmp_path, monkeypatch
) -> None:
    scenario = create_evidence_scenario(tmp_path)
    monkeypatch.setattr(
        api_config,
        "settings",
        api_config.APISettings(workspaces_root=tmp_path / "workspaces"),
    )
    before = scenario.database_path.stat()
    target = EvidenceTarget(
        scenario.database_path,
        scenario.result_store,
        scenario.scenario_id,
        scenario.run_id,
    )
    for metric in CANONICAL_METRICS:
        first = build_evidence_pack(target, metric, 2025, 2027)
        assert first == build_evidence_pack(target, metric, 2025, 2027)
        assert first.residual.contribution.value == "0"

    envelope = get_scenario_evidence_pack(
        scenario.workspace_id, scenario.scenario_id, "employer_match_cost", 2025, 2027
    )
    cli = CliRunner().invoke(
        app,
        [
            "evidence-pack",
            str(scenario.scenario_path),
            "--metric",
            "employer_match_cost",
            "--base-year",
            "2025",
            "--target-year",
            "2027",
        ],
    )
    after = scenario.database_path.stat()
    assert cli.exit_code == 0, cli.output
    assert cli.stdout == envelope.text_export
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
