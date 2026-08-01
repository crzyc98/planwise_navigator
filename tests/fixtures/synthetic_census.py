"""Generate census snapshots from *known* rates, so a fit can be graded.

The round-trip test for issue #458 needs ground truth: a population evolved
with rates the test picked, written out as annual census files, so
``planalign fit`` can be asked to recover them. Everything here is
deterministic given a seed — no reliance on the simulator, which is the point
(the fitter must be gradeable independently of the thing it configures).
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Optional, Sequence

CENSUS_COLUMNS = (
    "employee_id",
    "employee_birth_date",
    "employee_hire_date",
    "employee_termination_date",
    "employee_gross_compensation",
    "active",
    "level_id",
    "employee_deferral_rate",
    "employee_enrollment_date",
)

# Midpoint compensation per level, loosely matching config_job_levels.csv.
LEVEL_COMPENSATION = {
    1: 68_000.0,
    2: 100_000.0,
    3: 140_000.0,
    4: 220_000.0,
    5: 350_000.0,
}
MAX_LEVEL = 5


@dataclass(frozen=True)
class TruthRates:
    """The rates a synthetic population is evolved with."""

    termination: float = 0.10
    new_hire_termination: float = 0.22
    promotion: float = 0.06
    merit: float = 0.04
    cola: float = 0.015
    promotion_raise: float = 0.18
    # Within-component dispersion of the annual raise. Without these a
    # population is two point masses (every ordinary raise exactly
    # `merit + cola`, every promotion raise exactly `promotion_raise`), which
    # no real census resembles and which makes separating the two trivial.
    # Defaults keep the components distinguishable; widen `merit_sigma` or
    # shrink the gap to build a deliberately inseparable population.
    merit_sigma: float = 0.015
    promotion_sigma: float = 0.04
    enrollment: float = 0.20
    new_hire_enrollment: float = 0.35
    hire_rate: float = 0.14
    starting_deferral: float = 0.05
    escalation_adoption: float = 0.0
    escalation_increment: float = 0.01


@dataclass
class Employee:
    employee_id: str
    birth_date: date
    hire_date: date
    compensation: float
    level_id: int
    deferral_rate: float
    enrollment_date: Optional[date]
    termination_date: Optional[date] = None

    @property
    def active(self) -> bool:
        return self.termination_date is None

    def row(self) -> dict[str, object]:
        return {
            "employee_id": self.employee_id,
            "employee_birth_date": self.birth_date.isoformat(),
            "employee_hire_date": self.hire_date.isoformat(),
            "employee_termination_date": (
                self.termination_date.isoformat() if self.termination_date else ""
            ),
            "employee_gross_compensation": f"{self.compensation:.2f}",
            "active": "true" if self.active else "false",
            "level_id": self.level_id,
            "employee_deferral_rate": f"{self.deferral_rate:.5f}",
            "employee_enrollment_date": (
                self.enrollment_date.isoformat() if self.enrollment_date else ""
            ),
        }


@dataclass
class SyntheticHistory:
    """Snapshot files plus the rates they were generated from."""

    directory: Path
    years: list[int]
    truth: TruthRates
    paths: list[Path] = field(default_factory=list)


def _new_employee(
    rng: random.Random, employee_id: str, year: int, tenure: int, enrolled_share: float
) -> Employee:
    age = rng.randint(24, 62)
    level = rng.choices([1, 2, 3, 4, 5], weights=[45, 27, 16, 8, 4])[0]
    enrolled = rng.random() < enrolled_share
    return Employee(
        employee_id=employee_id,
        birth_date=date(year - age, rng.randint(1, 12), rng.randint(1, 28)),
        hire_date=date(year - tenure, rng.randint(1, 12), rng.randint(1, 28)),
        compensation=LEVEL_COMPENSATION[level] * rng.uniform(0.9, 1.1),
        level_id=level,
        deferral_rate=round(rng.uniform(0.03, 0.10), 4) if enrolled else 0.0,
        enrollment_date=date(year - tenure, 6, 1) if enrolled else None,
    )


def _draw_raise(rng: random.Random, truth: TruthRates, promoted: bool) -> float:
    """One employee's annual raise, drawn around its component's centre.

    Dispersion is lognormal so a raise cannot turn negative however wide the
    sigma, and so the distribution is right-skewed the way real raises are.
    Draws come from the caller's seeded ``rng``, keeping the fixture
    reproducible.
    """
    if promoted:
        centre, sigma = truth.promotion_raise, truth.promotion_sigma
    else:
        centre, sigma = truth.merit + truth.cola, truth.merit_sigma
    if sigma <= 0:
        return centre
    # Solve the lognormal parameters so the drawn growth factor has mean
    # (1 + centre) and standard deviation sigma, rather than sigma applying to
    # the log scale where it would not mean what the field name says.
    mean_factor = 1.0 + centre
    variance = sigma**2
    mu = math.log(mean_factor**2 / math.sqrt(mean_factor**2 + variance))
    log_sigma = math.sqrt(math.log(1.0 + variance / mean_factor**2))
    return rng.lognormvariate(mu, log_sigma) - 1.0


def _advance_year(
    population: Sequence[Employee],
    rng: random.Random,
    year: int,
    truth: TruthRates,
    next_index: int,
) -> tuple[list[Employee], int]:
    """One year of terminations, raises, promotions, enrollments, and hires."""
    survivors: list[Employee] = []
    leavers: list[Employee] = []

    for employee in population:
        if rng.random() < truth.termination:
            leavers.append(
                Employee(
                    **{
                        **employee.__dict__,
                        "termination_date": date(year, rng.randint(1, 12), 15),
                    }
                )
            )
            continue

        promoted = employee.level_id < MAX_LEVEL and rng.random() < truth.promotion
        raise_pct = _draw_raise(rng, truth, promoted)
        survivor = Employee(
            **{
                **employee.__dict__,
                "level_id": employee.level_id + (1 if promoted else 0),
                "compensation": employee.compensation * (1 + raise_pct),
            }
        )

        if survivor.enrollment_date is None:
            if rng.random() < truth.enrollment:
                survivor.enrollment_date = date(year, 6, 1)
                survivor.deferral_rate = truth.starting_deferral
        elif rng.random() < truth.escalation_adoption:
            survivor.deferral_rate = round(
                survivor.deferral_rate + truth.escalation_increment, 5
            )
        survivors.append(survivor)

    hires: list[Employee] = []
    for _ in range(round(len(population) * truth.hire_rate)):
        hire = _new_employee(
            rng, f"EMP{next_index:06d}", year, 0, truth.new_hire_enrollment
        )
        hire.hire_date = date(year, rng.randint(1, 10), rng.randint(1, 28))
        if hire.enrollment_date is not None:
            hire.enrollment_date = date(year, 11, 1)
            hire.deferral_rate = truth.starting_deferral
        if rng.random() < truth.new_hire_termination:
            hire.termination_date = date(year, 12, 1)
        hires.append(hire)
        next_index += 1

    return survivors + hires + leavers, next_index


def write_snapshot(path: Path, population: Iterable[Employee]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        # Explicit LF so a snapshot's hash does not depend on the platform.
        writer = csv.DictWriter(
            handle, fieldnames=list(CENSUS_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        for employee in population:
            writer.writerow(employee.row())


def generate_history(
    directory: Path,
    *,
    start_year: int = 2022,
    years: int = 3,
    headcount: int = 8_000,
    truth: Optional[TruthRates] = None,
    seed: int = 20260729,
) -> SyntheticHistory:
    """Write ``years`` annual census snapshots evolved with known rates."""
    truth = truth or TruthRates()
    rng = random.Random(seed)
    directory.mkdir(parents=True, exist_ok=True)

    population = [
        _new_employee(rng, f"EMP{index:06d}", start_year, rng.randint(0, 22), 0.55)
        for index in range(headcount)
    ]
    next_index = headcount

    paths = [directory / f"census_{start_year}.csv"]
    write_snapshot(paths[0], population)

    for offset in range(1, years):
        year = start_year + offset
        population = [e for e in population if e.active]
        population, next_index = _advance_year(population, rng, year, truth, next_index)
        path = directory / f"census_{year}.csv"
        write_snapshot(path, population)
        paths.append(path)

    return SyntheticHistory(
        directory=directory,
        years=list(range(start_year, start_year + years)),
        truth=truth,
        paths=paths,
    )
