"""Regression test: orchestrator resource cleanup calls only real methods.

A test run surfaced 'ResourceManager' object has no attribute 'cleanup' and
'ParallelExecutionEngine' object has no attribute 'shutdown' at simulation
end — _cleanup_resources was calling methods that don't exist, and the
swallowed AttributeErrors showed up as error milestones in the Studio
activity feed (feature 094).
"""

import logging
from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator
from planalign_orchestrator.resources.manager import ResourceManager

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def _bare_orchestrator() -> PipelineOrchestrator:
    """Orchestrator instance without running __init__ (cleanup-only surface)."""
    return object.__new__(PipelineOrchestrator)


def test_cleanup_uses_only_real_resource_manager_methods(caplog):
    orch = _bare_orchestrator()
    orch.db_manager = MagicMock()
    orch.parallel_execution_engine = MagicMock(spec=[])  # no methods at all
    # spec=ResourceManager: calling a nonexistent method raises AttributeError
    orch.resource_manager = MagicMock(spec=ResourceManager)
    orch.resource_manager.get_resource_status.return_value = {
        "memory": {"usage_mb": 512.0},
        "cpu": {"current_percent": 10.0},
    }

    with caplog.at_level(logging.WARNING):
        orch._cleanup_resources()

    orch.resource_manager.stop_monitoring.assert_called_once()
    orch.db_manager.close_all.assert_called_once()
    cleanup_errors = [
        r for r in caplog.records if "Error during" in r.getMessage()
    ]
    assert cleanup_errors == []


def test_cleanup_survives_missing_components(caplog):
    orch = _bare_orchestrator()
    # No attributes set at all — hasattr guards must handle this
    with caplog.at_level(logging.WARNING):
        orch._cleanup_resources()
    assert [r for r in caplog.records if "Error during" in r.getMessage()] == []
