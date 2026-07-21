"""The common dbt runner boundary records the executed work schedule."""

from planalign_orchestrator.construction import WorkSchedule
from planalign_orchestrator.dbt_runner import DbtResult, DbtRunner


def _success(command):
    return DbtResult(True, "", "", 0.0, 0, list(command))


def test_runner_captures_ordered_command_stage_year_and_kind(monkeypatch):
    schedule = WorkSchedule()
    runner = DbtRunner(executable="echo")
    runner.configure_work_schedule(schedule, runner_kind="dbt")
    monkeypatch.setattr(
        runner,
        "_execute_with_retry",
        lambda run_once, **_kwargs: run_once(),
    )
    monkeypatch.setattr(
        runner,
        "_execute_once",
        lambda command_args, **_kwargs: _success(command_args),
    )

    runner.set_schedule_context(stage="FOUNDATION", year=2025)
    runner.execute_command(["run", "--select", "tag:FOUNDATION"])
    runner.set_schedule_context(stage="VALIDATION", year=2025)
    runner.execute_command(["test", "--select", "tag:VALIDATION"])

    assert schedule.invocation_count == 2
    assert [step.seq for step in schedule.steps] == [1, 2]
    assert [step.command for step in schedule.steps] == [
        "run --select tag:FOUNDATION",
        "test --select tag:VALIDATION",
    ]
    assert [step.stage for step in schedule.steps] == ["FOUNDATION", "VALIDATION"]
    assert [step.year for step in schedule.steps] == [2025, 2025]
    assert {step.runner_kind for step in schedule.steps} == {"dbt"}
