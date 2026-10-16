"""Source contract for the Census Analysis metric surface."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


def test_census_analysis_surfaces_total_compensation() -> None:
    root = Path(__file__).parents[2]
    source = (root / "planalign_studio/components/CensusAnalysis.tsx").read_text()

    assert 'title="Total Compensation"' in source
    assert "result.overall.total_eligible_compensation" in source
    assert "row.total_eligible_compensation" in source
    assert "eligible employees" in source


def test_census_analysis_explains_unavailable_hce_and_inferred_date() -> None:
    root = Path(__file__).parents[2]
    source = (root / "planalign_studio/components/CensusAnalysis.tsx").read_text()

    assert "result.hce_compensation_threshold == null" in source
    assert "result.overall.hce_count == null" in source
    assert "HCE classification unavailable" in source
    assert "result.as_of_date_source === 'inferred'" in source
    assert "anchored to December 31" in source
