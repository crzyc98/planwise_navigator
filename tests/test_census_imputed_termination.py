"""Inactive census rows with no termination date (#1249)."""

from typing import Optional

import duckdb
import pytest

from planalign_api.services.census_schema import BOOLEAN_TRUE_ALIASES
from planalign_orchestrator.census_imputed_terminations import (
    report_imputed_terminations,
)
from tests.test_census_pay_basis import staging_ctes

pytestmark = pytest.mark.fast

Row = tuple[str, str, Optional[str], object]


def staged(rows: list[Row], dbt_vars: Optional[dict] = None) -> dict[str, tuple]:
    """employee_id -> (termination date, imputed flag) from the staging CTEs."""
    with duckdb.connect(":memory:") as conn:
        conn.execute("""CREATE TABLE raw_data (employee_id VARCHAR,
          employee_hire_date DATE, employee_termination_date DATE,
          employee_gross_compensation DOUBLE, active VARCHAR, rn INTEGER)""")
        conn.executemany(
            "INSERT INTO raw_data VALUES (?, ?, ?, 50000, ?, 1)",
            [(i, h, t, None if a is None else str(a)) for i, h, t, a in rows],
        )
        result = conn.execute(
            "WITH "
            + staging_ctes(dbt_vars or {}).rstrip().removesuffix(",")
            + " SELECT employee_id, employee_termination_date,"
            " termination_date_imputed FROM census_rows"
        ).fetchall()
    return {r[0]: (None if r[1] is None else str(r[1]), r[2]) for r in result}


def test_inactive_row_without_date_gets_the_plan_year_end() -> None:
    rows = staged(
        [
            ("current", "2020-01-01", None, "Y"),
            ("blank", "2020-01-01", None, None),
            ("stale", "2020-01-01", None, "N"),
            ("dated", "2020-01-01", "2025-03-31", "N"),
            ("late_hire", "2026-02-01", None, "false"),
            ("hire_2025", "2025-06-01", None, "Y"),
        ],
        {"plan_year_start_date": "2025-01-01"},
    )
    assert rows["current"] == (None, False)
    assert rows["blank"] == (None, False)
    assert rows["stale"] == ("2025-12-31", True)
    assert rows["dated"] == ("2025-03-31", False)
    # Never before the hire date, so termination_before_hire can't fire.
    assert rows["late_hire"] == ("2026-02-01", True)
    assert rows["hire_2025"] == (None, False)


@pytest.mark.parametrize("alias", sorted(BOOLEAN_TRUE_ALIASES))
def test_studio_true_aliases_stay_active(alias: str) -> None:
    rows = staged(
        [("x", "2020-01-01", None, alias.upper()), ("y", "2025-01-01", None, "Y")]
    )
    assert rows["x"] == (None, False)


def test_boolean_active_column() -> None:
    with duckdb.connect(":memory:") as conn:
        conn.execute("""CREATE TABLE raw_data AS SELECT * FROM (VALUES
          ('a', DATE '2025-01-01', NULL::DATE, 1., TRUE, 1),
          ('b', DATE '2024-01-01', NULL::DATE, 1., FALSE, 1)
        ) t(employee_id, employee_hire_date, employee_termination_date,
            employee_gross_compensation, active, rn)""")
        flags = dict(
            conn.execute(
                "WITH "
                + staging_ctes({}).rstrip().removesuffix(",")
                + " SELECT employee_id, termination_date_imputed FROM census_rows"
            ).fetchall()
        )
    assert flags == {"a": False, "b": True}


class _Sink:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def log_warning(self, message: str, **kwargs: object) -> None:
        self.messages.append(message)


def test_run_warning_names_the_count_and_date() -> None:
    sink = _Sink()
    with duckdb.connect(":memory:") as conn:
        conn.execute("""CREATE TABLE stg_census_data AS SELECT * FROM (VALUES
          (DATE '2025-12-31', TRUE), (DATE '2025-12-31', TRUE), (NULL, FALSE)
        ) t(employee_termination_date, termination_date_imputed)""")
        report_imputed_terminations(conn, sink)
        conn.execute("DELETE FROM stg_census_data WHERE termination_date_imputed")
        assert report_imputed_terminations(conn, sink) is None
    assert len(sink.messages) == 1
    assert "2 row(s) are marked inactive" in sink.messages[0]
    assert "2025-12-31" in sink.messages[0]


def test_run_warning_skips_without_staged_census() -> None:
    sink = _Sink()
    with duckdb.connect(":memory:") as conn:
        assert report_imputed_terminations(conn, sink) is None
    assert sink.messages == []


def test_stored_census_as_of_date_wins_over_the_plan_year_end() -> None:
    rows = staged(
        [
            ("stale", "2020-01-01", None, "N"),
            ("late_hire", "2025-11-01", None, "N"),
            ("current", "2025-06-01", None, "Y"),
        ],
        {"census_as_of_date": "2025-09-30"},
    )
    assert rows["stale"] == ("2025-09-30", True)
    assert rows["late_hire"] == ("2025-11-01", True)
    assert rows["current"] == (None, False)


def test_census_as_of_date_is_exported_and_validated() -> None:
    from planalign_orchestrator.config import load_simulation_config, to_dbt_vars
    from planalign_orchestrator.config.dbt_var_validation import validate_dbt_vars

    cfg = load_simulation_config("config/simulation_config.yaml")
    assert "census_as_of_date" not in to_dbt_vars(cfg)
    cfg.setup["census_as_of_date"] = "2025-09-30"
    exported = to_dbt_vars(cfg)
    assert exported["census_as_of_date"] == "2025-09-30"
    assert validate_dbt_vars(exported) == []
    assert validate_dbt_vars({**exported, "census_as_of_date": "2025-09-30'; --"})
