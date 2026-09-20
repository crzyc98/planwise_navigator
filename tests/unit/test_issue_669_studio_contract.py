"""Source contract for the deferral-spread clipping warning."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


def test_warning_uses_highest_segment_rate_and_reports_clipping() -> None:
    root = Path(__file__).parents[2]
    source = (root / "planalign_studio/components/config/DCPlanSection.tsx").read_text(
        encoding="utf-8"
    )

    assert "Math.max(...rates)" in source
    assert "spreadCeiling > maxVoluntaryDeferral" in source
    assert "formData.dcVoluntaryDeferralBaseRates" in source
    assert "Rates above that" in source
    assert 'role="alert"' in source
