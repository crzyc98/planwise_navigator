import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from planalign_cli.main import app
from planalign_cli.commands import provenance as provenance_command
from tests.fixtures.run_provenance import (
    RUN_ID,
    build_archive,
    build_duplicate_archives,
)

pytestmark = pytest.mark.fast
runner = CliRunner()


def test_cli_writes_pair_refuses_overwrite_and_supports_force(tmp_path: Path):
    build_archive(tmp_path)
    output = tmp_path / "reports"
    args = [
        "provenance",
        RUN_ID,
        "--output-dir",
        str(output),
        "--workspaces-root",
        str(tmp_path),
    ]
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    report = json.loads((output / f"{RUN_ID}-provenance.json").read_text())
    markdown = (output / f"{RUN_ID}-provenance.md").read_text()
    assert report["digest"]["value"] in markdown
    assert "Fully Verified" in first.output
    assert runner.invoke(app, args).exit_code == 2
    assert runner.invoke(app, [*args, "--force"]).exit_code == 0


def test_cli_exit_codes_and_archive_write_refusal(tmp_path: Path):
    run_dir = build_archive(tmp_path)
    missing = runner.invoke(
        app,
        [
            "provenance",
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "--output-dir",
            str(tmp_path / "out"),
            "--workspaces-root",
            str(tmp_path),
        ],
    )
    assert missing.exit_code == 3
    unsafe = runner.invoke(
        app,
        [
            "provenance",
            RUN_ID,
            "--output-dir",
            str(run_dir / "reports"),
            "--workspaces-root",
            str(tmp_path),
        ],
    )
    assert unsafe.exit_code == 2


def test_paired_publication_restores_prior_pair_on_failure(tmp_path: Path, monkeypatch):
    json_path = tmp_path / "report.json"
    md_path = tmp_path / "report.md"
    json_path.write_text("old-json", encoding="utf-8")
    md_path.write_text("old-md", encoding="utf-8")
    real_replace = provenance_command.os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publication failure")
        return real_replace(source, destination)

    monkeypatch.setattr(provenance_command.os, "replace", fail_second)
    with pytest.raises(OSError, match="injected"):
        provenance_command._publish_pair(json_path, "new-json", md_path, "new-md")
    assert json_path.read_text() == "old-json"
    assert md_path.read_text() == "old-md"


def test_cli_duplicate_identity_exits_four(tmp_path: Path):
    build_duplicate_archives(tmp_path)
    result = runner.invoke(
        app,
        [
            "provenance",
            RUN_ID,
            "--output-dir",
            str(tmp_path / "output"),
            "--workspaces-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 4
