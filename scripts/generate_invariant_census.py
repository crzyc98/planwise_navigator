#!/usr/bin/env python3
"""Generate the deterministic reference census for Feature 113."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

SEED = 113_435_436
EMPLOYEE_COUNT = 150
AS_OF_YEAR = 2025
AGE_CHOICES = (22, 29, 39, 49, 59, 68)
TENURE_BY_AGE = {
    22: (1,),
    29: (1, 3, 7),
    39: (1, 3, 7, 14),
    49: (1, 3, 7, 14, 24),
    59: (1, 3, 7, 14, 24),
    68: (1, 3, 7, 14, 24),
}
COMP_RANGES = (
    (56_000, 80_000),
    (81_000, 120_000),
    (121_000, 160_000),
    (161_000, 274_000),
    (300_000, 480_000),
)
FIELDS = (
    "employee_id",
    "employee_ssn",
    "employee_birth_date",
    "employee_hire_date",
    "employee_termination_date",
    "employee_gross_compensation",
    "employee_capped_compensation",
    "active",
    "employee_deferral_rate",
    "employee_contribution",
    "pre_tax_contribution",
    "roth_contribution",
    "after_tax_contribution",
    "employer_core_contribution",
    "employer_match_contribution",
    "eligibility_entry_date",
    "scheduled_hours_per_week",
    "auto_escalation_opt_out",
    "eligibility_override",
)


def _money(value: float) -> str:
    return f"{value:.2f}"


def _employee_row(index: int, rng: np.random.Generator) -> dict[str, Any]:
    age = AGE_CHOICES[index % len(AGE_CHOICES)]
    tenure_options = TENURE_BY_AGE[age]
    tenure = tenure_options[(index // len(AGE_CHOICES)) % len(tenure_options)]
    level = index % len(COMP_RANGES)
    low, high = COMP_RANGES[level]
    compensation = float(rng.integers(low, high + 1) // 100 * 100)
    enrolled = index < 60
    deferral = (0.04, 0.05, 0.06)[index % 3] if enrolled else 0.0
    contribution = compensation * deferral
    birth_date = date(AS_OF_YEAR - age, (index % 12) + 1, (index % 27) + 1)
    hire_date = date(AS_OF_YEAR - tenure, ((index + 4) % 12) + 1, (index % 27) + 1)
    terminated = index == EMPLOYEE_COUNT - 1
    return {
        "employee_id": f"INV_EMP_{index + 1:04d}",
        "employee_ssn": f"999-{70 + index // 100:02d}-{index:04d}",
        "employee_birth_date": birth_date.isoformat(),
        "employee_hire_date": hire_date.isoformat(),
        "employee_termination_date": "2023-06-30" if terminated else "",
        "employee_gross_compensation": _money(compensation),
        "employee_capped_compensation": _money(min(compensation, 350_000)),
        "active": str(not terminated).lower(),
        "employee_deferral_rate": f"{deferral:.5f}",
        "employee_contribution": _money(contribution),
        "pre_tax_contribution": _money(contribution),
        "roth_contribution": "0.00",
        "after_tax_contribution": "0.00",
        "employer_core_contribution": _money(compensation * 0.03 if enrolled else 0),
        "employer_match_contribution": _money(min(contribution, compensation * 0.04)),
        "eligibility_entry_date": hire_date.isoformat(),
        "scheduled_hours_per_week": "20.00" if index in {7, 31, 83, 127} else "40.00",
        "auto_escalation_opt_out": str(index in {2, 11, 29}).lower(),
        "eligibility_override": "",
    }


def generate(output: Path) -> None:
    """Write a stable, reviewable CSV fixture."""
    rng = np.random.default_rng(SEED)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(_employee_row(index, rng) for index in range(EMPLOYEE_COUNT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/invariant_census.csv"),
    )
    generate(parser.parse_args().output)


if __name__ == "__main__":
    main()
