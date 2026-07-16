"""Fast contract tests for the employee timeline service."""

from pathlib import Path

import pytest

from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.timeline_service import TimelineService

pytest_plugins = ["tests.fixtures.database"]


class _Resolver:
    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve(self, workspace_id: str, scenario_id: str) -> ResolvedDatabasePath:
        return ResolvedDatabasePath(path=self.path, source="scenario")


@pytest.fixture
def service(timeline_db: Path) -> TimelineService:
    return TimelineService(object(), _Resolver(timeline_db))  # type: ignore[arg-type]


@pytest.mark.fast
def test_timeline_merges_orders_and_paginates_stably(service: TimelineService) -> None:
    first = service.get_timeline("ws", "scenario", "  emp_a  ", years=2)
    second = service.get_timeline("ws", "scenario", "EMP_A", years=2)

    assert first.employee_id == "EMP_A"
    assert first.available_years == [2025, 2026, 2027]
    assert [year.simulation_year for year in first.years] == [2025, 2026]
    assert [event.event_id for year in first.years for event in year.events] == [
        "e-hire",
        "e-elig",
        "e-enroll",
        "m-2025",
        "e-escalate",
        "e-raise",
        "m-2026",
    ]
    assert first.years == second.years
    assert first.years[0].state is not None
    assert first.employee is not None
    assert first.employee.employee_ssn == "***-**-0001"


@pytest.mark.fast
def test_event_only_and_snapshot_only_years(service: TimelineService) -> None:
    event_only = service.get_timeline("ws", "scenario", "EMP_A", start_year=2027)
    snapshot_only = service.get_timeline("ws", "scenario", "emp_b")

    assert event_only.years[0].state is None
    assert snapshot_only.employee is not None
    assert all(
        not year.events and year.state is not None for year in snapshot_only.years
    )


@pytest.mark.fast
def test_unknown_employee_has_domain_not_found_response(
    service: TimelineService,
) -> None:
    result = service.get_timeline("ws", "scenario", "missing")
    assert result.employee is None
    assert result.available_years == []
    assert result.years == []


@pytest.mark.fast
def test_search_composes_filters_and_paginates(service: TimelineService) -> None:
    autocomplete = service.search_employees("ws", "scenario", q=" emp_")
    filtered = service.search_employees(
        "ws",
        "scenario",
        status="terminated",
        year=2026,
        enrolled=False,
        has_escalations=False,
        page=1,
        page_size=1,
    )

    assert {row.employee_id for row in autocomplete.results} == {"EMP_A", "EMP_B"}
    assert filtered.total == 1
    assert filtered.results[0].employee_id == "EMP_B"
    assert filtered.page_size == 1
