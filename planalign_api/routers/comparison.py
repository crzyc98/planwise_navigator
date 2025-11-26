"""Scenario comparison endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import APISettings, get_settings
from ..models.comparison import (
    ComparisonResponse,
    DeltaValue,
    EventComparisonMetric,
    WorkforceComparisonYear,
    WorkforceMetrics,
)
from ..storage.workspace_storage import WorkspaceStorage
from ..services.comparison_service import ComparisonService

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


def get_comparison_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> ComparisonService:
    """Dependency to get comparison service."""
    return ComparisonService(storage)


@router.get("/{workspace_id}/comparison", response_model=ComparisonResponse)
async def compare_scenarios(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated scenario IDs"),
    baseline: str = Query(..., description="Baseline scenario ID"),
    storage: WorkspaceStorage = Depends(get_storage),
    comparison_service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonResponse:
    """
    Compare multiple scenarios against a baseline.

    Returns pre-calculated deltas for workforce metrics and events.
    """
    # Verify workspace exists
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    # Parse scenario IDs
    scenario_ids = [s.strip() for s in scenarios.split(",")]

    # Verify baseline is in the list
    if baseline not in scenario_ids:
        scenario_ids.insert(0, baseline)

    # Verify all scenarios exist and are completed
    scenario_names = {}
    for scenario_id in scenario_ids:
        scenario = storage.get_scenario(workspace_id, scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )
        if scenario.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scenario {scenario_id} has not completed successfully",
            )
        scenario_names[scenario_id] = scenario.name

    # Generate comparison
    comparison = comparison_service.compare_scenarios(
        workspace_id, scenario_ids, baseline
    )

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate comparison",
        )

    comparison.scenario_names = scenario_names
    return comparison
