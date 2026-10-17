"""Execute production source SQL against disposable DuckDB inputs."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from jinja2 import Environment, StrictUndefined
from pydantic import ValidationError

from planalign_orchestrator.config.contribution_sources import (
    ContributionSourceSettings,
)

pytestmark = pytest.mark.fast
ROOT = Path(__file__).resolve().parents[3]


def allocate(
    *, year=2026, age=50, total=30000, wages=150001, fraction="0.15", **overrides
):
    evidence = (
        []
        if wages is None
        else [
            {
                "employee_id": "EMP",
                "employer_id": "sponsor",
                "wage_year": year - 1,
                "wages": wages,
                "basis": "confirmed",
                "provenance": "synthetic payroll",
            }
        ]
    )
    config = ContributionSourceSettings.model_validate(
        {
            "policy": "assumed_split",
            "roth_fraction": fraction,
            "mandatory_roth_enabled": True,
            "applicability": "single_employer_401k",
            "employer_id": "sponsor",
            "wage_evidence": evidence,
            **overrides,
        }
    )
    variables = {
        "simulation_year": year,
        "contribution_sources": config.model_dump(mode="json"),
    }
    template = Environment(undefined=StrictUndefined).from_string(
        (ROOT / "dbt/macros/contribution_source_allocation.sql").read_text()
        + "{{ contribution_source_allocation() }}"
    )
    sql = template.render(var=lambda name, default=None: variables.get(name, default))
    with duckdb.connect() as connection:
        connection.execute(
            "CREATE TABLE composed(employee_id VARCHAR, employee_birth_date DATE, annual_contribution_amount DECIMAL(18,2))"
        )
        birth = None if age is None else date(year - age, 12, 31)
        connection.execute("INSERT INTO composed VALUES ('EMP', ?, ?)", [birth, total])
        connection.execute(
            f"CREATE TABLE irs_limits AS SELECT * FROM read_csv_auto('{ROOT / 'dbt/seeds/config_irs_limits.csv'}') WHERE limit_year = {year}"
        )
        result = connection.execute(
            f"SELECT allocation.* FROM composed CROSS JOIN irs_limits CROSS JOIN LATERAL ({sql}) allocation"
        )
        return dict(zip([c[0] for c in result.description], result.fetchone()))


@pytest.mark.parametrize(
    "wages,status,roth",
    [
        (149999, "below_or_equal_threshold", 4500),
        (150000, "below_or_equal_threshold", 4500),
        (150001, "required", 5500),
        (0, "below_or_equal_threshold", 4500),
        (None, "unresolved_wages", 4500),
    ],
)
def test_strict_threshold_and_missing_evidence(wages, status, roth):
    result = allocate(wages=wages)
    assert result["mandatory_roth_status"] == status
    assert result["roth_contributions"] == roth
    assert result["pre_tax_contributions"] + result["roth_contributions"] == 30000
    assert result["prior_year_employer_fica_wages"] == wages


@pytest.mark.parametrize(
    "age,total,status",
    [
        (49, 25000, "ineligible_catch_up"),
        (50, 32500, "required"),
        (59, 32500, "required"),
        (60, 35750, "required"),
        (63, 35750, "required"),
        (64, 32500, "required"),
        (64, 35750, "exceeds_modeled_limit"),
        (None, 30000, "unresolved_age"),
    ],
)
def test_year_end_age_and_ordinary_super_limits(age, total, status):
    assert allocate(age=age, total=total)["mandatory_roth_status"] == status


def test_existing_roth_is_credited_not_double_counted():
    result = allocate(fraction="0.5")
    assert result["roth_contributions"] == 15000
    assert result["mandatory_roth_required"] == 5500
    assert result["mandatory_roth_reallocated"] == 0


def test_no_roth_blocks_allocation_without_changing_totals():
    result = allocate(roth_available=False, fraction="0")
    assert result["mandatory_roth_status"] == "blocked_no_roth"
    assert result["mandatory_roth_required"] == 5500
    assert result["roth_contributions"] is None
    assert result["pre_tax_contributions"] is None


@pytest.mark.parametrize("fraction", ["0", "0.15", "0.33333333", "1"])
def test_cent_reconciliation(fraction):
    result = allocate(total="123.45", fraction=fraction)
    assert result["mandatory_roth_status"] == "no_base_limit_catch_up"
    assert result["pre_tax_contributions"] + result["roth_contributions"] == Decimal(
        "123.45"
    )


def test_pre_2026_and_unknown_future_threshold():
    assert allocate(year=2025)["mandatory_roth_status"] == "not_applicable_before_2026"
    assert allocate(year=2027)["mandatory_roth_status"] == "unresolved_threshold"
    result = allocate(
        year=2027,
        projected_thresholds=[
            {
                "year": 2027,
                "threshold": 155000,
                "provenance": "analyst projection",
            }
        ],
        wages=160000,
    )
    assert result["mandatory_roth_status"] == "required_under_assumptions"
    assert result["mandatory_roth_threshold_basis"] == "projected"


def test_employer_and_year_lookup_never_infers_new_hire_wages():
    evidence = [
        {
            "employee_id": "EMP",
            "employer_id": employer,
            "wage_year": year,
            "wages": 200000,
            "basis": "confirmed",
            "provenance": "test",
        }
        for employer, year in [("other", 2025), ("sponsor", 2024)]
    ]
    assert (
        allocate(wage_evidence=evidence)["mandatory_roth_status"] == "unresolved_wages"
    )
    assert (
        allocate(wage_evidence=evidence, year=2025)["prior_year_employer_fica_wages"]
        == 200000
    )


def test_forecast_and_unsupported_scope_are_explicit():
    evidence = [
        {
            "employee_id": "EMP",
            "employer_id": "sponsor",
            "wage_year": 2025,
            "wages": 200000,
            "basis": "forecast",
            "provenance": "analyst forecast",
        }
    ]
    assert (
        allocate(wage_evidence=evidence)["mandatory_roth_status"]
        == "required_under_assumptions"
    )
    assert (
        allocate(applicability="unsupported")["mandatory_roth_status"]
        == "unsupported_applicability"
    )
    assert (
        allocate(mandatory_roth_enabled=False)["mandatory_roth_status"]
        == "not_evaluated"
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"roth_fraction": -1},
        {"roth_fraction": 2},
        {"roth_fraction": "NaN"},
        {"roth_fraction": "0.2"},
        {"roth_available": False},
        {"mandatory_roth_enabled": True},
        {
            "projected_thresholds": [
                {"year": 2026, "threshold": 145000, "provenance": "bad"}
            ]
        },
    ],
)
def test_invalid_policy_rejected(settings):
    with pytest.raises(ValidationError):
        ContributionSourceSettings.model_validate(settings)


def test_legacy_policy_is_explicit_and_reconciles():
    result = allocate(
        policy="legacy_estimate", mandatory_roth_enabled=False, total="100.01"
    )
    assert result["contribution_source_policy"] == "legacy_estimate"
    assert result["mandatory_roth_status"] == "not_evaluated"
    assert result["pre_tax_contributions"] == Decimal("85.01")
    assert result["roth_contributions"] == Decimal("15.00")


def test_duplicate_wage_and_threshold_evidence_rejected():
    wage = {
        "employee_id": "EMP",
        "employer_id": "sponsor",
        "wage_year": 2025,
        "wages": 0,
        "basis": "confirmed",
        "provenance": "confirmed no wages",
    }
    threshold = {"year": 2027, "threshold": 155000, "provenance": "forecast"}
    for settings in [
        {"wage_evidence": [wage, wage]},
        {"projected_thresholds": [threshold, threshold]},
    ]:
        with pytest.raises(ValidationError, match="Duplicate"):
            ContributionSourceSettings.model_validate(settings)
