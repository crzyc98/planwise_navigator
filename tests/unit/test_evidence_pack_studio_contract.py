"""Source contract for the completed-result Evidence Pack Studio surface."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


def test_completed_run_surface_has_controls_states_citations_and_export() -> None:
    root = Path(__file__).parents[2]
    detail = (root / "planalign_studio/components/SimulationDetail.tsx").read_text()
    panel = (root / "planalign_studio/components/EvidencePackPanel.tsx").read_text()
    api = (root / "planalign_studio/services/api.ts").read_text()

    assert "run.status === 'completed'" in detail
    assert "EvidencePackPanel" in detail
    for text in (
        "Evidence metric",
        "Base year",
        "Target year",
        "Computing evidence pack…",
        "Retry",
        "Driver",
        "Population",
        "Residual",
        "Q1.",
        "Export Evidence Pack",
    ):
        assert text in panel
    assert "baseYear < targetYear" in panel
    assert "text/markdown;charset=utf-8" in api
    assert "new Blob([envelope.text_export]" in api
    assert "revokeObjectURL" in api
    assert "window.open" not in panel
