"""CLI parity and safe-output tests for evidence packs."""

from typer.testing import CliRunner

from planalign_cli.main import app
from planalign_evidence.render import build_envelope
from planalign_evidence.service import EvidenceTarget, build_evidence_pack
from planalign_api.services.evidence_pack_service import apply_archive_trust
from tests.fixtures.evidence_pack import create_evidence_scenario

runner = CliRunner()


def test_cli_stdout_matches_shared_renderer_and_does_not_write(tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path)
    before = scenario.database_path.stat()
    result = runner.invoke(
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
    expected_pack = build_evidence_pack(
        EvidenceTarget(
            scenario.database_path,
            scenario.result_store,
            scenario.scenario_id,
            scenario.run_id,
            scenario.workspace_id,
            "Evidence Scenario",
        ),
        "employer_match_cost",
        2025,
        2027,
    )
    expected_pack, archive_warnings = apply_archive_trust(
        expected_pack, scenario.root / "workspaces", scenario.run_id
    )
    expected_pack = expected_pack.model_copy(
        update={"warnings": (*expected_pack.warnings, *archive_warnings)}
    )
    expected = build_envelope(expected_pack).text_export
    after = scenario.database_path.stat()
    assert result.exit_code == 0, result.output
    assert result.stdout == expected
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)


def test_cli_atomic_output_force_and_diagnostics(tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path)
    output = tmp_path / "exports" / "pack.md"
    arguments = [
        "evidence-pack",
        str(scenario.scenario_path),
        "--metric",
        "active_headcount",
        "--base-year",
        "2025",
        "--target-year",
        "2027",
        "--output",
        str(output),
    ]
    first = runner.invoke(app, arguments)
    assert first.exit_code == 0
    assert output.read_text(encoding="utf-8").startswith("# Evidence Pack")
    assert runner.invoke(app, arguments).exit_code == 2
    assert runner.invoke(app, [*arguments, "--force"]).exit_code == 0


def test_cli_supports_legacy_and_rejects_missing_year(tmp_path) -> None:
    scenario = create_evidence_scenario(tmp_path / "legacy", managed=False)
    base = [
        "evidence-pack",
        str(scenario.scenario_path),
        "--metric",
        "participation_rate",
        "--base-year",
        "2025",
    ]
    good = runner.invoke(app, [*base, "--target-year", "2027"])
    assert good.exit_code == 0
    assert "legacy_result" in good.stdout
    bad = runner.invoke(app, [*base, "--target-year", "2026"])
    assert bad.exit_code == 2
    assert "available years" in bad.stderr
