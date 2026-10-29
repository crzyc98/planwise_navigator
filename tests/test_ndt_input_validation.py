"""Regression for missing evidence incorrectly producing NDT passes."""

from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from planalign_api.services.ndt_service import NDTService
from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from tests.test_ndt_415 import _create_test_db, _insert_employee


@pytest.mark.parametrize(
    "kind,field",
    [
        ("adp", "prorated_annual_contributions"),
        ("adp", "prorated_annual_compensation"),
        ("acp", "employer_match_amount"),
        ("acp", "employee_after_tax_contributions"),
        ("415", "employer_core_amount"),
        ("415", "current_compensation"),
        ("401a4", "employer_core_amount"),
    ],
)
@pytest.mark.parametrize("invalid", [None, -1.0, float("nan")])
def test_invalid_used_operand_cannot_pass(
    tmp_path: Path, kind: str, field: str, invalid: float | None
) -> None:
    path = tmp_path / "synthetic.duckdb"
    with duckdb.connect(str(path)) as conn:
        _create_test_db(conn)
        for year in (2024, 2025):
            for employee, pay in [("H", 200000), ("N", 100000)]:
                _insert_employee(
                    conn,
                    employee,
                    year,
                    pay,
                    pay,
                    contributions=4000,
                    match_amount=2000,
                    core_amount=1000,
                )
        conn.execute(
            "ALTER TABLE fct_workforce_snapshot ADD COLUMN employee_after_tax_contributions DOUBLE DEFAULT 0"
        )
        conn.execute(
            f"UPDATE fct_workforce_snapshot SET {field}=? WHERE employee_id='H' AND simulation_year=2025",
            [invalid],
        )
    resolver = Mock()
    resolver.resolve.return_value = ResolvedDatabasePath(path=path, source="scenario")
    result = getattr(NDTService(Mock(), db_resolver=resolver), f"run_{kind}_test")(
        "w", "s", "Synthetic", 2025
    )
    assert result.test_result == "error"
    assert field in result.test_message
    assert "1 eligible row(s)" in result.test_message


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("duplicate", "duplicate or missing employee/year"),
        ("designs", "multiple plan_design_id"),
        ("null_design", "missing plan_design_id"),
        ("prior_null", "prorated_annual_contributions"),
        ("prior_negative", "HCE classification compensation"),
        ("null_eligibility", "unknown eligibility"),
        ("invalid_eligibility", "unknown eligibility"),
    ],
)
@pytest.mark.parametrize("method", ["current", "prior"])
def test_population_and_history_guard(
    tmp_path: Path, mutation: str, expected: str, method: str
) -> None:
    if mutation == "prior_null" and method == "current":
        pytest.skip("Prior deferrals are not an input to current-year ADP")
    path = tmp_path / "history.duckdb"
    with duckdb.connect(str(path)) as conn:
        _create_test_db(conn)
        for year in (2024, 2025):
            for employee, pay in [("H", 200000), ("N", 100000)]:
                _insert_employee(
                    conn,
                    employee,
                    year,
                    pay,
                    pay,
                    contributions=4000,
                    match_amount=2000,
                    core_amount=1000,
                )
        if mutation == "duplicate":
            conn.execute(
                "INSERT INTO fct_workforce_snapshot SELECT * FROM fct_workforce_snapshot WHERE employee_id='N' AND simulation_year=2024"
            )
        elif mutation == "designs":
            conn.execute(
                "ALTER TABLE fct_workforce_snapshot ADD COLUMN plan_design_id VARCHAR DEFAULT 'A'"
            )
            conn.execute(
                "UPDATE fct_workforce_snapshot SET plan_design_id='B' WHERE employee_id='N'"
            )
        elif mutation == "null_design":
            conn.execute(
                "ALTER TABLE fct_workforce_snapshot ADD COLUMN plan_design_id VARCHAR"
            )
        elif mutation in {"null_eligibility", "invalid_eligibility"}:
            conn.execute(
                "UPDATE fct_workforce_snapshot SET current_eligibility_status=? WHERE employee_id='H' AND simulation_year=2025",
                [None if mutation == "null_eligibility" else "typo"],
            )
        elif mutation == "prior_null":
            conn.execute(
                "UPDATE fct_workforce_snapshot SET prorated_annual_contributions=NULL WHERE employee_id='N' AND simulation_year=2024"
            )
        else:
            conn.execute(
                "UPDATE fct_workforce_snapshot SET current_compensation=-1 WHERE employee_id='H' AND simulation_year=2024"
            )
    resolver = Mock()
    resolver.resolve.return_value = ResolvedDatabasePath(path=path, source="scenario")
    result = NDTService(Mock(), db_resolver=resolver).run_adp_test(
        "w", "s", "Synthetic", 2025, testing_method=method
    )
    assert result.test_result == "error"
    assert expected in result.test_message
    # A real second connection can write after the error; the service released its handle.
    with duckdb.connect(str(path)) as conn:
        conn.execute("CREATE TABLE connection_released (ok BOOLEAN)")
