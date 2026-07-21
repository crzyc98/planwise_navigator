"""Fail-loud initialization contract tests."""

import logging
from types import SimpleNamespace

import pytest

from planalign_orchestrator.construction.builder import execute_initialization
from planalign_orchestrator.construction.spec import InitializationPolicy
from planalign_orchestrator.exceptions import InitializationError
from planalign_orchestrator.pipeline.hooks import Hook, HookManager, HookType


class _Initializer:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def ensure_initialized(self):
        self.calls += 1
        return self.result


def test_none_policy_does_not_run_initializer():
    initializer = _Initializer(SimpleNamespace(success=True))

    execute_initialization(InitializationPolicy.NONE, initializer)

    assert initializer.calls == 0


def test_self_healing_failure_propagates_with_attributable_context():
    initializer = _Initializer(
        SimpleNamespace(
            success=False,
            error="foundation failed",
            missing_tables_found=["int_baseline_workforce"],
        )
    )

    with pytest.raises(InitializationError) as captured:
        execute_initialization(InitializationPolicy.SELF_HEALING, initializer)

    error = captured.value
    assert error.context.correlation_id
    assert error.context.metadata["failed_step"] == "pre_simulation"
    assert "foundation failed" in str(error)
    assert error.resolution_hints


def test_optional_hook_failure_remains_isolated(caplog):
    manager = HookManager()
    manager.register_hook(
        Hook(
            hook_type=HookType.PRE_SIMULATION,
            callback=lambda _context: (_ for _ in ()).throw(RuntimeError("optional")),
            name="optional_hook",
        )
    )

    with caplog.at_level(logging.ERROR):
        manager.execute_hooks(HookType.PRE_SIMULATION, {})

    assert "optional_hook" in caplog.text
