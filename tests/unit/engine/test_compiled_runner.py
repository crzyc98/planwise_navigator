"""#470 T015: CompiledRunner state machine — typed-only delegation."""

import pytest

from planalign_orchestrator.dbt_runner import DbtResult
from planalign_orchestrator.engine.compiled_runner import CompiledRunner
from planalign_orchestrator.engine.preflight import KnownUnsupportedSemantics
from planalign_orchestrator.engine.transaction import TransactionExecutionError
from tests.fixtures.compiled_execution import FakeDbManager

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]

VARS = {"scenario_id": "default", "random_seed": 42}


@pytest.fixture()
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "planalign_orchestrator.engine.workspace.DEFAULT_ARTIFACT_ROOT",
        tmp_path / "ws",
    )
    r = CompiledRunner(
        working_dir=tmp_path, threads=1, db_manager=FakeDbManager(tmp_path / "r.duckdb")
    )
    return r


@pytest.fixture()
def spy(monkeypatch):
    calls = {"delegated": [], "direct": []}

    def fake_delegated(args, **kwargs):
        calls["delegated"].append(list(args))
        return DbtResult(
            success=True,
            stdout="",
            stderr="",
            execution_time=0.01,
            return_code=0,
            command=list(args),
        )

    monkeypatch.setattr(
        "planalign_orchestrator.engine.compiled_runner.invoke_dbt_delegated",
        fake_delegated,
    )
    return calls


def _patch_preflight(monkeypatch, runner, outcome):
    if isinstance(outcome, Exception):

        def fake(request):
            raise outcome

    else:

        def fake(request):
            return outcome

    monkeypatch.setattr(runner, "_preflight", fake)


@pytest.mark.parametrize(
    "args,expected_reason",
    [
        (["seed", "--full-refresh"], "command"),
        (["build", "--select", "dim_x"], "command"),
        (["run", "--select", "int_x", "--full-refresh"], "full_refresh"),
        (["run", "--select", "int_x", "--weird-flag"], "option"),
        (["run", "--select", "staging.*"], "option"),  # var-less (auto-init)
    ],
)
def test_expected_delegations_by_parse(runner, spy, args, expected_reason):
    year = 2025 if "--weird-flag" in args or "--full-refresh" in args else None
    dbt_vars = VARS if year else None
    result = runner.execute_command(args, simulation_year=year, dbt_vars=dbt_vars)
    assert result.success and spy["delegated"]
    (record,) = runner.record_log.records
    assert record.kind == "delegation"
    assert record.reason == expected_reason
    assert runner.record_log.fallback_count == 0


def test_preflight_unsupported_delegates_typed(runner, spy, monkeypatch):
    _patch_preflight(
        monkeypatch,
        runner,
        KnownUnsupportedSemantics("empty_selection", "no nodes"),
    )
    result = runner.execute_command(
        ["run", "--select", "nope"], simulation_year=2025, dbt_vars=VARS
    )
    assert result.success
    (record,) = runner.record_log.records
    assert (record.kind, record.reason) == ("delegation", "empty_selection")


def test_generic_direct_failure_never_delegates(runner, spy, monkeypatch):
    class FakePlan:
        nodes = ("model.pkg.a",)
        connection_hooks = ()
        operations = ()
        end_logs = ()
        target_database = runner.db_manager.db_path

    _patch_preflight(monkeypatch, runner, FakePlan())

    def boom(**kwargs):
        raise TransactionExecutionError(
            "kaput",
            node="model.pkg.a",
            phase="model",
            statement="SELECT 1",
            original=RuntimeError("kaput"),
            rollback_attempted=True,
            rollback_succeeded=True,
            operations_completed=0,
        )

    monkeypatch.setattr(
        "planalign_orchestrator.engine.transaction.execute_invocation_transaction",
        boom,
    )
    with pytest.raises(Exception) as excinfo:
        runner.execute_command(
            ["run", "--select", "a"], simulation_year=2025, dbt_vars=VARS
        )
    assert not spy["delegated"], "generic failures must not replay through dbt"
    assert runner.record_log.fallback_count == 0
    assert "rollback_succeeded=True" in str(excinfo.value)
    assert len(runner.execution_records) == 1
    assert runner.execution_records[0].outcome == "failed"
    assert runner.execution_records[0].rollback_succeeded is True


def test_delegation_failure_raises_classified(runner, monkeypatch):
    def failing(args, **kwargs):
        return DbtResult(
            success=False,
            stdout="",
            stderr="boom",
            execution_time=0.0,
            return_code=1,
            command=list(args),
        )

    monkeypatch.setattr(
        "planalign_orchestrator.engine.compiled_runner.invoke_dbt_delegated", failing
    )
    with pytest.raises(Exception):
        runner.execute_command(["seed"])
    (record,) = runner.record_log.records
    assert record.kind == "delegation"


def test_zero_node_plan_cannot_succeed():
    assert CompiledRunner.classify_direct_result(()) != "SUCCEEDED"
    assert CompiledRunner.classify_direct_result(("model.pkg.a",)) == "SUCCEEDED"


def test_unclassified_preflight_failure_is_recorded_not_delegated(
    runner, spy, monkeypatch
):
    _patch_preflight(monkeypatch, runner, RuntimeError("bundle hash mismatch"))
    with pytest.raises(RuntimeError, match="bundle hash mismatch"):
        runner.execute_command(
            ["run", "--select", "a"],
            description="FOUNDATION",
            simulation_year=2025,
            dbt_vars=VARS,
        )
    assert not spy["delegated"]
    (record,) = runner.execution_records
    assert record.outcome == "failed"
    assert record.stage == "FOUNDATION"
    assert record.error_context["type"] == "RuntimeError"
