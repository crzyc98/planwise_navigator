"""Issue #652: flat new-hire voluntary-enrollment and opt-out rates.

The controls under test are only observable in a completed multi-year
simulation, so these tests query databases produced out of band rather than
running the pipeline inside pytest. Build them with, for example:

    DATABASE_PATH=var/652/us1.duckdb planalign simulate 2026-2030 \
      --config var/652/us1.yaml --database var/652/us1.duckdb

then point the matching environment variable at the result. A test whose
database is absent skips rather than fails, so the suite stays green on a
machine that has not run the sweep.

Populations follow the specification exactly: the denominator is *eligible*
new hires (hire year == simulation year, plan-eligible), because new hires
inside a waiting period are outside the scope of both rates.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.dbt]

# Selection is a per-employee hash draw rather than an exact count (decision
# D3), so a cohort of roughly a thousand deviates about 1.7 points at one
# standard deviation. Two points is the honest tolerance.
TOLERANCE_PCT = 2.0

VOLUNTARY = "participating - voluntary enrollment"
AUTO = "participating - auto enrollment"
OPTED_OUT = "not_participating - opted out of AE"
NOT_ENROLLED = "not_participating - not auto enrolled"


def _database(env_var: str) -> Path:
    raw = os.environ.get(env_var)
    if not raw:
        pytest.skip(f"{env_var} not set; run the {env_var} scenario first")
    path = Path(raw)
    if not path.exists():
        pytest.skip(f"{env_var} points at a missing database: {path}")
    return path


def _eligible_new_hire_shares(database: Path) -> dict[int, dict[str, float]]:
    """Percentage split of eligible new hires by outcome, keyed by year.

    Restricted to new hires still active at year end. A new hire who
    terminates before their auto-enrollment date generates no enrollment
    event at all, which is correct behaviour, so including them would put a
    permanent floor under "not enrolled" that no rate setting can move.
    """
    with duckdb.connect(str(database), read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT
              simulation_year,
              participation_status_detail,
              100.0 * COUNT(*)
                / SUM(COUNT(*)) OVER (PARTITION BY simulation_year) AS pct
            FROM fct_workforce_snapshot
            WHERE EXTRACT(YEAR FROM employee_hire_date) = simulation_year
              AND current_eligibility_status = 'eligible'
              AND termination_date IS NULL
            GROUP BY 1, 2
            """
        ).fetchall()
    shares: dict[int, dict[str, float]] = {}
    for year, detail, pct in rows:
        shares.setdefault(year, {})[detail] = pct
    assert shares, "no eligible new hires found; the scenario produced no cohort"
    return shares


def _voluntary_employee_ids(database: Path) -> set[tuple[str, int]]:
    with duckdb.connect(str(database), read_only=True) as conn:
        return set(
            conn.execute(
                """
                SELECT employee_id, simulation_year
                FROM fct_yearly_events
                WHERE event_type = 'enrollment'
                  AND event_category = 'voluntary_enrollment'
                """
            ).fetchall()
        )


class TestVoluntaryRateIsHonoured:
    """US1 / SC-001, SC-002: the dial produces the share it names."""

    def test_sixty_percent_voluntary(self):
        """P=0.6 yields 60% voluntary among eligible new hires, every year."""
        shares = _eligible_new_hire_shares(_database("PLANALIGN_652_DB_P60Q10"))
        for year, split in sorted(shares.items()):
            assert split.get(VOLUNTARY, 0.0) == pytest.approx(
                60.0, abs=TOLERANCE_PCT
            ), f"{year}: voluntary share {split.get(VOLUNTARY, 0.0):.1f}% != 60%"

    def test_full_voluntary_has_no_demographic_cap(self):
        """P=1.0 yields ~100% voluntary. The original bug: it yielded ~58%."""
        shares = _eligible_new_hire_shares(_database("PLANALIGN_652_DB_P100"))
        for year, split in sorted(shares.items()):
            assert (
                split.get(VOLUNTARY, 0.0) >= 99.0
            ), f"{year}: voluntary share {split.get(VOLUNTARY, 0.0):.1f}% < 99%"


class TestDeterminism:
    """US1 / SC-005: same seed selects the same individuals, not just counts."""

    def test_identical_employees_selected_across_runs(self):
        first = _voluntary_employee_ids(_database("PLANALIGN_652_DB_P60Q10"))
        second = _voluntary_employee_ids(_database("PLANALIGN_652_DB_P60Q10_REPEAT"))
        assert first, "no voluntary enrollment events found"
        assert first == second, (
            f"{len(first ^ second)} employee-years differ between two runs at "
            "the same seed; selection is not reproducible"
        )


class TestSingleEnrollmentDecision:
    """US1 / FR-004: one decision per new hire, not two draws deduplicated."""

    def test_no_employee_enrolls_twice_in_a_year(self):
        database = _database("PLANALIGN_652_DB_P60Q10")
        with duckdb.connect(str(database), read_only=True) as conn:
            (count,) = conn.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT employee_id, simulation_year
                  FROM fct_yearly_events
                  WHERE event_type = 'enrollment'
                  GROUP BY 1, 2
                  HAVING COUNT(*) > 1
                )
                """
            ).fetchone()
        assert count == 0, f"{count} employee-years hold multiple enrollment events"

    def test_proactive_path_produces_nothing_when_flat_rate_is_set(self):
        """The second independent draw must be gone, not merely outranked."""
        database = _database("PLANALIGN_652_DB_P60Q10")
        with duckdb.connect(str(database), read_only=True) as conn:
            (count,) = conn.execute(
                """
                SELECT COUNT(*) FROM fct_yearly_events
                WHERE event_category = 'proactive_voluntary'
                """
            ).fetchone()
        assert count == 0, (
            f"{count} proactive_voluntary events remain; new hires are still "
            "being drawn twice"
        )


class TestFullDistribution:
    """US2 / SC-001, SC-003, SC-004: the whole four-way split."""

    def test_sixty_ten_split(self):
        """P=0.6, Q=0.1 -> 60% voluntary, 36% auto, 4% opted out, 0% unenrolled."""
        shares = _eligible_new_hire_shares(_database("PLANALIGN_652_DB_P60Q10"))
        for year, split in sorted(shares.items()):
            assert split.get(VOLUNTARY, 0.0) == pytest.approx(60.0, abs=TOLERANCE_PCT)
            assert split.get(AUTO, 0.0) == pytest.approx(36.0, abs=TOLERANCE_PCT)
            assert split.get(OPTED_OUT, 0.0) == pytest.approx(4.0, abs=TOLERANCE_PCT)

    def test_zero_voluntary_zero_optout_is_all_auto(self):
        """P=0.0, Q=0.0 -> everyone auto-enrolls and stays."""
        shares = _eligible_new_hire_shares(_database("PLANALIGN_652_DB_P0Q0"))
        for year, split in sorted(shares.items()):
            assert (
                split.get(AUTO, 0.0) >= 99.0
            ), f"{year}: auto-enrolled share {split.get(AUTO, 0.0):.1f}% < 99%"

    def test_no_active_eligible_new_hire_is_left_unenrolled(self):
        """SC-004, measured over new hires active at year end (decision D2).

        The residual in the reproduction was entirely people who terminated
        in their hire year, which is correct behaviour, so terminations are
        excluded rather than engineered away.
        """
        database = _database("PLANALIGN_652_DB_P60Q10")
        with duckdb.connect(str(database), read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT simulation_year, COUNT(*)
                FROM fct_workforce_snapshot
                WHERE EXTRACT(YEAR FROM employee_hire_date) = simulation_year
                  AND current_eligibility_status = 'eligible'
                  AND termination_date IS NULL
                  AND participation_status_detail = ?
                GROUP BY 1 ORDER BY 1
                """,
                [NOT_ENROLLED],
            ).fetchall()
        offenders = {year: n for year, n in rows if n > 0}
        assert not offenders, f"active eligible new hires left unenrolled: {offenders}"


class TestContinuingEmployeesUnaffected:
    """US4 / SC-006, SC-009: the blast radius is new hires only.

    "Continuing" here means employees hired BEFORE the simulation window --
    the census population the new-hire rates can never reach. Defining it as
    "hire year != simulation year" would be wrong: a 2026 new hire is a
    continuing employee in 2027 and legitimately carries its changed
    enrollment forward, so that population is expected to move.
    """

    #: First simulated year. Anyone hired before this is census population.
    START_YEAR = 2026

    def test_continuing_employee_enrollment_matches_baseline(self):
        """With both rates unset, nothing moves at all."""
        baseline = _database("PLANALIGN_652_DB_BASELINE")
        candidate = _database("PLANALIGN_652_DB_UNSET")
        query = f"""
            SELECT simulation_year, participation_status_detail, COUNT(*)
            FROM fct_workforce_snapshot
            WHERE employee_hire_date < DATE '{self.START_YEAR}-01-01'
            GROUP BY 1, 2 ORDER BY 1, 2
        """
        with duckdb.connect(str(baseline), read_only=True) as conn:
            before = conn.execute(query).fetchall()
        with duckdb.connect(str(candidate), read_only=True) as conn:
            after = conn.execute(query).fetchall()
        assert before == after, "continuing-employee enrollment counts changed"

    def test_changing_new_hire_rate_leaves_continuing_employees_alone(self):
        baseline = _database("PLANALIGN_652_DB_BASELINE")
        candidate = _database("PLANALIGN_652_DB_P60Q10")
        query = f"""
            SELECT simulation_year, COUNT(*)
            FROM fct_workforce_snapshot
            WHERE employee_hire_date < DATE '{self.START_YEAR}-01-01'
              AND participation_status = 'participating'
            GROUP BY 1 ORDER BY 1
        """
        with duckdb.connect(str(baseline), read_only=True) as conn:
            before = conn.execute(query).fetchall()
        with duckdb.connect(str(candidate), read_only=True) as conn:
            after = conn.execute(query).fetchall()
        assert (
            before == after
        ), "changing the new-hire voluntary rate moved continuing employees"
