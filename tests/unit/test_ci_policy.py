"""Prevent risk selection and skipped jobs from silently weakening CI."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ci_policy", ROOT / "scripts/ci_policy.py"
)
assert SPEC is not None and SPEC.loader is not None
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


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
    assert set(jobs["ci-gate"]["needs"]) == set(jobs) - {"ci-gate", "nightly-alert"}
    assert jobs["ci-gate"]["if"] == "always()"
    for name in policy.SIMULATION_JOBS:
        assert jobs[name]["if"] == "needs.ci-scope.outputs.simulation == 'true'"
    assert jobs["test"]["if"] == "needs.ci-scope.outputs.full == 'true'"


def test_a_failed_nightly_run_opens_an_issue() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    alert = workflow["jobs"]["nightly-alert"]
    assert alert["needs"] == ["ci-gate"]
    assert "github.event_name == 'schedule'" in alert["if"]
    assert "needs.ci-gate.result == 'failure'" in alert["if"]
    assert alert["permissions"] == {"issues": "write"}


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


def test_plain_pull_requests_skip_simulations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"labels": []}}))
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    policy.select()
    assert output.read_text() == "full=false\nsimulation=false\n"


def test_gate_rejects_missing_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy.sys, "argv", ["ci_policy.py", "gate"])
    monkeypatch.setenv("CI_NEEDS", json.dumps(results()))
    with pytest.raises(SystemExit, match="Missing or invalid"):
        policy.main()
