"""Contract tests for construction signatures and schedules."""

from planalign_orchestrator.construction.signature import (
    ConstructionSignature,
    ScheduleStep,
    WorkSchedule,
)


def _signature(**overrides) -> ConstructionSignature:
    values = {
        "entry_point": "cli.simulate",
        "runner_kind": "dbt",
        "database_path": "/tmp/one.duckdb",
        "dbt_project_dir": None,
        "thread_count": 1,
        "initialization_policy": "none",
        "installed_hook_names": ("telemetry",),
        "execution_engine": "dbt",
    }
    values.update(overrides)
    return ConstructionSignature(**values)


def test_signature_hash_ignores_attribution_and_literal_database_path():
    first = _signature()
    second = _signature(
        entry_point="studio",
        database_path="/tmp/two.duckdb",
    )

    assert first.signature_hash == second.signature_hash


def test_signature_hash_normalizes_hook_order():
    first = _signature(installed_hook_names=("beta", "alpha"))
    second = _signature(installed_hook_names=("alpha", "beta"))

    assert first.signature_hash == second.signature_hash


def test_signature_hash_distinguishes_semantic_project_relationship():
    shared = _signature(dbt_project_dir=None)
    overlay = _signature(dbt_project_dir="/tmp/scenario/dbt")

    assert shared.signature_hash != overlay.signature_hash


def test_work_schedule_records_stable_execution_order():
    schedule = WorkSchedule()
    first = schedule.record(
        command="run --select tag:FOUNDATION",
        stage="FOUNDATION",
        year=2025,
        runner_kind="dbt",
    )
    second = schedule.record(
        command="run --select tag:EVENT_GENERATION",
        stage="EVENT_GENERATION",
        year=2025,
        runner_kind="dbt",
    )

    assert first == ScheduleStep(
        seq=1,
        command="run --select tag:FOUNDATION",
        stage="FOUNDATION",
        year=2025,
        runner_kind="dbt",
    )
    assert second.seq == 2
    assert schedule.invocation_count == 2
    assert schedule.steps == [first, second]
