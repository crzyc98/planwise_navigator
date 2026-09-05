"""Issue #652: upward-only deferral-rate spread.

The demographic table assigns every member of a cell the identical rate, so a
cell renders as a single spike. These tests verify the spread turns that into
a distribution of whole-percent elections at or above the table value.

Databases are built out of band; see test_new_hire_enrollment_rates.py for the
rationale and the environment-variable convention.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.dbt]

#: By design the floor holds 40% of a cell (weights 40/30/15/10/5 across
#: +0..+4). A single fixed threshold is the wrong test: at n=45 the binomial
#: standard deviation is 7.3 points, so a flat 45% bar leaves under one sigma
#: of headroom and fails on ordinary sampling noise. The bound is therefore
#: computed per cell as the design share plus three standard deviations.
FLOOR_DESIGN_SHARE_PCT = 40.0
SIGMA_ALLOWANCE = 3.0


def _floor_share_bound_pct(cell_size: int) -> float:
    """Upper bound on the floor's share for a cell of this size."""
    import math

    p = FLOOR_DESIGN_SHARE_PCT / 100.0
    sigma_pct = 100.0 * math.sqrt(p * (1 - p) / cell_size)
    return FLOOR_DESIGN_SHARE_PCT + SIGMA_ALLOWANCE * sigma_pct


def _database(env_var: str) -> Path:
    raw = os.environ.get(env_var)
    if not raw:
        pytest.skip(f"{env_var} not set; run the {env_var} scenario first")
    path = Path(raw)
    if not path.exists():
        pytest.skip(f"{env_var} points at a missing database: {path}")
    return path


_CELL_QUERY = """
    SELECT
      simulation_year,
      CASE WHEN current_age < 31 THEN 'young'
           WHEN current_age < 46 THEN 'mid_career'
           WHEN current_age < 56 THEN 'mature'
           ELSE 'senior' END AS age_seg,
      CASE WHEN current_compensation < 50000 THEN 'low'
           WHEN current_compensation < 100000 THEN 'moderate'
           WHEN current_compensation < 200000 THEN 'high'
           ELSE 'executive' END AS income_seg,
      ROUND(current_deferral_rate, 4) AS rate,
      COUNT(*) AS n
    FROM fct_workforce_snapshot
    WHERE EXTRACT(YEAR FROM employee_hire_date) = simulation_year
      AND participation_status_detail = 'participating - voluntary enrollment'
    GROUP BY 1, 2, 3, 4
"""


def _cells(database: Path) -> dict[tuple, dict[float, int]]:
    with duckdb.connect(str(database), read_only=True) as conn:
        rows = conn.execute(_CELL_QUERY).fetchall()
    cells: dict[tuple, dict[float, int]] = {}
    for year, age, income, rate, n in rows:
        cells.setdefault((year, age, income), {})[float(rate)] = n
    return cells


class TestSpreadBreaksUpTheSpike:
    """SC-010: no cell is a single spike any more."""

    #: Cells this small are dominated by integer effects, not distribution.
    MIN_CELL_SIZE = 30

    def test_the_table_value_is_no_longer_a_spike(self):
        """The floor must stop holding the whole cell.

        Deliberately measured at the FLOOR rather than at "any single rate".
        The match magnet legitimately piles employees onto the employer-match
        ceiling -- in the baseline the young/moderate cell already sat at 96
        people on 3% and 86 on 6% for exactly that reason. Asserting that no
        rate anywhere holds >45% would demand we break match-maximising
        behaviour, which is real and wanted. What this feature owes is that
        the demographic table value stops being a spike.
        """
        baseline = _cells(_database("PLANALIGN_652_DB_BASELINE"))
        spread = _cells(_database("PLANALIGN_652_DB_SPREAD"))
        offenders = []
        checked = 0
        for key, dist in spread.items():
            total = sum(dist.values())
            base = baseline.get(key)
            if total < self.MIN_CELL_SIZE or not base:
                continue
            checked += 1
            floor = min(base)
            share = 100.0 * dist.get(floor, 0) / total
            bound = _floor_share_bound_pct(total)
            if share > bound:
                offenders.append((key, round(share, 1), round(bound, 1), total))
        assert checked, "no cells large enough to judge"
        assert not offenders, (
            "cells still spiking on their table value "
            f"(cell, observed%, bound%, n): {offenders[:5]}"
        )

    def test_baseline_really_was_a_spike(self):
        """Guards the premise: without the spread, cells sit on 1-2 values.

        Baseline cells hold at most two rates -- the table value and the
        match ceiling -- so counting distinct rates is the honest measure of
        "this looks assigned, not elected".
        """
        cells = _cells(_database("PLANALIGN_652_DB_BASELINE"))
        assert cells, "no voluntary new-hire enrollments in the baseline"
        checked = [
            len(dist)
            for dist in cells.values()
            if sum(dist.values()) >= self.MIN_CELL_SIZE
        ]
        assert checked, "no cells large enough to judge"
        assert (
            max(checked) <= 2
        ), f"expected baseline cells to hold at most 2 rates, saw {max(checked)}"


class TestFloorIsRespected:
    """SC-011 / FR-019: the table value is a floor, never a centre."""

    def test_no_rate_falls_below_the_cell_floor(self):
        """Every spread rate must be >= the same cell's baseline rate."""
        baseline = _cells(_database("PLANALIGN_652_DB_BASELINE"))
        spread = _cells(_database("PLANALIGN_652_DB_SPREAD"))
        violations = []
        for key, dist in spread.items():
            base = baseline.get(key)
            if not base:
                continue
            # The baseline cell is a spike, so its floor is its only/lowest rate.
            floor = min(base)
            below = [r for r in dist if r < floor - 1e-9]
            if below:
                violations.append((key, floor, sorted(below)[:3]))
        assert not violations, f"rates below their cell floor: {violations[:5]}"


class TestSpreadIsOptIn:
    """SC-012 / FR-020: disabled means byte-identical to before."""

    def test_disabled_spread_changes_nothing_on_its_own(self):
        """The spread must contribute exactly zero when switched off.

        Compared against the CAP baseline, not the original pre-change
        baseline. Raising the deferral cap from 10% to 15% (decision D7) is a
        separate, deliberate change that moves 295 employee-years whether or
        not the spread is enabled; see cap-change-impact.md. Comparing against
        the pre-cap baseline would fold that change into this assertion and
        make the spread look responsible for it.
        """
        baseline = _database("PLANALIGN_652_DB_CAP_BASELINE")
        candidate = _database("PLANALIGN_652_DB_UNSET")
        query = """
            SELECT employee_id, simulation_year, current_deferral_rate
            FROM fct_workforce_snapshot ORDER BY 1, 2
        """
        with duckdb.connect(str(baseline), read_only=True) as conn:
            before = conn.execute(query).fetchall()
        with duckdb.connect(str(candidate), read_only=True) as conn:
            after = conn.execute(query).fetchall()
        assert before == after, "deferral rates moved with the spread disabled"


class TestLiftDistribution:
    """FR-018: the decay shape, measured against the configured weights."""

    #: +0..+4 at 40/30/15/10/5. Generous tolerance: the match-magnet snap runs
    #: after the spread and legitimately moves some employees upward.
    EXPECTED = {0: 40.0, 1: 30.0, 2: 15.0, 3: 10.0, 4: 5.0}
    TOLERANCE_PCT = 12.0

    def test_lift_decays_from_the_floor(self):
        baseline = _cells(_database("PLANALIGN_652_DB_BASELINE"))
        spread = _cells(_database("PLANALIGN_652_DB_SPREAD"))
        lift_counts: dict[int, int] = {}
        for key, dist in spread.items():
            base = baseline.get(key)
            if not base:
                continue
            floor = min(base)
            for rate, n in dist.items():
                lift = int(round((rate - floor) * 100))
                if 0 <= lift <= 4:
                    lift_counts[lift] = lift_counts.get(lift, 0) + n
        total = sum(lift_counts.values())
        assert total, "no employees mapped to a lift bucket"
        for lift, expected in self.EXPECTED.items():
            share = 100.0 * lift_counts.get(lift, 0) / total
            assert share == pytest.approx(
                expected, abs=self.TOLERANCE_PCT
            ), f"+{lift}pp holds {share:.1f}% of employees, expected ~{expected}%"

    def test_floor_is_the_most_common_single_outcome(self):
        baseline = _cells(_database("PLANALIGN_652_DB_BASELINE"))
        spread = _cells(_database("PLANALIGN_652_DB_SPREAD"))
        lift_counts: dict[int, int] = {}
        for key, dist in spread.items():
            base = baseline.get(key)
            if not base:
                continue
            floor = min(base)
            for rate, n in dist.items():
                lift = int(round((rate - floor) * 100))
                if 0 <= lift <= 4:
                    lift_counts[lift] = lift_counts.get(lift, 0) + n
        assert lift_counts, "no employees mapped to a lift bucket"
        assert (
            max(lift_counts, key=lift_counts.get) == 0
        ), f"the floor is not the most common outcome: {lift_counts}"
