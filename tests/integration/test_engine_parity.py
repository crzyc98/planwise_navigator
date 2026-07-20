"""Fast standing parity guard for the compiled execution engine."""

from pathlib import Path

import pytest

from planalign_orchestrator.tools.parity import run_parity
from tests.fixtures.invariant_simulation import CENSUS_CSV, CONFIG_YAML

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_tiny_one_year_engine_parity(tmp_path: Path) -> None:
    report = run_parity(
        start_year=2025,
        end_year=2025,
        config_path=CONFIG_YAML,
        census_path=CENSUS_CSV,
        seed=42,
        workdir=tmp_path,
    )

    assert report.verdict == "IDENTICAL", report.to_json()
    assert report.unexpected_fallback_count == 0
    assert all(table.identical for table in report.tables)
