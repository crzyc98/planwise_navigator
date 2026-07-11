"""Regression coverage for configuration serialization at orchestrator startup."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.pipeline_orchestrator import PipelineOrchestrator
from tests.utils.json_validators import assert_no_decimals_in_structure


@pytest.mark.fast
def test_orchestrator_records_json_safe_configuration(
    config_with_decimal_fields, monkeypatch, tmp_path
) -> None:
    """The production observability boundary receives JSON-safe config data."""
    observability = MagicMock()
    observability.get_run_id.return_value = "test-run"
    module = "planalign_orchestrator.pipeline_orchestrator"

    monkeypatch.setattr(
        f"{module}.ObservabilityManager", lambda **_kwargs: observability
    )
    monkeypatch.setattr(f"{module}.setup_memory_manager", MagicMock())
    monkeypatch.setattr(
        f"{module}.setup_parallelization",
        MagicMock(return_value=(None, None, None, None, False)),
    )
    monkeypatch.setattr(f"{module}.setup_hazard_cache", MagicMock())
    monkeypatch.setattr(f"{module}.setup_performance_monitor", MagicMock())

    PipelineOrchestrator(
        config_with_decimal_fields,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        reports_dir=tmp_path,
    )

    recorded_config = observability.set_configuration.call_args.args[0]
    assert_no_decimals_in_structure(recorded_config, "observability configuration")
    json.dumps(recorded_config)
