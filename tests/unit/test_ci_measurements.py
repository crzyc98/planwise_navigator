"""Exercise CI measurement safeguards without running simulations."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "refresh_test_durations", ROOT / "scripts/refresh_test_durations.py"
)
assert SPEC is not None and SPEC.loader is not None
refresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh)


def test_merge_requires_disjoint_complete_shard_observations(tmp_path: Path) -> None:
    for index in range(1, 5):
        directory = tmp_path / f"test-durations-{index}"
        directory.mkdir()
        (directory / ".test_durations").write_text(json.dumps({f"test_{index}": index}))
    assert refresh.merge_durations(tmp_path) == {f"test_{i}": i for i in range(1, 5)}
    path = tmp_path / "test-durations-4/.test_durations"
    path.write_text('{"test_1": 4}')
    with pytest.raises(ValueError, match="Duplicate"):
        refresh.merge_durations(tmp_path)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        refresh.merge_durations(tmp_path)


def test_failed_shard_cannot_supply_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs = [{"name": f"test ({i})", "conclusion": "failure"} for i in range(1, 5)]
    monkeypatch.setattr(
        refresh.subprocess, "check_output", lambda *a, **kw: json.dumps({"jobs": jobs})
    )
    with pytest.raises(ValueError, match="did not succeed"):
        refresh.read_run("123")


def coverage_command(*arguments: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "coverage", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def combined_smoke_report(tmp_path: Path) -> Path:
    """Produce combined coverage without importing any application modules."""
    smoke = tmp_path / "smoke.py"
    smoke.write_text("value = 1\n")
    for shard in (1, 2):
        coverage_command(
            "run",
            "--rcfile=pyproject.toml",
            f"--data-file={tmp_path}/.coverage.{shard}",
            str(smoke),
        )
    data = tmp_path / ".coverage"
    coverage_command("combine", f"--data-file={data}", str(tmp_path))
    report = tmp_path / "coverage.json"
    coverage_command("json", f"--data-file={data}", "-o", str(report))
    return report


def test_combined_coverage_includes_unexecuted_shipped_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = combined_smoke_report(tmp_path)
    files = json.loads(report.read_text())["files"]
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    sources = set(config["tool"]["coverage"]["run"]["source"])
    shipped = {p.split(".")[0] for p in config["tool"]["setuptools"]["packages"]}
    assert sources == shipped
    for package in sources:
        expected = {
            p.relative_to(ROOT).as_posix() for p in (ROOT / package).rglob("*.py")
        }
        assert expected and expected <= files.keys()
        assert any(files[p]["summary"]["missing_lines"] > 0 for p in expected)
    spec = importlib.util.spec_from_file_location(
        "check_coverage_inventory", ROOT / "scripts/check_coverage_inventory.py"
    )
    assert spec is not None and spec.loader is not None
    inventory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inventory)
    monkeypatch.chdir(ROOT)
    inventory.main(report)
    content = json.loads(report.read_text())
    omitted = next(path for path in files if path.startswith("planalign_evidence/"))
    del content["files"][omitted]
    report.write_text(json.dumps(content))
    with pytest.raises(ValueError, match="Coverage omitted planalign_evidence"):
        inventory.main(report)


def test_dbt_version_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location(
        "check_dbt_versions", ROOT / "scripts/check_dbt_versions.py"
    )
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(checker, "version", lambda name: "1.8.8")
    with pytest.raises(ValueError, match="violates"):
        checker.main()
