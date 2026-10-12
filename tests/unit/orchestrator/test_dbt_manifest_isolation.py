"""Graph-contract parsing must own its artifacts under parallel execution."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.helpers import dbt_manifest


@pytest.fixture
def isolated_helper(tmp_path: Path, monkeypatch):
    root = tmp_path / "project"
    shared_target = root / "dbt/target"
    shared_target.mkdir(parents=True)
    (shared_target / "manifest.json").write_text("incomplete concurrent manifest")
    monkeypatch.setattr(dbt_manifest, "ROOT", root)
    monkeypatch.setattr(dbt_manifest.shutil, "which", lambda _: "dbt")
    dbt_manifest.load_production_manifest.cache_clear()
    yield shared_target
    dbt_manifest.load_production_manifest.cache_clear()


def test_parse_reads_owned_manifest_and_cleans_artifacts(
    isolated_helper: Path, monkeypatch
) -> None:
    targets = []

    def parse(*args, **kwargs):
        env = kwargs["env"]
        target = Path(env["DBT_TARGET_PATH"])
        targets.append(target)
        assert target.parent == Path(env["DATABASE_PATH"]).parent
        assert target.parent == Path(env["DBT_LOG_PATH"]).parent
        target.mkdir()
        (target / "manifest.json").write_text(json.dumps({"nodes": {"owned": {}}}))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(dbt_manifest.subprocess, "run", parse)
    assert dbt_manifest.load_production_manifest() == {"nodes": {"owned": {}}}
    assert (
        isolated_helper / "manifest.json"
    ).read_text() == "incomplete concurrent manifest"
    assert not targets[0].parent.exists()
    dbt_manifest.load_production_manifest.cache_clear()
    dbt_manifest.load_production_manifest()
    assert targets[0] != targets[1]


def test_parse_failure_retains_diagnostics_and_cleans_artifacts(
    isolated_helper: Path, monkeypatch
) -> None:
    targets = []

    def parse(*args, **kwargs):
        targets.append(Path(kwargs["env"]["DBT_TARGET_PATH"]))
        return SimpleNamespace(
            returncode=1, stdout="parse output", stderr="parse error"
        )

    monkeypatch.setattr(dbt_manifest.subprocess, "run", parse)
    with pytest.raises(AssertionError, match="(?s)parse output.*parse error"):
        dbt_manifest.load_production_manifest()
    assert not targets[0].parent.exists()
