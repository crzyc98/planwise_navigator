"""Source contracts for DC Plan participation and savings-rate trends (#641)."""

from pathlib import Path

import pytest


pytestmark = pytest.mark.fast

ROOT = Path(__file__).parents[2]
COMPONENT = ROOT / "planalign_studio" / "components" / "DCPlanAnalytics.tsx"
API_CLIENT = ROOT / "planalign_studio" / "services" / "api.ts"


def test_population_control_defaults_to_all_eligible() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "useState<DCPlanPopulation>('all_eligible')" in source
    assert "All eligible" in source
    assert "Actives only" in source
    assert "Terms only" in source
    assert 'aria-label="Eligible employee population"' in source
    assert "Active employees only" not in source


def test_participation_and_component_savings_trends_are_rendered() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "Participation Rate Trend" in source
    assert "Average Savings Rate Trend" in source
    assert 'dataKey="participationRate"' in source
    assert 'dataKey="employeeRate"' in source
    assert 'dataKey="matchRate"' in source
    assert 'dataKey="coreRate"' in source
    assert "Employee deferral" in source
    assert "Employer match" in source
    assert "Employer non-elective/core" in source


def test_empty_populations_are_gaps_with_explicit_no_data_copy() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "year.total_eligible_count > 0" in source
    assert "year.total_compensation > 0" in source
    assert (
        "participationRate: hasEligiblePopulation ? year.participation_rate : null"
        in source
    )
    assert "No eligible employees are available" in source
    assert "No eligible compensation is available" in source


def test_api_client_sends_explicit_population_parameter() -> None:
    source = API_CLIENT.read_text(encoding="utf-8")

    assert "export type DCPlanPopulation" in source
    assert "if (population) params.set('population', population)" in source


def test_each_trend_has_a_spreadsheet_ready_copy_action() -> None:
    source = COMPONENT.read_text(encoding="utf-8")

    assert "useCopyToClipboard" in source
    assert "Copy participation trend" in source
    assert "Copy savings trend" in source
    assert "Enrolled employees" in source
    assert "Eligible employees" in source
    assert "Employee deferral rate" in source
    assert "Employer match rate" in source
    assert "Employer non-elective/core rate" in source
    assert "Total savings rate" in source
    assert "['Average'" in source
    assert "row.employeeRate + (row.matchRate ?? 0) + (row.coreRate ?? 0)" in source
