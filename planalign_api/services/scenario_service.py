"""Scenario service - thin wrapper around storage."""

from typing import Any, Dict, List, Optional

from ..models.scenario import Scenario, ScenarioCreate, ScenarioUpdate
from ..storage.workspace_storage import WorkspaceStorage


class ScenarioService:
    """Service for scenario operations."""

    def __init__(self, storage: WorkspaceStorage):
        self.storage = storage

    def list_scenarios(self, workspace_id: str) -> List[Scenario]:
        """List all scenarios in a workspace."""
        return self.storage.list_scenarios(workspace_id)

    def get_scenario(
        self, workspace_id: str, scenario_id: str
    ) -> Optional[Scenario]:
        """Get a scenario by ID."""
        return self.storage.get_scenario(workspace_id, scenario_id)

    def create_scenario(
        self, workspace_id: str, data: ScenarioCreate
    ) -> Optional[Scenario]:
        """Create a new scenario in a workspace."""
        return self.storage.create_scenario(workspace_id, data)

    def update_scenario(
        self, workspace_id: str, scenario_id: str, data: ScenarioUpdate
    ) -> Optional[Scenario]:
        """Update an existing scenario."""
        return self.storage.update_scenario(workspace_id, scenario_id, data)

    def delete_scenario(self, workspace_id: str, scenario_id: str) -> bool:
        """Delete a scenario."""
        return self.storage.delete_scenario(workspace_id, scenario_id)

    def get_merged_config(
        self, workspace_id: str, scenario_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get merged configuration (base + overrides)."""
        return self.storage.get_merged_config(workspace_id, scenario_id)

    def duplicate_scenario(
        self,
        workspace_id: str,
        scenario_id: str,
        new_name: str,
    ) -> Optional[Scenario]:
        """Duplicate a scenario with a new name."""
        original = self.storage.get_scenario(workspace_id, scenario_id)
        if not original:
            return None

        return self.storage.create_scenario(
            workspace_id,
            ScenarioCreate(
                name=new_name,
                description=f"Copy of {original.name}",
                config_overrides=original.config_overrides,
            ),
        )
