"""Execute production source SQL against disposable DuckDB inputs."""

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pytest
from jinja2 import Environment, StrictUndefined
from pydantic import ValidationError

from planalign_orchestrator.config.contribution_sources import (
    ContributionSourceSettings,
)
from planalign_orchestrator.config import load_simulation_config, to_dbt_vars
from planalign_orchestrator.config.wage_evidence import write_wage_evidence
from planalign_orchestrator.dbt_runner import DbtRunner
from planalign_orchestrator.run_metadata import compute_config_fingerprint

pytestmark = pytest.mark.fast
ROOT = Path(__file__).resolve().parents[3]


def allocate(
    *,
    year=2026,
    age=50,
    total=30000,
    wages=150001,
    fraction="0.15",
    hire_year=None,
    current_age=None,
    seed_threshold=None,
    no_file=False,
    **overrides,
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
    with TemporaryDirectory() as directory:
        variables = {
            "simulation_year": year,
            "contribution_sources": config.model_dump(
                mode="json", exclude={"wage_evidence"}
            ),
            "contribution_wage_evidence_path": (
                ""
                if no_file
                else str(write_wage_evidence(config, Path(directory) / "unit.duckdb"))
            ),
        }
        template = Environment(undefined=StrictUndefined).from_string(
            (ROOT / "dbt/macros/contribution_source_allocation.sql").read_text()
            + "{{ contribution_source_allocation() }}"
        )
        sql = template.render(
            var=lambda name, default=None: variables.get(name, default)
        )
        with duckdb.connect() as connection:
            connection.execute(
                "CREATE TABLE composed(employee_id VARCHAR, employee_birth_date DATE, employee_hire_date DATE, current_age INTEGER, annual_contribution_amount DECIMAL(18,2))"
            )
            birth = None if age is None else date(year - age, 12, 31)
            connection.execute(
                "INSERT INTO composed VALUES ('EMP', ?, ?, ?, ?)",
                [birth, date(hire_year or year - 1, 1, 1), current_age, total],
            )
            connection.execute(
                f"CREATE TABLE irs_limits AS SELECT * FROM read_csv_auto('{ROOT / 'dbt/seeds/config_irs_limits.csv'}') ORDER BY CASE WHEN limit_year = {year} THEN 0 ELSE 1 END, ABS(limit_year - {year}) LIMIT 1"
            )
            if seed_threshold is not None:
                connection.execute(
                    "UPDATE irs_limits SET roth_catch_up_wage_threshold = ?",
                    [seed_threshold],
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


def test_missing_evidence_file_uses_empty_schema():
    result = allocate(wages=None, no_file=True)
    assert result["mandatory_roth_status"] == "unresolved_wages"


def test_threshold_comes_from_selected_irs_seed_row():
    result = allocate(wages=150001, seed_threshold=160000)
    assert result["mandatory_roth_status"] == "below_or_equal_threshold"
    assert result["mandatory_roth_threshold"] == 160000
    assert allocate(year=2036)["mandatory_roth_rule_version"] == "sec603_2035_v1"


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


def test_missing_birth_date_uses_current_age():
    result = allocate(age=None, current_age=60, total=35750)
    assert result["source_year_end_age"] == 60
    assert result["mandatory_roth_status"] == "required"


@pytest.mark.parametrize(
    "age,total,expected_disallowed,fraction",
    [(49, 30000, 5500, "0.15"), (64, 35750, 3250, "0.15"), (64, 35750, 3250, "1")],
)
def test_invalid_catch_up_keeps_allowed_sources(
    age, total, expected_disallowed, fraction
):
    result = allocate(age=age, total=total, fraction=fraction)
    assert result["disallowed_catch_up_contributions"] == expected_disallowed
    assert result["pre_tax_contributions"] >= 24500
    assert (
        result["pre_tax_contributions"]
        + result["roth_contributions"]
        + result["disallowed_catch_up_contributions"]
        == total
    )


def test_existing_roth_is_credited_not_double_counted():
    result = allocate(fraction="0.5")
    assert result["roth_contributions"] == 15000
    assert result["mandatory_roth_required"] == 5500
    assert result["mandatory_roth_reallocated"] == 0


def test_no_roth_blocks_allocation_without_changing_totals():
    result = allocate(roth_available=False, fraction="0")
    assert result["mandatory_roth_status"] == "blocked_no_roth"
    assert result["mandatory_roth_required"] == 5500
    assert result["roth_contributions"] == 0
    assert result["pre_tax_contributions"] == 24500
    assert result["disallowed_catch_up_contributions"] == 5500


@pytest.mark.parametrize("fraction", ["0", "0.15", "0.33333333", "1"])
def test_cent_reconciliation(fraction):
    result = allocate(total="123.45", fraction=fraction)
    assert result["mandatory_roth_status"] == "no_base_limit_catch_up"
    assert result["pre_tax_contributions"] + result["roth_contributions"] == Decimal(
        "123.45"
    )


def test_pre_2026_and_unknown_future_threshold():
    prior = allocate(year=2025)
    assert prior["mandatory_roth_status"] == "not_applicable_before_2026"
    assert prior["mandatory_roth_rule_version"] == "not_applicable_before_2026"
    assert allocate(year=2027)["mandatory_roth_status"] == "required_under_assumptions"
    assert allocate(year=2028)["mandatory_roth_rule_version"] == "sec603_2028_v1"
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


def test_employer_year_and_new_hire_structural_wages():
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
    hired = allocate(wage_evidence=evidence, hire_year=2026)
    assert hired["mandatory_roth_status"] == "below_or_equal_threshold"
    assert hired["prior_year_employer_fica_wages"] == 0
    assert hired["prior_year_wage_basis"] == "structural"
    rehire = allocate(
        wage_evidence=[{**evidence[0], "employer_id": "sponsor"}], hire_year=2026
    )
    assert rehire["mandatory_roth_status"] == "required"
    assert rehire["prior_year_wage_basis"] == "confirmed"
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
    assert result["disallowed_catch_up_contributions"] == 0


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


def test_dbt_vars_do_not_grow_with_wage_evidence(tmp_path: Path) -> None:
    fixture = ROOT / "tests/fixtures/edge_config/auto_escalation_low_cap.yaml"
    config = load_simulation_config(fixture, env_overrides=False)
    record = {
        "employee_id": "EMP_0",
        "employer_id": "sponsor",
        "wage_year": 2025,
        "wages": 150001,
        "basis": "confirmed",
        "provenance": "payroll",
    }
    runner = DbtRunner(threads=1)
    lengths = []
    fingerprints = []
    for count in (1, 1000):
        config.contribution_sources = ContributionSourceSettings.model_validate(
            {
                "wage_evidence": [
                    {**record, "employee_id": f"EMP_{i}"} for i in range(count)
                ]
            }
        )
        fingerprints.append(compute_config_fingerprint(config))
        variables = to_dbt_vars(config, database_path=tmp_path / "source.duckdb")
        command = runner._build_command(["run"], dbt_vars=variables)
        payload = command[command.index("--vars") + 1]
        lengths.append(len(payload.encode()))
        assert "EMP_0" not in payload
        assert "wage_evidence" not in json.dumps(variables["contribution_sources"])
        with duckdb.connect() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM read_parquet(?)",
                    [variables["contribution_wage_evidence_path"]],
                ).fetchone()[0]
                == count
            )
    assert lengths[0] == lengths[1]
    assert fingerprints[0] != fingerprints[1]
    changed = config.contribution_sources.model_dump(mode="json")
    changed["wage_evidence"][0]["wages"] = "200000.00"
    config.contribution_sources = ContributionSourceSettings.model_validate(changed)
    assert compute_config_fingerprint(config) != fingerprints[1]
