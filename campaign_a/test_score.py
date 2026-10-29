"""Independent numeric expectations for the lead scorer."""

from pathlib import Path

import duckdb
import pytest

from campaign_a.score import annual, range_flags, score_run

pytestmark = pytest.mark.fast


def test_annual_scores_all_population_and_retains_active_diagnostic(tmp_path: Path):
    database = tmp_path / "score.duckdb"
    with duckdb.connect(str(database)) as conn:
        conn.execute(
            "CREATE TABLE fct_workforce_snapshot(employee_id VARCHAR, simulation_year INTEGER, prorated_annual_compensation DOUBLE, employment_status VARCHAR)"
        )
        for offset in range(5):
            conn.executemany(
                "INSERT INTO fct_workforce_snapshot VALUES (?,?,?,?)",
                [
                    ("a", 2026 + offset, 100 * 1.04**offset, "active"),
                    ("b", 2026 + offset, 20 * 1.02**offset, "terminated"),
                ],
            )
    rows = annual(str(database))
    assert rows[0]["avg_comp"] == 60
    assert rows[1]["comp_growth"] == pytest.approx(3.6666666666666665)
    assert rows[1]["active_comp_growth"] == pytest.approx(4)
    assert rows[1]["hc_growth"] == 0


def test_failed_run_has_no_numeric_score():
    result = score_run({}, {"status": "failed"}, "unused")
    assert result["score"] is None
    assert result["cal_gap"] is None
    assert result["failures"]


def test_duplicate_snapshots_rejected(tmp_path: Path):
    database = tmp_path / "duplicate.duckdb"
    with duckdb.connect(str(database)) as conn:
        conn.execute(
            "CREATE TABLE fct_workforce_snapshot AS SELECT 'a' employee_id, 2026 simulation_year FROM range(2)"
        )
    with pytest.raises(ValueError, match="duplicate"):
        annual(str(database))


def test_invalid_ranges_and_clamp_are_failures():
    flags = range_flags(
        {
            "ranges": [
                {"level": 1, "min_compensation": 10, "max_compensation": 20},
                {"level": 2, "min_compensation": 5, "max_compensation": 5},
            ],
            "scale_clamped": True,
            "outcome": {"best_scale": 0.5},
        }
    )
    assert "scale_clamped" in flags
    assert "invalid_range_level_2" in flags
    assert "nonmonotone_range_level_2" in flags
