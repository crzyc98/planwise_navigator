"""Regression contracts for issues #655, #665, and #666."""

from pathlib import Path

import pytest
import yaml


pytestmark = pytest.mark.fast

ROOT = Path(__file__).resolve().parents[2]


def test_workforce_proration_uses_null_safe_event_exclusion() -> None:
    source = (
        ROOT / "dbt/models/intermediate/int_workforce_state_accumulator.sql"
    ).read_text(encoding="utf-8")
    cte = source.split("prorated_without_events AS (", maxsplit=1)[1].split(
        "prorated_compensation AS (", maxsplit=1
    )[0]

    assert "WHERE NOT EXISTS (" in cte
    assert "WHERE c.employee_id = w.employee_id" in cte
    assert "NOT IN" not in cte


def test_enrollment_events_are_scenario_scoped() -> None:
    enrollment = (ROOT / "dbt/models/intermediate/int_enrollment_events.sql").read_text(
        encoding="utf-8"
    )
    current_year = (
        ROOT / "dbt/models/intermediate/int_current_year_events.sql"
    ).read_text(encoding="utf-8")
    enrollment_union = current_year.split(
        "FROM {{ ref('int_enrollment_events') }}", maxsplit=1
    )[0].rsplit("SELECT", maxsplit=1)[1]

    assert "unique_key=['scenario_id'," in enrollment
    assert "DELETE FROM {{ this }} WHERE scenario_id =" in enrollment
    assert "AS scenario_id" in enrollment
    assert "scenario_id," in enrollment_union
    assert "'{{ sid }}' AS scenario_id" not in enrollment_union
    assert "WHERE scenario_id = '{{ sid }}'" in current_year


@pytest.mark.parametrize(
    "relative_path",
    [
        "dbt/models/intermediate/events/int_deferral_rate_escalation_events.sql",
        "dbt/models/intermediate/events/int_deferral_match_response_events.sql",
        "dbt/macros/events/events_enrollment_sql.sql",
        "dbt/macros/duckdb_workforce_optimizations.sql",
    ],
)
def test_enrollment_event_consumers_are_scenario_scoped(relative_path: str) -> None:
    source = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "scenario_id = '{{ var('scenario_id', 'default') }}'" in source


def test_event_and_enrollment_grain_is_declared_in_schema() -> None:
    marts = yaml.safe_load(
        (ROOT / "dbt/models/marts/schema.yml").read_text(encoding="utf-8")
    )
    intermediate = yaml.safe_load(
        (ROOT / "dbt/models/intermediate/schema.yml").read_text(encoding="utf-8")
    )
    yearly_events = next(
        model for model in marts["models"] if model["name"] == "fct_yearly_events"
    )
    enrollment = next(
        model
        for model in intermediate["models"]
        if model["name"] == "int_enrollment_events"
    )
    event_id = next(
        column for column in yearly_events["columns"] if column["name"] == "event_id"
    )
    scenario_id = next(
        column for column in enrollment["columns"] if column["name"] == "scenario_id"
    )

    assert set(event_id["data_tests"]) == {"not_null", "unique"}
    assert "not_null" in scenario_id["data_tests"]


def test_vesting_refresh_only_reloads_route_scoped_data() -> None:
    source = (ROOT / "planalign_studio/components/VestingAnalysis.tsx").read_text(
        encoding="utf-8"
    )
    handler = source.split("const handleRefresh = () => {", maxsplit=1)[1].split(
        "};", maxsplit=1
    )[0]

    assert "fetchSchedules();" in handler
    assert "fetchScenarios(selectedWorkspaceId);" in handler
    assert "fetchWorkspaces" not in handler
