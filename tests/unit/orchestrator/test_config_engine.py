"""Feature 119: optimization.execution_engine config validation."""

import pytest
from pydantic import ValidationError

from planalign_orchestrator.config.performance import OptimizationSettings

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator, pytest.mark.config]


def test_default_engine_is_dbt():
    assert OptimizationSettings().execution_engine == "dbt"


def test_compiled_engine_accepted():
    assert (
        OptimizationSettings(execution_engine="compiled").execution_engine == "compiled"
    )


def test_invalid_engine_rejected_at_load():
    with pytest.raises(ValidationError):
        OptimizationSettings(execution_engine="warp-drive")
