"""Consistent run-selection headers for scenario-scoped API reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..storage.workspace_storage import WorkspaceStorage
from .current_result import resolve_scenario_read_context

RUN_WARNING_HEADER = "X-PlanAlign-Run-Warning"
ACTIVE_RUN_HEADER = "X-PlanAlign-Active-Run-Id"
RESULT_RUN_HEADER = "X-PlanAlign-Result-Run-Id"
RUN_CONSISTENCY_HEADERS = (
    RUN_WARNING_HEADER,
    ACTIVE_RUN_HEADER,
    RESULT_RUN_HEADER,
)


@dataclass(frozen=True)
class ScenarioReadRef:
    workspace_id: str
    scenario_id: str


def _format_ids(values: list[tuple[str, str]], *, multiple: bool) -> str | None:
    if not values:
        return None
    ordered = sorted(values)
    if not multiple:
        return ordered[0][1]
    return ",".join(f"{scenario_id}={run_id}" for scenario_id, run_id in ordered)


def build_scenario_read_headers(
    storage: WorkspaceStorage, refs: Iterable[ScenarioReadRef]
) -> dict[str, str]:
    """Resolve active/latest-success context without changing response bodies."""
    unique = sorted(set(refs), key=lambda item: (item.scenario_id, item.workspace_id))
    active: list[tuple[str, str]] = []
    results: list[tuple[str, str]] = []
    for ref in unique:
        context = resolve_scenario_read_context(
            storage._scenario_path(ref.workspace_id, ref.scenario_id)
        )
        if context.active_run_id is not None:
            active.append((ref.scenario_id, str(context.active_run_id)))
        if context.result_run_id is not None:
            results.append((ref.scenario_id, str(context.result_run_id)))

    headers: dict[str, str] = {}
    if active:
        headers[RUN_WARNING_HEADER] = "run_in_progress"
    active_value = _format_ids(active, multiple=len(unique) > 1)
    result_value = _format_ids(results, multiple=len(unique) > 1)
    if active_value:
        headers[ACTIVE_RUN_HEADER] = active_value
    if result_value:
        headers[RESULT_RUN_HEADER] = result_value
    return headers


def has_selected_result(
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario_id: str,
    scenario_status: str,
) -> bool:
    """Accept managed latest-success results or a completed legacy scenario."""
    context = resolve_scenario_read_context(
        storage._scenario_path(workspace_id, scenario_id)
    )
    return context.database_path is not None or scenario_status == "completed"
