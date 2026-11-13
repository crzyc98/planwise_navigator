"""Workspace service - thin wrapper around storage."""

from copy import deepcopy
from typing import Any, Dict, List, Optional

from ..models.workspace import (
    Workspace,
    WorkspaceCreate,
    WorkspaceSummary,
    WorkspaceUpdate,
)
from ..storage.workspace_storage import WorkspaceStorage

# Built-in defaults mirroring routers/workspaces.py:get_default_config, used when
# no default_config is supplied to create_workspace().
_BUILTIN_DEFAULT_CONFIG: Dict[str, Any] = {
    "simulation": {
        "start_year": 2025,
        "end_year": 2027,
        "random_seed": 42,
        "target_growth_rate": 0.03,
    },
    "compensation": {
        "cola_rate": 0.02,
        "merit_budget": 0.035,
    },
    "workforce": {
        "total_termination_rate": 0.12,
    },
    "enrollment": {
        "auto_enrollment": {"enabled": True},
    },
    "employer_match": {
        "active_formula": "simple_match",
        "formulas": {
            "simple_match": {
                "name": "Simple Match",
                "type": "simple",
                "match_rate": 0.50,
                "max_match_percentage": 0.06,
            },
        },
        "tenure_match_tiers": [],
        "points_match_tiers": [],
        "tenure_graded_bands": [],
    },
    "employer_core_contribution": {
        "enabled": True,
        "status": "flat",
        "contribution_rate": 0.03,
    },
}


def with_raise_budget(config: Dict[str, Any]) -> Dict[str, Any]:
    """Start a new workspace on one raise budget, at the same merit-plus-COLA level.

    Only new workspaces get this. Saved workspaces and scenario files keep merit
    and COLA, because a budget in shared defaults would silently override them.
    """
    merged = deepcopy(config)
    compensation = merged.setdefault("compensation", {})
    if compensation.get("raise_budget") is None:
        total = float(compensation.get("merit_budget", 0.035)) + float(
            compensation.get("cola_rate", 0.02)
        )
        compensation["raise_budget"] = round(total, 6)
    return merged


# Studio's default hire pay ranges, the same as dbt/seeds/config_job_levels.csv.
_DEFAULT_PAY_SCALE: List[Dict[str, Any]] = [
    {"level": 1, "name": "Staff", "min_compensation": 56000, "max_compensation": 80000},
    {
        "level": 2,
        "name": "Manager",
        "min_compensation": 81000,
        "max_compensation": 120000,
    },
    {
        "level": 3,
        "name": "Sr Manager",
        "min_compensation": 121000,
        "max_compensation": 160000,
    },
    {
        "level": 4,
        "name": "Director",
        "min_compensation": 161000,
        "max_compensation": 300000,
    },
    {"level": 5, "name": "VP", "min_compensation": 275000, "max_compensation": 500000},
]


def with_shared_pay_scale(config: Dict[str, Any]) -> Dict[str, Any]:
    """Start a new workspace on the shared pay scale, which horizon calibration needs.

    Only new workspaces get this (#1075). Saved workspaces and scenario files keep
    their setting, because turning it on changes how incumbents and hires are paid.
    """
    merged = deepcopy(config)
    new_hire = merged.setdefault("new_hire", {})
    if new_hire.get("shared_pay_scale") is None:
        new_hire["shared_pay_scale"] = True
        new_hire.setdefault("job_level_compensation", deepcopy(_DEFAULT_PAY_SCALE))
    return merged


NEW_WORKSPACE_YEARS = (2026, 2030)


def with_new_workspace_years(config: Dict[str, Any]) -> Dict[str, Any]:
    """Start a new workspace on the 2026-2030 horizon.

    Only new workspaces get this. Saved workspaces and scenario files keep their years.
    """
    merged = deepcopy(config)
    simulation = merged.setdefault("simulation", {})
    simulation["start_year"], simulation["end_year"] = NEW_WORKSPACE_YEARS
    return merged


def new_workspace_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """The Studio defaults a new workspace starts from, on top of the shared config."""
    return with_new_workspace_years(with_shared_pay_scale(with_raise_budget(config)))


class WorkspaceService:
    """Service for workspace operations."""

    def __init__(self, storage: WorkspaceStorage):
        self.storage = storage

    def list_workspaces(self) -> List[WorkspaceSummary]:
        """List all workspaces."""
        return self.storage.list_workspaces()

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get a workspace by ID."""
        return self.storage.get_workspace(workspace_id)

    def create_workspace(
        self, data: WorkspaceCreate, default_config: Optional[Dict[str, Any]] = None
    ) -> Workspace:
        """Create a new workspace."""
        return self.storage.create_workspace(
            data, new_workspace_defaults(default_config or _BUILTIN_DEFAULT_CONFIG)
        )

    def update_workspace(
        self, workspace_id: str, data: WorkspaceUpdate
    ) -> Optional[Workspace]:
        """Update an existing workspace."""
        return self.storage.update_workspace(
            workspace_id,
            name=data.name,
            description=data.description,
            base_config=data.base_config,
            lifecycle=data.lifecycle,
        )

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace and all its scenarios."""
        return self.storage.delete_workspace(workspace_id)

    def get_base_config(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get base configuration for a workspace."""
        workspace = self.storage.get_workspace(workspace_id)
        if workspace:
            return workspace.base_config
        return None

    def update_base_config(
        self, workspace_id: str, config: Dict[str, Any]
    ) -> Optional[Workspace]:
        """Update base configuration for a workspace."""
        return self.storage.update_workspace(workspace_id, base_config=config)
