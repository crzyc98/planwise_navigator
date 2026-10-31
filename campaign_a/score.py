"""Lead scorer for the frozen Campaign A oracle; reads databases only."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import duckdb
import yaml

ROOT = Path(__file__).resolve().parent
Json = dict[str, Any]


# Amendment 2026-10-30 (see ORACLE.md), fixed before any holdout run.
PER_YEAR_BAR = 0.50
CAGR_BAR = 0.25
HC_BAR = 0.10
CAL_GAP_BAR = 0.10
STRESS_COMP_TARGETS = (1,)
CENSUS_YEAR = 2026


def annual(database: str) -> list[Json]:
    with duckdb.connect(database, read_only=True) as conn:
        duplicate = conn.execute(
            "SELECT count(*) FROM (SELECT employee_id, simulation_year FROM fct_workforce_snapshot GROUP BY 1,2 HAVING count(*) > 1)"
        ).fetchone()[0]
        if duplicate:
            raise ValueError("duplicate employee/year snapshots")
        rows = conn.execute(
            "SELECT simulation_year, count(DISTINCT employee_id), avg(prorated_annual_compensation), count(DISTINCT employee_id) FILTER (WHERE lower(employment_status)='active'), avg(prorated_annual_compensation) FILTER (WHERE lower(employment_status)='active') FROM fct_workforce_snapshot WHERE simulation_year BETWEEN 2026 AND 2030 GROUP BY 1 ORDER BY 1"
        ).fetchall()
    if [row[0] for row in rows] != list(range(2026, 2031)):
        raise ValueError("missing snapshot years")
    result = []
    for index, row in enumerate(rows):
        if any(
            value is None or not math.isfinite(value) or value <= 0 for value in row[1:]
        ):
            raise ValueError("invalid annual compensation or headcount")
        entry = dict(
            zip(
                [
                    "year",
                    "headcount",
                    "avg_comp",
                    "active_headcount",
                    "active_avg_comp",
                ],
                row,
            )
        )
        for column, name in [
            (1, "hc_growth"),
            (2, "comp_growth"),
            (3, "active_hc_growth"),
            (4, "active_comp_growth"),
        ]:
            entry[name] = (
                100 * (row[column] / rows[index - 1][column] - 1) if index else None
            )
        result.append(entry)
    return result


def range_flags(calibration: Json) -> list[str]:
    flags = []
    ranges = sorted(calibration.get("ranges") or [], key=lambda row: row["level"])
    if not ranges:
        return ["missing_ranges"]
    previous = (0.0, 0.0)
    for row in ranges:
        lo, hi = row["min_compensation"], row["max_compensation"]
        if not all(math.isfinite(x) and x >= 0 for x in (lo, hi)) or lo >= hi:
            flags.append(f"invalid_range_level_{row['level']}")
        if lo < previous[0] or hi < previous[1]:
            flags.append(f"nonmonotone_range_level_{row['level']}")
        previous = (lo, hi)
    if calibration.get("scale_clamped"):
        flags.append("scale_clamped")
    outcome = calibration.get("outcome", {})
    if outcome.get("best_scale") is None:
        flags.append("missing_scale_or_fallback")
    return flags


def hire_flags(database: str, census: str, growth: float = 0.0) -> list[str]:
    with duckdb.connect(database, read_only=True) as conn:
        rows = conn.execute(
            "SELECT simulation_year,level_id,avg(compensation_amount),min(compensation_amount) FROM fct_yearly_events WHERE upper(event_type)='HIRE' GROUP BY 1,2"
        ).fetchall()
        means = dict(
            conn.execute(
                "SELECT employee_job_level,avg(employee_gross_compensation) FROM read_parquet(?) GROUP BY 1",
                [census],
            ).fetchall()
        )
        # Amendment 2026-10-31b: a level only misses hires that were planned for it.
        planned = conn.execute(
            "SELECT simulation_year,level_id FROM int_workforce_needs_by_level WHERE hires_needed > 0"
        ).fetchall()
    flags = []
    observed = {(year, level) for year, level, _, _ in rows}
    for year, level in sorted(set(planned) - observed):
        flags.append(f"missing_hires_{year}_{level}")
    for year, level, average, minimum in rows:
        if average is None or not math.isfinite(average) or minimum < 0:
            flags.append(f"invalid_hire_pay_{year}_{level}")
        elif (
            level not in means
            or not 0.6 <= average / indexed(means[level], year, growth) <= 1.3
        ):
            flags.append(f"hire_pay_ratio_{year}_{level}")
    return flags


def indexed(census_mean: float, year: int, growth: float) -> float:
    """Amendment 2026-10-31: the census yardstick rises with configured starting-pay growth."""
    return census_mean * (1 + growth) ** (year - CENSUS_YEAR)


def salary_growth(config_path: str) -> float:
    config = yaml.safe_load(Path(config_path).read_text()) or {}
    return float((config.get("new_hire") or {}).get("salary_growth_rate", 0.0))


def cagr_err(rows: list[Json], target: float) -> float:
    """Amendment 2026-10-30: compound Active comp growth error over the horizon."""
    first, last = rows[0]["active_avg_comp"], rows[-1]["active_avg_comp"]
    growth = 100 * ((last / first) ** (1 / (len(rows) - 1)) - 1)
    return abs(growth - target)


def bars(cell: Json, result: Json) -> Json:
    """Amendment 2026-10-30 acceptance bars; 1% comp targets are stress cells."""
    clean = (
        result["score"] is not None
        and result["hc_err"] <= HC_BAR
        and result["cal_gap"] <= CAL_GAP_BAR
        and not result["failures"]
    )
    return {
        "stress": cell["comp_target_pct"] in STRESS_COMP_TARGETS,
        "pass_per_year": clean and result["score"] <= PER_YEAR_BAR,
        "pass_cagr": clean and result["cagr_err"] <= CAGR_BAR,
    }


def score_run(cell: Json, run: Json, census: str) -> Json:
    if run.get("status") != "completed":
        return {
            "status": run.get("status", "not_run"),
            "score": None,
            "hc_err": None,
            "cal_gap": None,
            "failures": ["incomplete_applied_pipeline"],
        }
    try:
        rows = annual(run["applied"]["database"])
        predictions = {
            row["simulation_year"]: row["yoy_growth_pct"]
            for row in run["calibration"]["annual_predictions"]
        }
        for row in rows[1:]:
            prediction = predictions[row["year"]]
            if prediction is None or not math.isfinite(prediction):
                raise ValueError("missing or nonfinite calibration prediction")
            # Amendment 2026-10-29: score Studio's Active view (see ORACLE.md).
            row["comp_err"] = abs(row["active_comp_growth"] - cell["comp_target_pct"])
            row["hc_err"] = abs(row["active_hc_growth"] - cell["hc_target_pct"])
            row["cal_gap"] = abs(prediction - row["active_comp_growth"])
        flags = range_flags(run["calibration"]) + hire_flags(
            run["applied"]["database"],
            census,
            salary_growth(run["applied"]["config_path"]),
        )
        return {
            "status": "scored",
            "score": max(row["comp_err"] for row in rows[1:]),
            "cagr_err": cagr_err(rows, cell["comp_target_pct"]),
            "hc_err": max(row["hc_err"] for row in rows[1:]),
            "cal_gap": max(row["cal_gap"] for row in rows[1:]),
            "failures": flags,
            "annual": rows,
        }
    except (
        duckdb.Error,
        OSError,
        yaml.YAMLError,
        KeyError,
        ValueError,
        TypeError,
        ZeroDivisionError,
    ) as exc:
        return {
            "status": "unscorable",
            "score": None,
            "hc_err": None,
            "cal_gap": None,
            "failures": [f"{type(exc).__name__}: {exc}"],
        }


def main(
    stage: str = "baseline", split: str | None = None, seed: int | None = None
) -> None:
    cells = json.loads((ROOT / "matrix.json").read_text())
    if split is not None:
        cells = [cell for cell in cells if cell["split"] == split]
    census = json.loads((ROOT / "census_manifest.json").read_text())
    scores = []
    for cell in cells:
        record = json.loads((ROOT / "cells" / f"{cell['id']}.json").read_text())
        for run_seed in [s for s in cell["seeds"] if seed in (None, s)]:
            run = record.get("runs", {}).get(stage, {}).get(str(run_seed), {})
            result = score_run(cell, run, census[cell["shape"]]["path"])
            outcome = run.get("calibration", {}).get("outcome", {})
            scores.append(
                dict(
                    cell=cell["id"],
                    split=cell["split"],
                    seed=run_seed,
                    calibration_status=outcome.get("status"),
                    calibration_reason=outcome.get("reason"),
                    **result,
                    **bars(cell, result),
                )
            )
    suffix = ("_holdout" if split == "holdout" else "") + (
        f"_seed{seed}" if seed is not None else ""
    )
    (ROOT / f"{stage}{suffix}_scores.json").write_text(
        json.dumps(scores, indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "expected": len(scores),
                "scored": sum(row["score"] is not None for row in scores),
                "failed_or_missing": sum(row["score"] is None for row in scores),
                "standard_cells": sum(not row["stress"] for row in scores),
                "standard_pass_per_year": sum(
                    row["pass_per_year"] for row in scores if not row["stress"]
                ),
                "standard_pass_cagr": sum(
                    row["pass_cagr"] for row in scores if not row["stress"]
                ),
            }
        )
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="baseline")
    parser.add_argument("--split", choices=["dev", "holdout"])
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    main(args.stage, args.split, args.seed)
