"""Unit tests for part-time scheduled hours SQL formulas (#093 / GitHub issue #282).

Locks in the two SQL behaviors introduced by the feature, executed against
in-memory DuckDB with the exact expressions used in the dbt models:

1. Eligibility hours formula: ``COALESCE(scheduled_hours_per_week, 40.0) * 52.0``
   replaces the hardcoded 2080 in int_employer_eligibility and
   int_eligibility_computation_period.
2. Part-time new hire assignment: deterministic hash in int_hiring_events
   selects a stable ``part_time_new_hire_pct`` fraction of each cohort.
"""

import duckdb
import pytest

pytestmark = [pytest.mark.fast]


HOURS_FORMULA = "COALESCE(scheduled_hours_per_week, 40.0) * 52.0"

# Exact expression from int_hiring_events.sql (with year inlined)
PT_HASH_EXPR = (
    "ABS(MOD(HASH(CONCAT(CAST(seq AS VARCHAR), '_pt_', CAST(2025 AS VARCHAR)))::DOUBLE,"
    " 1000000.0)) / 1000000.0"
)


@pytest.fixture
def conn():
    con = duckdb.connect(":memory:")
    yield con
    con.close()


class TestEligibilityHoursFormula:
    """The COALESCE formula that replaced hardcoded 2080."""

    def test_null_schedule_yields_2080(self, conn):
        """NULL scheduled hours → full-time 2080 annual hours (no regression)."""
        result = conn.execute(
            f"SELECT {HOURS_FORMULA} FROM (SELECT NULL::DECIMAL(5,2) AS scheduled_hours_per_week)"
        ).fetchone()[0]
        assert result == 2080.0

    def test_20_hours_yields_1040(self, conn):
        """20 hrs/week → 1,040 annual hours."""
        result = conn.execute(
            f"SELECT {HOURS_FORMULA} FROM (SELECT 20.0::DECIMAL(5,2) AS scheduled_hours_per_week)"
        ).fetchone()[0]
        assert result == 1040.0

    def test_partial_year_proration(self, conn):
        """Half-year part-time employee gets half of 1,040 hours (within rounding)."""
        # 182 days employed at 20 hrs/wk: days * (hrs * 52 / 365)
        result = conn.execute(
            f"SELECT 182 * ({HOURS_FORMULA} / 365.0) "
            "FROM (SELECT 20.0::DECIMAL(5,2) AS scheduled_hours_per_week)"
        ).fetchone()[0]
        assert result == pytest.approx(518.6, abs=0.5)

    def test_part_time_cannot_reach_full_time_hours(self, conn):
        """A full-year 20 hrs/wk employee is capped at 1,040 — the bug this feature fixes."""
        result = conn.execute(
            f"SELECT {HOURS_FORMULA} FROM (SELECT 20.0::DECIMAL(5,2) AS scheduled_hours_per_week)"
        ).fetchone()[0]
        assert result < 2080.0


class TestPartTimeNewHireHash:
    """The deterministic hash assignment in int_hiring_events."""

    def _pt_count(self, conn, pct: float, n: int = 1000) -> int:
        return conn.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT seq FROM range(1, {n + 1}) t(seq)
                WHERE {PT_HASH_EXPR} < {pct}
            )
            """
        ).fetchone()[0]

    def test_zero_pct_assigns_no_part_time(self, conn):
        assert self._pt_count(conn, 0.0) == 0

    def test_20_pct_assigns_roughly_20_percent(self, conn):
        count = self._pt_count(conn, 0.2, n=1000)
        assert 150 <= count <= 250  # ~20% with hash-distribution tolerance

    def test_assignment_is_deterministic(self, conn):
        """Same sequence numbers and year → identical assignment across runs."""
        query = f"""
            SELECT seq FROM range(1, 1001) t(seq)
            WHERE {PT_HASH_EXPR} < 0.2
            ORDER BY seq
        """
        first = conn.execute(query).fetchall()
        second = conn.execute(query).fetchall()
        assert first == second
        assert len(first) > 0
