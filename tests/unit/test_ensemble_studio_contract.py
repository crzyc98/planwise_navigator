"""Source contract for the ensemble visualization surface."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


def test_ensemble_panel_preserves_distribution_and_experimental_semantics() -> None:
    root = Path(__file__).parents[2]
    source = (
        root / "planalign_studio/components/EnsembleAnalysisPanel.tsx"
    ).read_text()

    for text in (
        "p10",
        "p50",
        "p90",
        "is_sufficient",
        "Threshold-exceedance risk",
        "[EXPERIMENTAL] Variance attribution",
        "not a ranked decomposition",
        "not included in client-facing exports",
        "anchor-averaged conditional variance shares",
    ):
        assert text in source


def test_ensemble_panel_does_not_render_insufficient_percentiles_as_values() -> None:
    root = Path(__file__).parents[2]
    source = (
        root / "planalign_studio/components/EnsembleAnalysisPanel.tsx"
    ).read_text()
    assert (
        "row.is_sufficient && row.p10 !== null && row.p50 !== null && row.p90 !== null"
        in source
    )
