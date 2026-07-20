"""Feature 119 paired-engine performance artifact coverage."""

import pytest

from scripts.perf_profile.build_report import _paired_engine_lines
from scripts.perf_profile.profile_config import (
    CensusSize,
    EnvNote,
    TimingSample,
)
from scripts.perf_profile import run_matrix

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def _sample(engine: str, wall_s: float, rss_mb: float) -> TimingSample:
    return TimingSample(
        sample_id=f"campaign-{engine}-tiny-1",
        campaign_id="campaign",
        engine=engine,
        census_size=CensusSize.TINY,
        census_rows=150,
        census_parquet="tiny.parquet",
        census_fingerprint="c" * 64,
        config_fingerprint="f" * 64,
        horizon=(2025, 2027),
        repetition=1,
        warm=True,
        db_path=f"{engine}.duckdb",
        total_wall_s=wall_s,
        env=EnvNote(
            machine="test",
            os="test",
            python="3.12",
            dbt_core="1.8.8",
            dbt_duckdb="1.8.1",
            duckdb="1.0.0",
            git_sha="abc",
        ),
        peak_rss_mb=rss_mb,
    )


def test_paired_report_includes_speedup_rss_and_fallbacks() -> None:
    lines = _paired_engine_lines(
        [_sample("dbt", 20.0, 100.0), _sample("compiled", 10.0, 80.0)]
    )
    report = "\n".join(lines)
    assert "2.00x" in report
    assert "80.0 MiB" in report
    assert "Delegated / unexpected" in report


def test_memory_size_resolves_acceptance_census(monkeypatch, tmp_path) -> None:
    census = tmp_path / "census_100k.parquet"
    census.touch()
    monkeypatch.setattr(run_matrix, "MEMORY_CENSUS_PARQUET", census)
    assert run_matrix.resolve_census(CensusSize.MEMORY) == census
