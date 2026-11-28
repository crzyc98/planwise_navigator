"""Join-year hours credit for an acquired group (#1329).

Isolated 2025-2027 runs share one config and seed. Each adds the same group of
40 joining on 1 October 2026, who work about 510 hours before year end, under a
plan that requires 1,000 hours for match (the simple rule, ``apply_eligibility:
false``) and for core (configured rules). One run leaves
``join_year_hours_credit`` unset; the other sets ``full_year``.

Without the credit the group gets no match or core in 2026. With it the group
gets both, on the same deferrals and earned pay. Nothing else changes: every
event, every other employee, and the group's 2027 contributions are the same.
A third run keeps the credit and switches match to configured rules
(``apply_eligibility: true``), the other form the match hours test takes.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterator

import duckdb
import pytest
import yaml

from planalign_orchestrator.config import SimulationConfig, load_simulation_config
from tests.fixtures.invariant_simulation import (
    CONFIG_YAML,
    SimulationRun,
    _execute,
    require_successful_run,
)

pytest_plugins = ("tests.fixtures.invariant_simulation",)
pytestmark = [pytest.mark.integration, pytest.mark.edge_config_matrix]

JOIN_YEAR = 2026
EFFECTIVE = date(JOIN_YEAR, 10, 1)
HEADCOUNT = 40
CORE_RATE = 0.02
MINIMUM_HOURS = 1000
# Contribution columns the credit may change, and only in the join year.
EMPLOYER_COLUMNS = (
    "employer_match_amount",
    "employer_core_amount",
    "total_employer_contributions",
)
# Run-time stamps and ids that differ between any two runs.
VOLATILE_COLUMNS = frozenset(
    {"event_id", "created_at", "snapshot_created_at", "parameter_scenario_id"}
)


def _config(
    census_parquet: Path,
    path: Path,
    credit: str | None,
    configured_match: bool = False,
) -> SimulationConfig:
    raw = yaml.safe_load(CONFIG_YAML.read_text())
    raw["scenario_id"] = "acquisition_join_year_hours"
    raw["setup"]["census_parquet_path"] = str(census_parquet)
    raw["employer_core_contribution"] = {
        "enabled": True,
        "status": "flat",
        "contribution_rate": CORE_RATE,
        "eligibility": {
            "minimum_tenure_years": 0,
            "require_active_at_year_end": True,
            "minimum_hours_annual": MINIMUM_HOURS,
            "allow_new_hires": True,
        },
    }
    if configured_match:
        raw["employer_match"]["apply_eligibility"] = True
        raw["employer_match"]["eligibility"] = {
            "minimum_tenure_years": 0,
            "require_active_at_year_end": True,
            "minimum_hours_annual": MINIMUM_HOURS,
            "allow_new_hires": True,
        }
    group: dict[str, Any] = {
        "id": "late",
        "headcount": HEADCOUNT,
        "effective_date": EFFECTIVE,
    }
    if credit is not None:
        group["join_year_hours_credit"] = credit
    raw["workforce"]["acquisitions"] = [group]
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return load_simulation_config(path, env_overrides=False)


@pytest.fixture(scope="module")
def runs(
    tmp_path_factory: pytest.TempPathFactory,
    invariant_census_parquet: Path,
    shared_dev_db_signature: tuple[int, str] | None,
) -> Iterator[tuple[SimulationRun, ...]]:
    del shared_dev_db_signature
    root = tmp_path_factory.mktemp("acquisition-join-year-hours")
    off = _execute(
        root / "off.duckdb",
        invariant_census_parquet,
        _config(invariant_census_parquet, root / "off.yaml", None),
    )
    on = _execute(
        root / "on.duckdb",
        invariant_census_parquet,
        _config(invariant_census_parquet, root / "on.yaml", "full_year"),
    )
    configured = _execute(
        root / "configured.duckdb",
        invariant_census_parquet,
        _config(
            invariant_census_parquet,
            root / "configured.yaml",
            "full_year",
            configured_match=True,
        ),
    )
    yield off, on, configured


@pytest.fixture(scope="module")
def off_db(runs: tuple[SimulationRun, ...]) -> Path:
    return require_successful_run(runs[0])


@pytest.fixture(scope="module")
def on_db(runs: tuple[SimulationRun, ...]) -> Path:
    return require_successful_run(runs[1])


@pytest.fixture(scope="module")
def configured_db(runs: tuple[SimulationRun, ...]) -> Path:
    return require_successful_run(runs[2])


def _rows(database: Path, sql: str) -> list[tuple[Any, ...]]:
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(sql).fetchall()


def _group_totals(database: Path, year: int) -> tuple[Any, ...]:
    [row] = _rows(
        database,
        f"""
        SELECT COUNT(*), SUM(ytd_contributions), SUM(employer_match_amount),
          SUM(employer_core_amount), AVG(annual_hours_worked)
        FROM fct_workforce_snapshot
        WHERE acquisition_id = 'late' AND simulation_year = {year}
        """,
    )
    return row


def _comparable(database: Path, table: str, exclude: frozenset[str]) -> list[Any]:
    """Every row of a table, ordered, with volatile columns dropped and numbers
    rounded to a cent's hundredth (main drifts ~1e-13 between runs)."""
    with duckdb.connect(str(database), read_only=True) as connection:
        described = connection.execute(f"DESCRIBE {table}").fetchall()
        columns = [
            f"ROUND({name}, 4)" if kind.startswith(("DOUBLE", "DECIMAL")) else name
            for name, kind, *_ in described
            if name not in exclude
        ]
        listed = ", ".join(columns)
        return connection.execute(
            f"SELECT {listed} FROM {table} ORDER BY ALL"
        ).fetchall()


def test_both_runs_completed(runs: tuple[SimulationRun, ...]) -> None:
    for run in runs:
        assert run.error is None, repr(run.error)


def test_without_credit_the_group_gets_no_match_or_core(off_db: Path) -> None:
    members, deferrals, match, core, hours = _group_totals(off_db, JOIN_YEAR)
    assert members == HEADCOUNT
    assert deferrals > 0
    assert hours < MINIMUM_HOURS
    assert (match, core) == (0, 0)


def test_with_credit_the_group_gets_match_and_core(on_db: Path) -> None:
    members, deferrals, match, core, hours = _group_totals(on_db, JOIN_YEAR)
    assert members == HEADCOUNT
    assert hours < MINIMUM_HOURS
    assert match > 0 and core > 0
    rows = _rows(
        on_db,
        f"""
        SELECT s.employment_status,
          LEAST(s.prorated_annual_compensation, c.irs_401a17_limit),
          s.ytd_contributions, s.employer_match_amount, s.employer_core_amount
        FROM fct_workforce_snapshot s
        JOIN int_employer_core_contributions c
          ON c.employee_id = s.employee_id AND c.simulation_year = s.simulation_year
        WHERE s.acquisition_id = 'late' AND s.simulation_year = {JOIN_YEAR}
        """,
    )
    for status, earned, deferred, member_match, member_core in rows:
        if status != "active":
            continue
        # Core is the flat rate on earned (prorated, capped) pay, not a full year's.
        assert float(member_core) == pytest.approx(CORE_RATE * float(earned), abs=0.01)
        # The tiered match never exceeds the member's own deferrals.
        assert 0 <= float(member_match) <= float(deferred) + 0.01
        assert (float(member_match) > 0) == (float(deferred) > 0)


def test_credit_is_flagged_for_the_group_in_its_join_year_only(on_db: Path) -> None:
    rows = _rows(
        on_db,
        """
        SELECT simulation_year, employee_id LIKE 'ACQ_late_%' AS member,
          COUNT(*) FILTER (WHERE join_year_hours_credited),
          MAX(annual_hours_worked) FILTER (WHERE join_year_hours_credited)
        FROM int_employer_eligibility
        GROUP BY ALL
        ORDER BY ALL
        """,
    )
    credited = {(year, member): (count, hours) for year, member, count, hours in rows}
    assert credited[(JOIN_YEAR, True)][0] == HEADCOUNT
    assert credited[(JOIN_YEAR, True)][1] < MINIMUM_HOURS
    others = {key: value for key, value in credited.items() if key != (JOIN_YEAR, True)}
    assert all(count == 0 for count, _ in others.values())
    [(missing,)] = _rows(
        on_db,
        "SELECT COUNT(*) FROM int_employer_eligibility "
        "WHERE join_year_hours_credited IS NULL",
    )
    assert missing == 0


def test_events_are_identical(off_db: Path, on_db: Path) -> None:
    assert _comparable(off_db, "fct_yearly_events", VOLATILE_COLUMNS) == _comparable(
        on_db, "fct_yearly_events", VOLATILE_COLUMNS
    )


def test_snapshot_differs_only_in_the_groups_join_year_employer_money(
    off_db: Path, on_db: Path
) -> None:
    exclude = VOLATILE_COLUMNS | frozenset(EMPLOYER_COLUMNS)
    assert _comparable(off_db, "fct_workforce_snapshot", exclude) == _comparable(
        on_db, "fct_workforce_snapshot", exclude
    )
    employer = ", ".join(EMPLOYER_COLUMNS)
    outside_join_year = f"""
        SELECT employee_id, simulation_year, {employer}
        FROM fct_workforce_snapshot
        WHERE NOT (acquisition_id = 'late' AND simulation_year = {JOIN_YEAR})
          OR acquisition_id IS NULL
        ORDER BY ALL
    """
    assert _rows(off_db, outside_join_year) == _rows(on_db, outside_join_year)
    following = _group_totals(on_db, JOIN_YEAR + 1)
    assert following == _group_totals(off_db, JOIN_YEAR + 1)
    assert following[2] > 0 and following[3] > 0


def test_configured_match_rules_also_take_the_credit(configured_db: Path) -> None:
    rows = _rows(
        configured_db,
        f"""
        SELECT employee_id LIKE 'ACQ_late_%' AS member, match_eligibility_reason,
          COUNT(*)
        FROM int_employer_eligibility
        WHERE simulation_year = {JOIN_YEAR}
          AND annual_hours_worked < {MINIMUM_HOURS}
          AND employment_status = 'active'
        GROUP BY ALL
        """,
    )
    reasons = {(member, reason): count for member, reason, count in rows}
    assert reasons.get((True, "eligible")) == HEADCOUNT
    # Anyone else short of the hours, such as a late hire, is still held to them.
    assert all(
        reason == "insufficient_hours" for member, reason in reasons if not member
    )
    _, _, match, core, _ = _group_totals(configured_db, JOIN_YEAR)
    assert match > 0 and core > 0
