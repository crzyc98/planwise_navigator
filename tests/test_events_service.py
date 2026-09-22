"""Fast contract tests for the event explorer service."""

from pathlib import Path

import pytest

from planalign_api.services.database_path_resolver import ResolvedDatabasePath
from planalign_api.services.events_service import EventExplorerService

pytest_plugins = ["tests.fixtures.database"]


class _Resolver:
    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve(self, workspace_id: str, scenario_id: str) -> ResolvedDatabasePath:
        return ResolvedDatabasePath(path=self.path, source="run", run_id="run-123")


@pytest.fixture
def service(events_explorer_db: Path) -> EventExplorerService:
    return EventExplorerService(object(), _Resolver(events_explorer_db))  # type: ignore[arg-type]


@pytest.mark.fast
def test_event_explorer_composes_predicates(service: EventExplorerService) -> None:
    result = service.list_events(
        "ws",
        "scenario",
        simulation_year=2026,
        event_category="PLAN",
        employee_id="emp_a",
    )

    assert result.total == 1
    assert [event.event_id for event in result.events] == ["evt-a-escalate"]


@pytest.mark.fast
def test_event_explorer_total_is_independent_of_page_size(
    service: EventExplorerService,
) -> None:
    result = service.list_events("ws", "scenario", page_size=2)

    assert result.total == 8
    assert len(result.events) == 2


@pytest.mark.fast
def test_event_explorer_ordering_is_stable(service: EventExplorerService) -> None:
    first = service.list_events("ws", "scenario")
    second = service.list_events("ws", "scenario")

    assert [event.event_id for event in first.events] == [
        "evt-a-elig",
        "evt-a-hire",
        "evt-b-hire",
        "evt-a-enroll",
        "evt-b-raise",
        "evt-a-escalate",
        "evt-c-term",
        "evt-a-raise",
    ]
    assert first.events == second.events


@pytest.mark.fast
def test_event_explorer_without_filters_returns_all(
    service: EventExplorerService,
) -> None:
    result = service.list_events("ws", "scenario")

    assert result.total == 8
    assert len(result.events) == 8
    assert result.run_id == "run-123"
    assert result.database_source == "run"
