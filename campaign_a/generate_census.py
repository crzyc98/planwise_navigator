#!/usr/bin/env python3
"""Generate deterministic synthetic census parquet files for campaign A."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

SEED = 42
ROWS = 5000
OUTPUT_DIR = Path("/tmp/nhcal/census_v2")
MANIFEST_PATH = Path("campaign_a/census_manifest.json")


def make_dataset(shape: str) -> pd.DataFrame:
    rng = random.Random(SEED)
    records = []
    for index in range(ROWS):
        weights = {
            "balanced": [35, 30, 20, 10, 5],
            "young": [65, 20, 9, 4, 2],
            "older": [10, 15, 30, 30, 15],
        }[shape]
        level = rng.choices(range(1, 6), weights=weights)[0]
        age_mean = {"balanced": 40, "young": 28, "older": 54}[shape]
        age = max(22, min(65, int(rng.gauss(age_mean + level, 5))))
        bands = [
            (56000, 80000),
            (81000, 120000),
            (121000, 160000),
            (161000, 274000),
            (300000, 450000),
        ]
        low, high = bands[level - 1]
        if shape == "older":
            high = low + (high - low) * 0.25
        gross = round(rng.uniform(low, high), 2)
        birth_year = 2025 - age
        birth = date(birth_year, rng.randint(1, 12), 1) + timedelta(
            days=rng.randint(0, 27)
        )
        if index < ROWS // 5:
            hire = date(2025, 1, 1) + timedelta(days=rng.randint(0, 364))
        else:
            hire = date(2024 - rng.randint(0, 30), 1, 1) + timedelta(
                days=rng.randint(0, 364)
            )
        hire = max(hire, date(birth.year + 18, birth.month, birth.day))
        gross = round(gross * min(365, (date(2025, 12, 31) - hire).days + 1) / 365, 2)
        contribution = round(gross * 0.06, 2)
        records.append(
            dict(
                employee_job_level=level,
                employee_id=f"SYN-{shape.upper()}-{index+1:05d}",
                employee_ssn=f"999-{index // 10000:02d}-{index+1:04d}",
                employee_birth_date=birth,
                employee_hire_date=hire,
                employee_termination_date=None,
                employee_gross_compensation=gross,
                active=True,
                employee_capped_compensation=min(gross, 350000),
                employee_deferral_rate=0.06,
                employee_contribution=contribution,
                pre_tax_contribution=contribution,
                roth_contribution=0.0,
                after_tax_contribution=0.0,
                employer_core_contribution=0.0,
                employer_match_contribution=0.0,
                eligibility_entry_date=hire,
                scheduled_hours_per_week=40,
                auto_escalation_opt_out=False,
                eligibility_override=False,
            )
        )
    df = pd.DataFrame(records)
    for col in (
        "employee_birth_date",
        "employee_hire_date",
        "employee_termination_date",
        "eligibility_entry_date",
    ):
        df[col] = pd.to_datetime(df[col])
    return df


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for shape in ("balanced", "young", "older"):
        path = OUTPUT_DIR / f"{shape}.parquet"
        frame = make_dataset(shape)
        with duckdb.connect() as conn:
            conn.register("synthetic_census", frame)
            conn.execute(
                "COPY (SELECT * REPLACE (CAST(employee_birth_date AS DATE) AS employee_birth_date, CAST(employee_hire_date AS DATE) AS employee_hire_date, CAST(employee_termination_date AS DATE) AS employee_termination_date, CAST(eligibility_entry_date AS DATE) AS eligibility_entry_date) FROM synthetic_census) TO ? (FORMAT PARQUET)",
                [str(path)],
            )
        manifest[shape] = {
            "path": str(path),
            "count": ROWS,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
