from pathlib import Path

import pytest

from navigator_orchestrator.dbt_runner import (
    DbtRunner,
    DbtResult,
    classify_dbt_error,
    DbtCompilationError,
    DbtExecutionError,
    DbtDataQualityError,
    retry_with_backoff,
)


def test_dbt_runner_successful_command_execution(tmp_path: Path):
    # Use python executable to simulate a command
    runner = DbtRunner(working_dir=tmp_path, executable="python")
    result = runner.execute_command(["-c", "print('hello')"], stream_output=False)
    assert isinstance(result, DbtResult)
    assert result.success is True
    assert "hello" in result.stdout


def test_dbt_runner_streaming_output_capture(tmp_path: Path):
    runner = DbtRunner(working_dir=tmp_path, executable="python")
    lines = []
    code = (
        "import time\n"
        "[print(i) or time.sleep(0.01) for i in range(3)]\n"
    )
    result = runner.execute_command(["-u", "-c", code], stream_output=True, on_line=lines.append)
    assert result.success is True
    assert lines == ["0", "1", "2"]


def test_retry_logic_transient_failures():
    calls = {"n": 0}

    def unstable():
        calls["n"] += 1
        if calls["n"] < 2:
            raise DbtExecutionError("transient")
        return DbtResult(True, "", "", 0.0, 0, ["dbt"])

    res = retry_with_backoff(unstable, max_attempts=3, base_delay=0.01)
    assert res.success is True
    assert calls["n"] == 2


def test_error_classification_compilation_vs_execution():
    assert isinstance(classify_dbt_error("", "Compilation Error in model x", 1), DbtCompilationError)
    assert isinstance(classify_dbt_error("", "Database Error: failed", 1), DbtExecutionError)
    assert isinstance(classify_dbt_error("some test failed", "", 1), DbtDataQualityError)


def test_command_templating_variable_injection(tmp_path: Path):
    runner = DbtRunner(working_dir=tmp_path, executable="dbt")
    # Build private method to inspect command
    cmd = runner._build_command(["run"], simulation_year=2026, dbt_vars={"cola_rate": 0.01})
    # Should include --vars JSON with both keys
    assert "--vars" in cmd
    idx = cmd.index("--vars")
    payload = cmd[idx + 1]
    assert "simulation_year" in payload and "cola_rate" in payload


def test_parallel_model_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    runner = DbtRunner(working_dir=tmp_path)

    def fake_run_model(model_name: str, **kwargs):
        return DbtResult(True, model_name, "", 0.0, 0, ["dbt", "run", model_name])

    monkeypatch.setattr(runner, "run_model", fake_run_model)
    models = ["m1", "m2", "m3"]
    results = runner.run_models(models, parallel=True)
    assert [r.stdout for r in results] == models
