"""Independent numeric expectations for the lead scorer."""

from pathlib import Path

import duckdb
import pytest

from campaign_a.score import annual, bars, cagr_err, range_flags, score_run

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


def test_cagr_err_uses_first_and_last_active_average():
    rows = [{"active_avg_comp": 100.0}] + [{}] * 3 + [{"active_avg_comp": 121.0}]
    assert cagr_err(rows, 4.0) == pytest.approx(abs(100 * (1.21**0.25 - 1) - 4))


def test_bars_mark_stress_cells_and_require_clean_runs():
    result = {
        "score": 0.4,
        "cagr_err": 0.1,
        "hc_err": 0.0,
        "cal_gap": 0.0,
        "failures": [],
    }
    assert bars({"comp_target_pct": 4}, result) == {
        "stress": False,
        "pass_per_year": True,
        "pass_cagr": True,
    }
    assert bars({"comp_target_pct": 1}, result)["stress"]
    flagged = dict(result, failures=["hire_pay_ratio_2030_5"])
    assert not any(
        bars({"comp_target_pct": 4}, flagged)[k] for k in ("pass_per_year", "pass_cagr")
    )
    missing = dict(result, score=None)
    assert not bars({"comp_target_pct": 4}, missing)["pass_cagr"]
