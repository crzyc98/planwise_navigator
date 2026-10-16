"""Prevent risk selection and skipped jobs from silently weakening CI."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ci_policy", ROOT / "scripts/ci_policy.py"
)
assert SPEC is not None and SPEC.loader is not None
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


@pytest.mark.parametrize(
    "paths, expected",
    [
        (["docs/guides/example.md", "README.md"], False),
        (["planalign_studio/components/Example.tsx"], False),
        (["planalign_studio/package-lock.json"], False),
        (["planalign_studio/App.tsx", "planalign_api/main.py"], True),
        (["dbt/models/int_example.sql"], True),
        (["planalign_orchestrator/config.py"], True),
        (["tests/conftest.py"], True),
        (["requirements.txt"], True),
        ([".github/workflows/ci.yml"], True),
        (["docs/example.py"], True),
        (["new_package/logic.py"], True),
        ([], True),
    ],
)
def test_conservative_simulation_selection(paths: list[str], expected: bool) -> None:
    assert policy.needs_simulation(paths) is expected


def results() -> dict[str, dict]:
    jobs = {name: {"result": "success"} for name in policy.BASE_JOBS | {"ci-scope"}}
    jobs.update(
        {
            name: {"result": "skipped"}
            for name in policy.SIMULATION_JOBS | policy.FULL_JOBS
        }
    )
    return jobs


def test_skips_allowed_only_when_not_required() -> None:
    jobs = results()
    assert not policy.gate_errors(jobs, simulation=False, full=False)
    assert len(policy.gate_errors(jobs, simulation=True, full=False)) == 2
    assert len(policy.gate_errors(jobs, simulation=True, full=True)) == 4
    for job in jobs.values():
        job["result"] = "success"
    assert not policy.gate_errors(jobs, simulation=True, full=True)


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", None])
def test_baseline_check_must_succeed(result: str | None) -> None:
    jobs = results()
    jobs["fast-tests"]["result"] = result
    assert policy.gate_errors(jobs, simulation=False, full=False)
    del jobs["fast-tests"]
    assert policy.gate_errors(jobs, simulation=False, full=False)


def test_optional_failure_cannot_be_hidden() -> None:
    jobs = results()
    jobs["test"]["result"] = "failure"
    assert policy.gate_errors(jobs, simulation=False, full=False)


@pytest.mark.parametrize(
    "event_name, labels", [("push", []), ("pull_request", [{"name": "full-ci"}])]
)
def test_full_run_needs_no_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event_name: str, labels: list[dict]
) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"labels": labels}}))
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    policy.select()
    assert output.read_text() == "full=true\nsimulation=true\n"


def test_workflow_gate_observes_every_job() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    assert set(jobs["ci-gate"]["needs"]) == set(jobs) - {"ci-gate"}
    assert jobs["ci-gate"]["if"] == "always()"
    for name in policy.SIMULATION_JOBS:
        assert jobs[name]["if"] == "needs.ci-scope.outputs.simulation == 'true'"
    assert jobs["test"]["if"] == "needs.ci-scope.outputs.full == 'true'"


def test_runner_context_is_step_scoped_and_dbt_stays_isolated() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for job in workflow["jobs"].values():
        assert "runner." not in json.dumps(job.get("env", {}))
    validation = next(
        step
        for step in workflow["jobs"]["validate-models"]["steps"]
        if step.get("name") == "Validate dbt project"
    )
    assert validation["env"]["DATABASE_PATH"] == (
        "${{ runner.temp }}/planalign_ci_model_validation.duckdb"
    )


def test_renamed_backend_file_cannot_hide_in_docs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=tmp_path).decode().strip()

    git("init", "-q")
    git("config", "user.email", "ci@example.invalid")
    git("config", "user.name", "CI Test")
    (tmp_path / "engine.py").write_text("value = 1\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "docs").mkdir()
    git("mv", "engine.py", "docs/example.md")
    git("commit", "-qm", "rename")
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"sha": base},
                    "head": {"sha": git("rev-parse", "HEAD")},
                    "labels": [],
                }
            }
        )
    )
    output = tmp_path / "output"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    policy.select()
    assert output.read_text() == "full=false\nsimulation=true\n"


def test_gate_rejects_missing_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy.sys, "argv", ["ci_policy.py", "gate"])
    monkeypatch.setenv("CI_NEEDS", json.dumps(results()))
    with pytest.raises(SystemExit, match="Missing or invalid"):
        policy.main()
