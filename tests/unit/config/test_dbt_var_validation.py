"""Exported vars are checked against the types their SQL consumers require."""

from pathlib import Path

import pytest
import yaml

from planalign_orchestrator.config.dbt_var_validation import validate_dbt_vars
from planalign_orchestrator.config.export import to_dbt_vars
from planalign_orchestrator.config.loader import SimulationConfig
from planalign_orchestrator.exceptions import ConfigurationError
from planalign_orchestrator.construction import ConstructionSpec, build_orchestrator

pytestmark = pytest.mark.fast


@pytest.mark.parametrize("value", ["", " "])
def test_blank_date_is_rejected(value):
    assert validate_dbt_vars({"auto_enrollment_hire_date_cutoff": value}) == [
        {
            "section": "engine_variables",
            "field": "auto_enrollment_hire_date_cutoff",
            "message": "must be an ISO date (YYYY-MM-DD); omit it to use the default",
        }
    ]


@pytest.mark.parametrize("value", ["2025-02-30", "yesterday", "2025-1-1"])
def test_invalid_date_is_rejected(value):
    problems = validate_dbt_vars({"plan_year_start_date": value})
    assert [problem["field"] for problem in problems] == ["plan_year_start_date"]


def test_boolean_rate_and_enum_are_checked():
    problems = validate_dbt_vars(
        {
            "auto_enrollment_enabled": "false",
            "auto_enrollment_default_deferral_rate": 1.2,
            "auto_enrollment_scope": ["other"],
            "employer_match": {"eligibility": {"allow_new_hires": "false"}},
        }
    )
    assert {problem["field"] for problem in problems} == {
        "auto_enrollment_enabled",
        "auto_enrollment_default_deferral_rate",
        "auto_enrollment_scope",
        "employer_match.eligibility.allow_new_hires",
    }


@pytest.mark.parametrize(
    ("distribution", "ok"),
    [
        ([{"age": 21, "weight": 0.5}, {"age": 35, "weight": 0.5}], True),
        ([{"age": 20, "weight": 0.1}, {"age": 35, "weight": 0.9}], False),
        ([{"weight": 1.0}], False),
        ([{"age": 22.5, "weight": 1.0}], False),
        ([{"age": float("nan"), "weight": 1.0}], False),
        ([{"age": True, "weight": 1.0}], False),
        ([{"age": 25, "weight": 0}], False),
        (["25"], False),
        ("22", False),
    ],
)
def test_new_hires_are_never_under_21(distribution: object, ok: bool) -> None:
    """#1040: plans can require at most age 21, so simulated hires start there."""
    problems = validate_dbt_vars({"new_hire_age_distribution": distribution})
    assert (problems == []) is ok


@pytest.mark.parametrize(("age", "ok"), [(18, True), (21, True), (22, False)])
def test_plan_minimum_age_is_capped_at_21(age: int, ok: bool) -> None:
    assert (validate_dbt_vars({"minimum_age": age}) == []) is ok


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("uniform", True),
        ("normal", True),
        ("deterministic", True),
        ("custom'type", False),
        ("gaussian", False),
        ("", False),
        (123, False),
    ],
)
def test_promotion_distribution_type_validation(value: object, ok: bool) -> None:
    problems = validate_dbt_vars({"promotion_distribution_type": value})
    assert (problems == []) is ok
    if not ok:
        assert [problem["field"] for problem in problems] == [
            "promotion_distribution_type"
        ]


def test_simulation_rejects_invalid_export_before_dbt(tmp_path):
    payload = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    payload.setdefault("setup", {})["plan_year_start_date"] = "2025-02-30"
    config = SimulationConfig.model_validate(payload)
    with pytest.raises(ConfigurationError, match="plan_year_start_date"):
        build_orchestrator(
            ConstructionSpec(
                config=config,
                database=tmp_path / "run.duckdb",
                reports_dir=tmp_path / "reports",
            )
        )


def test_default_config_passes_validate_dbt_vars():
    payload = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    config = SimulationConfig.model_validate(payload)
    assert validate_dbt_vars(to_dbt_vars(config)) == []


def test_checked_in_configs_export_without_var_problems():
    base = yaml.safe_load(Path("config/simulation_config.yaml").read_text())
    paths = [Path("config/simulation_config.yaml")]
    paths.extend(sorted(Path("scenarios").rglob("*.yaml")))
    paths.extend(sorted(Path("tests/fixtures").rglob("*.yaml")))
    checked = []
    for path in paths:
        payload = yaml.safe_load(path.read_text())
        if not isinstance(payload, dict) or "simulation" not in payload:
            continue  # Non-configuration fixture.
        if path.parent == Path("scenarios"):
            payload = _merge(base, payload)
        config = SimulationConfig.model_validate(payload)
        assert not validate_dbt_vars(to_dbt_vars(config)), str(path)
        checked.append(path)
    assert len(checked) >= 30


def _merge(base: dict, overrides: dict) -> dict:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@pytest.mark.parametrize(
    "bad_value",
    [
        [{"level": 1, "min_compensation": "50000", "max_compensation": 80000}],
        [{"level": "1", "min_compensation": 50000, "max_compensation": 80000}],
        [{"level": True, "min_compensation": 50000, "max_compensation": 80000}],
        [{"level": 1.5, "min_compensation": 50000, "max_compensation": 80000}],
        [{"level": 1, "min_compensation": float("nan"), "max_compensation": 80000}],
        [{"level": 1, "min_compensation": 50000, "max_compensation": float("inf")}],
        [
            {
                "level": 1,
                "min_compensation": 50000,
                "max_compensation": 80000,
                "extra": 1,
            }
        ],
        [{"level": 1, "min_compensation": 50000}],
        "not-a-list",
    ],
)
def test_job_level_compensation_rejects_invalid_entries(bad_value: object) -> None:
    problems = validate_dbt_vars({"job_level_compensation": bad_value})
    assert [p["field"] for p in problems] == ["job_level_compensation"]


def test_job_level_compensation_accepts_valid_entries_with_optional_name() -> None:
    valid = [
        {"level": 1, "min_compensation": 50000, "max_compensation": 80000},
        {
            "level": 2,
            "name": "Manager",
            "min_compensation": 80000.5,
            "max_compensation": 120000.0,
        },
    ]
    assert validate_dbt_vars({"job_level_compensation": valid}) == []


@pytest.mark.parametrize(
    "bad_tiers",
    [
        [{"employee_min": "0.0", "employee_max": 0.03, "match_rate": 1.0}],
        [{"employee_min": 0.0, "employee_max": False, "match_rate": 1.0}],
        [{"employee_min": 0.0, "employee_max": 0.03, "match_rate": float("inf")}],
        [{"employee_min": 0.0, "employee_max": None, "match_rate": 1.0}],
        [{"employee_min": 0.0, "employee_max": 0.03, "match_rate": 1.0, "extra": 0}],
        [{"employee_min": 0.0, "employee_max": 0.03}],
        "bad",
    ],
)
def test_match_tiers_rejects_invalid_entries(bad_tiers: object) -> None:
    problems = validate_dbt_vars({"match_tiers": bad_tiers})
    assert [p["field"] for p in problems] == ["match_tiers"]


@pytest.mark.parametrize(
    "bad_bands",
    [
        [
            {
                "min_years": "0",
                "max_years": 5,
                "tiers": [
                    {"employee_min": 0.0, "employee_max": 0.06, "match_rate": 1.0}
                ],
            }
        ],
        [
            {
                "min_years": 0,
                "max_years": "5",
                "tiers": [
                    {"employee_min": 0.0, "employee_max": 0.06, "match_rate": 1.0}
                ],
            }
        ],
        [
            {
                "min_years": 0,
                "max_years": None,
                "tiers": [
                    {"employee_min": 0.0, "employee_max": "0.06", "match_rate": 1.0}
                ],
            }
        ],
        [
            {
                "min_years": 0,
                "max_years": None,
                "tiers": [
                    {"employee_min": 0.0, "employee_max": 0.06, "match_rate": 1.0}
                ],
                "unexpected": 1,
            }
        ],
        "not-a-list",
    ],
)
def test_tenure_graded_bands_rejects_invalid_entries(bad_bands: object) -> None:
    problems = validate_dbt_vars({"tenure_graded_bands": bad_bands})
    assert [p["field"] for p in problems] == ["tenure_graded_bands"]


def test_tenure_graded_bands_accepts_nullable_max_years() -> None:
    valid = [
        {
            "min_years": 0,
            "max_years": 5,
            "tiers": [{"employee_min": 0.0, "employee_max": 0.03, "match_rate": 1.0}],
        },
        {
            "min_years": 5,
            "max_years": None,
            "tiers": [{"employee_min": 0.0, "employee_max": 0.06, "match_rate": 1.0}],
        },
    ]
    assert validate_dbt_vars({"tenure_graded_bands": valid}) == []


@pytest.mark.parametrize(
    ("var_name", "row"),
    [
        (
            "tenure_graded_bands",
            {
                "min_years": 2.5,
                "max_years": None,
                "tiers": [
                    {"employee_min": 0.0, "employee_max": 0.03, "match_rate": 1.0}
                ],
            },
        ),
        (
            "tenure_match_tiers",
            {"min_years": 0, "max_years": 2.5, "rate": 50, "max_deferral_pct": 6},
        ),
        (
            "points_match_tiers",
            {"min_points": 10.5, "max_points": None, "rate": 50, "max_deferral_pct": 6},
        ),
    ],
)
def test_service_and_points_bounds_must_be_whole_numbers(
    var_name: str, row: dict
) -> None:
    # Templates render these bounds as integers, so fractions are refused.
    problems = validate_dbt_vars({var_name: [row]})
    assert [p["field"] for p in problems] == [var_name]


@pytest.mark.parametrize(
    ("var_name", "valid_rows", "bad_rows"),
    [
        (
            "tenure_match_tiers",
            [{"min_years": 0, "max_years": None, "rate": 50, "max_deferral_pct": 6}],
            [{"min_years": 0, "max_years": None, "rate": "50", "max_deferral_pct": 6}],
        ),
        (
            "employer_match_graded_schedule",
            [{"min_years": 0, "max_years": 5, "rate": 50.0, "max_deferral_pct": 6.0}],
            [
                {
                    "min_years": True,
                    "max_years": 5,
                    "rate": 50.0,
                    "max_deferral_pct": 6.0,
                }
            ],
        ),
        (
            "points_match_tiers",
            [{"min_points": 0, "max_points": None, "rate": 50, "max_deferral_pct": 6}],
            [
                {
                    "min_points": 0,
                    "max_points": None,
                    "rate": 50,
                    "max_deferral_pct": "6",
                }
            ],
        ),
        (
            "employer_core_graded_schedule",
            [{"min_years": 0, "max_years": None, "rate": 3.0}],
            [{"min_years": 0, "max_years": None, "rate": float("nan")}],
        ),
        (
            "employer_core_points_schedule",
            [{"min_points": 40, "max_points": None, "rate": 4.5}],
            [{"min_points": 40, "max_points": "60", "rate": 4.5}],
        ),
        (
            "employer_core_age_schedule",
            [{"min_age": 40, "max_age": None, "rate": 5}],
            [{"min_age": 40, "max_age": None, "rate": 5, "extra": 1}],
        ),
    ],
)
def test_schedule_list_vars_validate_keys_and_numbers(
    var_name: str, valid_rows: list[dict], bad_rows: list[dict]
) -> None:
    assert validate_dbt_vars({var_name: valid_rows}) == []
    problems = validate_dbt_vars({var_name: bad_rows})
    assert [p["field"] for p in problems] == [var_name]


@pytest.mark.parametrize(
    ("var_name", "valid_val", "bad_val"),
    [
        ("promotion_level_overrides", {1: 0.15, "2": 0.2}, {"bad": 0.15}),
        ("promotion_level_overrides", {1: 0.15}, {1: "0.15"}),
        ("promotion_market_adjustments", {"eng": 1.1}, {"eng": "1.1"}),
        (
            "minimum_wage_steps",
            [{"hourly_rate": 18.5, "effective_date": "2026-07-01"}],
            [{"hourly_rate": 18.5, "effective_date": "2026-13-01"}],
        ),
        (
            "acquisitions",
            [
                {
                    "id": "acme-1",
                    "headcount": 25,
                    "effective_date": "2026-06-01",
                    "service_credit": "prior_service",
                    "plan_entry": "acquisition_date",
                    "join_year_hours_credit": "full_year",
                }
            ],
            [
                {
                    "id": "bad id!",
                    "headcount": 25,
                    "effective_date": "2026-06-01",
                }
            ],
        ),
        (
            "plan_design_assignment",
            {
                "default_plan_design_id": "plan_a",
                "rules": [
                    {
                        "type": "hire_date_cutoff",
                        "cutoff": "2026-01-01",
                        "plan_design_id": "plan_b",
                    }
                ],
            },
            {
                "default_plan_design_id": "plan_a",
                "rules": [
                    {
                        "type": "hire_date_cutoff",
                        "cutoff": "not-a-date",
                        "plan_design_id": "plan_b",
                    }
                ],
            },
        ),
        (
            "contribution_sources",
            {
                "policy": "legacy_estimate",
                "roth_fraction": "0.15",
                "roth_available": True,
                "mandatory_roth_enabled": False,
                "applicability": "unsupported",
                "employer_id": None,
                "projected_thresholds": [],
            },
            {
                "policy": "legacy_estimate",
                "roth_fraction": "not-a-number",
            },
        ),
    ],
)
def test_structured_dict_and_list_vars_are_validated(
    var_name: str, valid_val: object, bad_val: object
) -> None:
    assert validate_dbt_vars({var_name: valid_val}) == []
    problems = validate_dbt_vars({var_name: bad_val})
    assert [p["field"] for p in problems] == [var_name]


def test_employer_match_and_core_dict_validate_nested_fields() -> None:
    bad_match = {
        "apply_eligibility": "true",
        "eligibility": {"minimum_hours_annual": "1000", "minimum_tenure_years": True},
    }
    match_fields = {
        p["field"] for p in validate_dbt_vars({"employer_match": bad_match})
    }
    assert match_fields == {
        "employer_match.apply_eligibility",
        "employer_match.eligibility.minimum_hours_annual",
        "employer_match.eligibility.minimum_tenure_years",
    }

    bad_core = {
        "enabled": "yes",
        "contribution_rate": "0.03",
        "eligibility": {"allow_new_hires": "true", "minimum_hours_annual": -5},
    }
    core_fields = {
        p["field"] for p in validate_dbt_vars({"employer_core_contribution": bad_core})
    }
    assert core_fields == {
        "employer_core_contribution.enabled",
        "employer_core_contribution.contribution_rate",
        "employer_core_contribution.eligibility.allow_new_hires",
        "employer_core_contribution.eligibility.minimum_hours_annual",
    }


@pytest.mark.parametrize("token", ["{{", "}}", "{%", "%}", "{#", "#}"])
def test_jinja_delimiters_rejected_at_any_nesting_depth(token: str) -> None:
    top_problems = validate_dbt_vars({"custom_label": f"prefix {token} suffix"})
    assert any(p["field"] == "custom_label" for p in top_problems)

    nested_problems = validate_dbt_vars(
        {
            "job_level_compensation": [
                {
                    "level": 1,
                    "name": f"Level {token} 1",
                    "min_compensation": 50000,
                    "max_compensation": 80000,
                }
            ]
        }
    )
    assert any(p["field"] == "job_level_compensation[0].name" for p in nested_problems)

    deep_problems = validate_dbt_vars(
        {"nested": {"items": [{"label": f"val {token}"}]}}
    )
    assert any(p["field"] == "nested.items[0].label" for p in deep_problems)


@pytest.mark.parametrize(
    "field",
    [
        "plan_year_start_date",
        "plan_year_end_date",
        "census_as_of_date",
        "auto_enrollment_hire_date_cutoff",
        "deferral_escalation_hire_date_cutoff",
    ],
)
@pytest.mark.parametrize(
    "bad_date", ["2025-1-01", "2025-02-29", "2025-01-01; --", "2025/01/01", 20250101]
)
def test_all_date_vars_require_strict_iso_date(field: str, bad_date: object) -> None:
    problems = validate_dbt_vars({field: bad_date})
    assert [p["field"] for p in problems] == [field]


def test_plan_design_parameters_validated_for_types_and_extra_keys() -> None:
    from copy import deepcopy
    from tests.fixtures.plan_design_formula_families import relation_contract_payload

    valid_payload = relation_contract_payload()
    assert validate_dbt_vars({"plan_design_parameters": valid_payload}) == []

    bad_type = deepcopy(valid_payload)
    first_design = next(iter(bad_type))
    bad_type[first_design]["match"]["cap_percent"] = "0.04"
    assert [
        p["field"] for p in validate_dbt_vars({"plan_design_parameters": bad_type})
    ] == ["plan_design_parameters"]

    bad_extra = deepcopy(valid_payload)
    bad_extra[first_design]["match"]["unexpected_key"] = 1
    assert [
        p["field"] for p in validate_dbt_vars({"plan_design_parameters": bad_extra})
    ] == ["plan_design_parameters"]

    bad_nan = deepcopy(valid_payload)
    bad_nan[first_design]["employer_core"]["contribution_rate"] = float("nan")
    assert [
        p["field"] for p in validate_dbt_vars({"plan_design_parameters": bad_nan})
    ] == ["plan_design_parameters"]


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("service_credit", "hire_date", "prior_service or acquisition_date"),
        ("plan_entry", "next_quarter", "acquisition_date or waiting_period"),
        ("join_year_hours_credit", "partial", "none or full_year"),
    ],
)
def test_acquisition_plan_settings_name_their_allowed_values(
    key: str, value: str, message: str
) -> None:
    entry = {"id": "acme", "headcount": 5, "effective_date": "2026-10-01"}
    assert validate_dbt_vars({"acquisitions": [entry]}) == []
    problems = validate_dbt_vars({"acquisitions": [{**entry, key: value}]})
    assert len(problems) == 1
    assert f"entry 0.{key} must be {message}" in str(problems[0])
