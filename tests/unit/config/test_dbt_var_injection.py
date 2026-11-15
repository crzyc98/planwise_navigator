"""dbt vars rendered inside SQL string literals must be validated or escaped."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from planalign_api.models.bands import Band
from planalign_api.models.studio_config import StudioDCPlanConfig
from planalign_orchestrator.config.dbt_var_validation import validate_dbt_vars

pytestmark = pytest.mark.fast
DBT = Path(__file__).resolve().parents[3] / "dbt"


@pytest.mark.parametrize(
    "value", ["simple", "tiered", "stretch", "safe_harbor", "qaca"]
)
def test_known_match_templates_pass(value: str) -> None:
    assert not validate_dbt_vars({"match_template": value})
    assert StudioDCPlanConfig(match_template=value).match_template == value


def test_unknown_match_template_rejected() -> None:
    assert validate_dbt_vars({"match_template": "x' || 1 --"})
    with pytest.raises(ValidationError):
        StudioDCPlanConfig(match_template="x' || 1 --")


@pytest.mark.parametrize("value", ["01-01", "07-15", "02-29"])
def test_valid_escalation_month_day_passes(value: str) -> None:
    assert not validate_dbt_vars({"deferral_escalation_effective_mmdd": value})


@pytest.mark.parametrize("value", ["13-01", "02-30", "1-1", "01-01'", 101, None])
def test_invalid_escalation_month_day_rejected(value: object) -> None:
    assert validate_dbt_vars({"deferral_escalation_effective_mmdd": value})


def test_band_label_rejects_quotes() -> None:
    fields = {"band_id": 1, "min_value": 0, "max_value": 25, "display_order": 1}
    assert Band(band_label="< 25", **fields).band_label == "< 25"
    with pytest.raises(ValidationError):
        Band(band_label="x' END --", **fields)


@pytest.mark.parametrize(
    "path",
    [
        "macros/bands/assign_age_band.sql",
        "macros/bands/assign_tenure_band.sql",
        "models/intermediate/int_employee_match_calculations.sql",
    ],
)
def test_sql_literals_escape_quotes(path: str) -> None:
    source = (DBT / path).read_text()
    for var in ("row['band_label'] }}", "match_template }}"):
        assert var not in source
