"""#1037: every NDT says which pay each employee's HCE status came from.

Threshold is $155,000. Employees whose prior and current pay fall on opposite sides
of it show how the current-pay fallback changes HCE membership.
"""

from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.ndt_service import (
    ACPScenarioResult,
    ADPScenarioResult,
    NDTService,
    Section401a4ScenarioResult,
)
from tests.test_ndt_415 import _create_test_db, _insert_employee

pytestmark = [pytest.mark.fast]

# employee: (prior-year pay or None when missing, current pay)
CROSSING = {
    "RAISED": (100000.0, 200000.0),  # observed prior pay below: NHCE
    "NEW_HIRE": (None, 200000.0),  # no prior pay, current above: HCE by fallback
    "CUT": (200000.0, 100000.0),  # observed prior pay above: HCE
    "STEADY": (100000.0, 100000.0),  # NHCE either way
}


def _service(
    tmp_path: Path, people: dict[str, tuple[float | None, float]]
) -> NDTService:
    path = tmp_path / "provenance.duckdb"
    with duckdb.connect(str(path)) as conn:
        _create_test_db(conn)
        for employee, (prior, current) in people.items():
            if prior is not None:
                _insert_employee(conn, employee, 2024, prior, prior)
            _insert_employee(
                conn,
                employee,
                2025,
                current,
                current,
                contributions=current * 0.04,
                match_amount=current * 0.02,
                core_amount=current * 0.03,
            )
    resolver = Mock()
    resolver.resolve.return_value = ResolvedDatabasePath(path=path, source="scenario")
    return NDTService(Mock(), db_resolver=resolver)


def _run(
    service: NDTService, kind: str
) -> ADPScenarioResult | ACPScenarioResult | Section401a4ScenarioResult:
    return getattr(service, f"run_{kind}_test")(
        "w", "s", "t", 2025, include_employees=True
    )


@pytest.mark.parametrize("kind", ["adp", "acp", "401a4"])
def test_fallback_is_counted_disclosed_and_never_labelled_prior_pay(
    tmp_path: Path, kind: str
) -> None:
    result = _run(_service(tmp_path, CROSSING), kind)

    assert (result.prior_pay_observed_count, result.prior_pay_fallback_count) == (3, 1)
    assert "current compensation for 1 employee(s)" in result.test_message
    rows = {row.employee_id: row for row in result.employees}
    assert {name for name, row in rows.items() if row.is_hce} == {"NEW_HIRE", "CUT"}
    assert rows["NEW_HIRE"].hce_pay_basis == "current_pay_fallback"
    assert rows["NEW_HIRE"].prior_year_compensation is None
    assert rows["RAISED"].hce_pay_basis == "prior_year"
    assert rows["RAISED"].prior_year_compensation == pytest.approx(100000.0)


@pytest.mark.parametrize("kind", ["adp", "acp", "401a4"])
def test_first_year_classifies_everyone_on_current_pay(
    tmp_path: Path, kind: str
) -> None:
    people = {name: (None, current) for name, (_, current) in CROSSING.items()}
    result = _run(_service(tmp_path, people), kind)

    assert (result.prior_pay_observed_count, result.prior_pay_fallback_count) == (0, 4)
    assert {row.employee_id for row in result.employees if row.is_hce} == {
        "RAISED",
        "NEW_HIRE",
    }


@pytest.mark.parametrize("kind", ["adp", "acp", "401a4"])
def test_no_hce_outcome_still_reports_its_basis(tmp_path: Path, kind: str) -> None:
    people = {"STEADY": (100000.0, 100000.0), "NEW": (None, 90000.0)}
    result = _run(_service(tmp_path, people), kind)

    assert result.hce_count == 0
    assert (result.prior_pay_observed_count, result.prior_pay_fallback_count) == (1, 1)
    assert "current compensation for 1 employee(s)" in result.test_message


def test_prior_method_discloses_baseline_classified_on_current_pay(
    tmp_path: Path,
) -> None:
    result = _service(tmp_path, CROSSING).run_adp_test(
        "w", "s", "t", 2025, testing_method="prior"
    )

    assert result.testing_method == "prior"
    assert "baseline classifies 3 2024 employee(s) on current pay" in (
        result.test_message or ""
    )
