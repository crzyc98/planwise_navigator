"""Execute the acquired-member SQL against small synthetic workforces (#1226)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest
from jinja2 import Environment

pytestmark = [pytest.mark.fast, pytest.mark.dbt]
DBT = Path(__file__).resolve().parents[2] / "dbt"
YEAR = 2025


def _render(headcount: int, **overrides: Any) -> str:
    env = Environment()
    joining = [
        {
            "id": "acme",
            "headcount": headcount,
            "effective_date": f"{YEAR}-07-01",
            "ordinal": 1,
            "service_credit": overrides.pop("service_credit", "prior_service"),
            **overrides,
        }
    ]
    env.globals.update(
        var=lambda name, default=None: {
            "simulation_year": YEAR,
            "start_year": YEAR,
        }.get(name, default),
        config=lambda **kwargs: "",
        ref=lambda name: name,
        subsystem_seed=lambda name: 42,
        assign_age_band=lambda column: "'age_band'",
        assign_tenure_band=lambda column: "'tenure_band'",
        acquisitions_joining=lambda year: joining,
        acquisition_member_id=lambda acquisition, seq: (
            f"'ACQ_' || {acquisition} || '_' || LPAD(CAST({seq} AS VARCHAR), 6, '0')"
        ),
    )
    model = DBT / "models/intermediate/events/int_acquisition_hire_events.sql"
    return env.from_string(model.read_text()).render()


def _workforce(active: int, inactive: int) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    hash_source = (DBT / "macros/utils/stable_hash.sql").read_text()
    conn.execute(Environment().from_string(hash_source).module.install_stable_hash())
    conn.execute(
        """CREATE TABLE int_baseline_workforce AS
        SELECT 'E' || i AS employee_id, 30 + i % 20 AS current_age,
          i % 7 AS current_tenure, 1 + i % 3 AS level_id,
          50000.0 + i AS current_compensation, ? AS simulation_year,
          CASE WHEN i < ? THEN 'active' ELSE 'terminated' END AS employment_status
        FROM range(?) t(i)""",
        [YEAR, active, active + inactive],
    )
    conn.execute("""CREATE TABLE stg_census_data AS
        SELECT employee_id, NULL::DECIMAL(5,2) AS scheduled_hours_per_week
        FROM int_baseline_workforce""")
    return conn


@pytest.mark.parametrize(("inactive", "headcount"), [(3, 5000), (5000, 3)])
def test_acquisition_with_no_active_staff_fails_loudly(
    inactive: int, headcount: int
) -> None:
    """An acquisition with nobody to sample raises, at either relative size."""
    conn = _workforce(active=0, inactive=inactive)
    with pytest.raises(duckdb.Error, match="no active employees to sample"):
        conn.execute(_render(headcount)).fetchall()


def test_members_are_drawn_only_from_active_staff_with_replacement() -> None:
    conn = _workforce(active=4, inactive=50)
    rows = conn.execute(
        f"SELECT employee_id, compensation_amount, employee_ssn FROM ({_render(25)})"
    ).fetchall()
    assert len(rows) == 25
    assert len({row[0] for row in rows}) == 25
    assert len({row[2] for row in rows}) == 25
    assert all(row[0].startswith("ACQ_acme_") for row in rows)
    assert {row[1] for row in rows} <= {50000.0, 50001.0, 50002.0, 50003.0}


# --- #1228: who the group is -------------------------------------------------

MEMBERS = """
    SELECT employee_id, compensation_amount, employee_age, employee_tenure
    FROM ({sql}) ORDER BY employee_id
"""


def _members(conn: duckdb.DuckDBPyConnection, **overrides: Any) -> list[tuple]:
    return conn.execute(MEMBERS.format(sql=_render(400, **overrides))).fetchall()


def _mean(rows: list[tuple], column: int) -> float:
    return sum(float(row[column]) for row in rows) / len(rows)


def _spread_workforce() -> duckdb.DuckDBPyConnection:
    """Active staff with a wide pay spread, ages 22-61 and service 0-24."""
    conn = _workforce(active=200, inactive=0)
    conn.execute(
        """UPDATE int_baseline_workforce SET
          current_age = 22 + CAST(employee_id[2:] AS INT) % 40,
          current_tenure = CAST(employee_id[2:] AS INT) % 25 * 1.0,
          current_compensation = 30000.0 + 1500 * (CAST(employee_id[2:] AS INT) % 97)"""
    )
    conn.execute(
        "UPDATE int_baseline_workforce SET current_tenure = "
        "LEAST(current_tenure, current_age - 18)"
    )
    return conn


@pytest.mark.parametrize("relative_pay", [0.9, 1.25])
def test_relative_pay_scales_every_member_by_one_factor(relative_pay: float) -> None:
    conn = _spread_workforce()
    base = _members(conn)
    scaled = _members(conn, relative_pay=relative_pay)
    assert [row[0] for row in scaled] == [row[0] for row in base]
    for before, after in zip(base, scaled):
        assert after[1] == pytest.approx(before[1] * relative_pay)
        assert after[2:] == before[2:]


def test_average_pay_hits_the_target_and_keeps_the_spread() -> None:
    conn = _spread_workforce()
    base = _members(conn)
    scaled = _members(conn, average_pay=95_000.0)
    assert _mean(scaled, 1) == pytest.approx(95_000.0)
    factor = 95_000.0 / _mean(base, 1)
    for before, after in zip(base, scaled):
        assert after[1] == pytest.approx(before[1] * factor)


def test_average_age_and_service_shift_every_member_to_the_target() -> None:
    conn = _spread_workforce()
    base = _members(conn)
    moved = _members(conn, average_age=50.0, average_service=12.0)
    # Whole-year shifts: the mean lands within half a year (no clamping here).
    assert _mean(moved, 2) == pytest.approx(50.0, abs=0.5)
    assert _mean(moved, 3) == pytest.approx(12.0, abs=0.5)
    age_shifts = {after[2] - before[2] for before, after in zip(base, moved)}
    assert len(age_shifts) == 1
    assert [row[1] for row in moved] == [row[1] for row in base]
    assert all(0 <= row[3] <= row[2] - 18 for row in moved)


def test_age_and_service_are_clamped_to_sane_bounds() -> None:
    conn = _spread_workforce()
    young = _members(conn, average_age=19.0, average_service=30.0)
    assert min(row[2] for row in young) == 18
    assert all(0 <= row[3] <= row[2] - 18 for row in young)
    # A target of zero shifts everyone down by the mean; clamping at zero
    # leaves the most senior members above it, so the mean lands above zero.
    base = _members(conn)
    low = _members(conn, average_service=0.0)
    assert min(row[3] for row in low) == 0
    assert 0 < _mean(low, 3) < _mean(base, 3)


def test_service_from_the_acquisition_date_zeroes_shifted_service() -> None:
    conn = _spread_workforce()
    rows = _members(conn, average_service=10.0, service_credit="acquisition_date")
    assert {float(row[3]) for row in rows} == {0.0}


def test_bands_follow_adjusted_age_and_service() -> None:
    sql = _render(5, average_age=40.0, average_service=5.0)
    assert "'age_band' AS age_band" in sql
    assert "credited.tenure" in sql
    banded = _render(5, average_age=40.0)
    assert "member.current_age" in banded


def test_unset_overrides_render_no_adjustment() -> None:
    sql = _render(5)
    assert "sampled_means" not in sql
    assert "means.mean" not in sql
