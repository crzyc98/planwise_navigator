"""CLI coverage for the exact parity command."""

import json

from typer.testing import CliRunner

from planalign_cli.main import app
from planalign_orchestrator.tools.parity import ParityReport

runner = CliRunner()


def test_parity_json_success(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    census = tmp_path / "census.csv"
    config.write_text("simulation: {}\n")
    census.write_text("employee_id\n1\n")
    report = ParityReport(
        baseline_database="a.duckdb",
        candidate_database="b.duckdb",
        input_fingerprint="f" * 64,
    )
    monkeypatch.setattr(
        "planalign_cli.commands.parity.run_parity", lambda **_kwargs: report
    )

    result = runner.invoke(
        app,
        [
            "parity",
            "2025-2027",
            "--config",
            str(config),
            "--census",
            str(census),
            "--seed",
            "42",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["verdict"] == "IDENTICAL"
    assert payload["input_fingerprint"] == "f" * 64
    assert payload["baseline_engine"] == "dbt"
    assert payload["candidate_engine"] == "compiled"


def test_parity_rejects_missing_input(tmp_path):
    result = runner.invoke(
        app,
        [
            "parity",
            "2025",
            "--config",
            str(tmp_path / "missing.yaml"),
            "--census",
            str(tmp_path / "missing.csv"),
            "--seed",
            "42",
        ],
    )
    assert result.exit_code == 2
    assert "file not found" in result.stdout
