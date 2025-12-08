"""Filesystem storage operations for workspaces and scenarios."""

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..config import get_settings
from ..models.workspace import Workspace, WorkspaceCreate, WorkspaceSummary
from ..models.scenario import Scenario, ScenarioCreate


class WorkspaceStorage:
    """Handles filesystem operations for workspaces and scenarios."""

    def __init__(self, workspaces_root: Optional[Path] = None):
        """Initialize storage with workspace root directory."""
        self.workspaces_root = workspaces_root or get_settings().workspaces_root
        self.workspaces_root.mkdir(parents=True, exist_ok=True)

    def _workspace_path(self, workspace_id: str) -> Path:
        """Get path to workspace directory."""
        return self.workspaces_root / workspace_id

    def _workspace_json_path(self, workspace_id: str) -> Path:
        """Get path to workspace.json file."""
        return self._workspace_path(workspace_id) / "workspace.json"

    def _base_config_path(self, workspace_id: str) -> Path:
        """Get path to base_config.yaml file."""
        return self._workspace_path(workspace_id) / "base_config.yaml"

    def _scenarios_path(self, workspace_id: str) -> Path:
        """Get path to scenarios directory."""
        return self._workspace_path(workspace_id) / "scenarios"

    def _scenario_path(self, workspace_id: str, scenario_id: str) -> Path:
        """Get path to scenario directory."""
        return self._scenarios_path(workspace_id) / scenario_id

    def _scenario_json_path(self, workspace_id: str, scenario_id: str) -> Path:
        """Get path to scenario.json file."""
        return self._scenario_path(workspace_id, scenario_id) / "scenario.json"

    # ==================== Workspace Operations ====================

    def list_workspaces(self) -> List[WorkspaceSummary]:
        """List all workspaces with summary info."""
        summaries = []

        for workspace_dir in sorted(self.workspaces_root.iterdir()):
            if not workspace_dir.is_dir() or workspace_dir.name.startswith("."):
                continue

            workspace_json = workspace_dir / "workspace.json"
            if not workspace_json.exists():
                continue

            with open(workspace_json) as f:
                data = json.load(f)

            # Count scenarios
            scenarios_dir = workspace_dir / "scenarios"
            scenario_count = 0
            last_run_at = None

            if scenarios_dir.exists():
                for scenario_dir in scenarios_dir.iterdir():
                    if scenario_dir.is_dir():
                        scenario_count += 1
                        scenario_json = scenario_dir / "scenario.json"
                        if scenario_json.exists():
                            with open(scenario_json) as f:
                                scenario_data = json.load(f)
                            if scenario_data.get("last_run_at"):
                                run_at = datetime.fromisoformat(
                                    scenario_data["last_run_at"]
                                )
                                if last_run_at is None or run_at > last_run_at:
                                    last_run_at = run_at

            # Calculate storage
            storage_mb = sum(
                f.stat().st_size for f in workspace_dir.rglob("*") if f.is_file()
            ) / (1024 * 1024)

            summaries.append(
                WorkspaceSummary(
                    id=data["id"],
                    name=data["name"],
                    description=data.get("description"),
                    created_at=datetime.fromisoformat(data["created_at"]),
                    scenario_count=scenario_count,
                    last_run_at=last_run_at,
                    storage_used_mb=storage_mb,
                )
            )

        return summaries

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get a workspace by ID."""
        workspace_json = self._workspace_json_path(workspace_id)
        if not workspace_json.exists():
            return None

        with open(workspace_json) as f:
            data = json.load(f)

        # Load base config
        base_config_path = self._base_config_path(workspace_id)
        if base_config_path.exists():
            with open(base_config_path) as f:
                base_config = yaml.safe_load(f)
        else:
            base_config = data.get("base_config", {})

        return Workspace(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            base_config=base_config,
            storage_path=str(self._workspace_path(workspace_id)),
        )

    def create_workspace(
        self, create_data: WorkspaceCreate, default_config: Dict[str, Any]
    ) -> Workspace:
        """Create a new workspace."""
        workspace_id = str(uuid.uuid4())
        workspace_path = self._workspace_path(workspace_id)
        workspace_path.mkdir(parents=True)

        # Create scenarios directory
        (workspace_path / "scenarios").mkdir()
        (workspace_path / "comparisons").mkdir()

        now = datetime.utcnow()
        base_config = create_data.base_config or default_config

        # Save workspace.json
        workspace_data = {
            "id": workspace_id,
            "name": create_data.name,
            "description": create_data.description,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        with open(self._workspace_json_path(workspace_id), "w") as f:
            json.dump(workspace_data, f, indent=2)

        # Save base_config.yaml
        with open(self._base_config_path(workspace_id), "w") as f:
            yaml.dump(base_config, f, default_flow_style=False)

        return Workspace(
            id=workspace_id,
            name=create_data.name,
            description=create_data.description,
            created_at=now,
            updated_at=now,
            base_config=base_config,
            storage_path=str(workspace_path),
        )

    def update_workspace(
        self,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        base_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Workspace]:
        """Update a workspace."""
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return None

        now = datetime.utcnow()

        # Update workspace.json
        workspace_json_path = self._workspace_json_path(workspace_id)
        with open(workspace_json_path) as f:
            data = json.load(f)

        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        data["updated_at"] = now.isoformat()

        with open(workspace_json_path, "w") as f:
            json.dump(data, f, indent=2)

        # Update base_config.yaml if provided
        if base_config is not None:
            with open(self._base_config_path(workspace_id), "w") as f:
                yaml.dump(base_config, f, default_flow_style=False)

        return self.get_workspace(workspace_id)

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace and all its contents."""
        workspace_path = self._workspace_path(workspace_id)
        if not workspace_path.exists():
            return False

        shutil.rmtree(workspace_path)
        return True

    # ==================== Scenario Operations ====================

    def list_scenarios(self, workspace_id: str) -> List[Scenario]:
        """List all scenarios in a workspace."""
        scenarios = []
        scenarios_dir = self._scenarios_path(workspace_id)

        if not scenarios_dir.exists():
            return scenarios

        for scenario_dir in sorted(scenarios_dir.iterdir()):
            if not scenario_dir.is_dir():
                continue

            scenario_json = scenario_dir / "scenario.json"
            if not scenario_json.exists():
                continue

            with open(scenario_json) as f:
                data = json.load(f)

            scenarios.append(
                Scenario(
                    id=data["id"],
                    workspace_id=data["workspace_id"],
                    name=data["name"],
                    description=data.get("description"),
                    config_overrides=data.get("config_overrides", {}),
                    status=data.get("status", "not_run"),
                    created_at=datetime.fromisoformat(data["created_at"]),
                    last_run_at=(
                        datetime.fromisoformat(data["last_run_at"])
                        if data.get("last_run_at")
                        else None
                    ),
                    last_run_id=data.get("last_run_id"),
                    results_summary=data.get("results_summary"),
                )
            )

        return scenarios

    def get_scenario(self, workspace_id: str, scenario_id: str) -> Optional[Scenario]:
        """Get a scenario by ID."""
        scenario_json = self._scenario_json_path(workspace_id, scenario_id)
        if not scenario_json.exists():
            return None

        with open(scenario_json) as f:
            data = json.load(f)

        return Scenario(
            id=data["id"],
            workspace_id=data["workspace_id"],
            name=data["name"],
            description=data.get("description"),
            config_overrides=data.get("config_overrides", {}),
            status=data.get("status", "not_run"),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_run_at=(
                datetime.fromisoformat(data["last_run_at"])
                if data.get("last_run_at")
                else None
            ),
            last_run_id=data.get("last_run_id"),
            results_summary=data.get("results_summary"),
        )

    def create_scenario(
        self, workspace_id: str, create_data: ScenarioCreate
    ) -> Optional[Scenario]:
        """Create a new scenario in a workspace."""
        # Verify workspace exists
        if not self._workspace_path(workspace_id).exists():
            return None

        scenario_id = str(uuid.uuid4())
        scenario_path = self._scenario_path(workspace_id, scenario_id)
        scenario_path.mkdir(parents=True)

        # Create subdirectories
        (scenario_path / "results").mkdir()
        (scenario_path / "runs").mkdir()

        now = datetime.utcnow()

        scenario_data = {
            "id": scenario_id,
            "workspace_id": workspace_id,
            "name": create_data.name,
            "description": create_data.description,
            "config_overrides": create_data.config_overrides,
            "status": "not_run",
            "created_at": now.isoformat(),
        }

        with open(self._scenario_json_path(workspace_id, scenario_id), "w") as f:
            json.dump(scenario_data, f, indent=2)

        # Save overrides.yaml for reference
        with open(scenario_path / "overrides.yaml", "w") as f:
            yaml.dump(create_data.config_overrides, f, default_flow_style=False)

        return Scenario(
            id=scenario_id,
            workspace_id=workspace_id,
            name=create_data.name,
            description=create_data.description,
            config_overrides=create_data.config_overrides,
            status="not_run",
            created_at=now,
        )

    def update_scenario(
        self,
        workspace_id: str,
        scenario_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[Scenario]:
        """Update a scenario."""
        scenario_json_path = self._scenario_json_path(workspace_id, scenario_id)
        if not scenario_json_path.exists():
            return None

        with open(scenario_json_path) as f:
            data = json.load(f)

        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if config_overrides is not None:
            data["config_overrides"] = config_overrides
            # Update overrides.yaml
            with open(
                self._scenario_path(workspace_id, scenario_id) / "overrides.yaml", "w"
            ) as f:
                yaml.dump(config_overrides, f, default_flow_style=False)

        with open(scenario_json_path, "w") as f:
            json.dump(data, f, indent=2)

        return self.get_scenario(workspace_id, scenario_id)

    def update_scenario_status(
        self,
        workspace_id: str,
        scenario_id: str,
        status: str,
        run_id: Optional[str] = None,
        results_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[Scenario]:
        """Update scenario status after a run."""
        scenario_json_path = self._scenario_json_path(workspace_id, scenario_id)
        if not scenario_json_path.exists():
            return None

        with open(scenario_json_path) as f:
            data = json.load(f)

        data["status"] = status
        if run_id:
            data["last_run_id"] = run_id
            data["last_run_at"] = datetime.utcnow().isoformat() + "Z"  # Add Z for UTC timezone
        if results_summary:
            data["results_summary"] = results_summary

        with open(scenario_json_path, "w") as f:
            json.dump(data, f, indent=2)

        return self.get_scenario(workspace_id, scenario_id)

    def delete_scenario(self, workspace_id: str, scenario_id: str) -> bool:
        """Delete a scenario and all its contents."""
        scenario_path = self._scenario_path(workspace_id, scenario_id)
        if not scenario_path.exists():
            return False

        shutil.rmtree(scenario_path)
        return True

    def get_scenario_database_path(self, workspace_id: str, scenario_id: str) -> Path:
        """Get path to scenario's DuckDB database."""
        return self._scenario_path(workspace_id, scenario_id) / "simulation.duckdb"

    def get_merged_config(
        self, workspace_id: str, scenario_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get merged configuration (base + overrides) for a scenario."""
        workspace = self.get_workspace(workspace_id)
        scenario = self.get_scenario(workspace_id, scenario_id)

        if not workspace or not scenario:
            return None

        # Deep merge base config with overrides
        return self._deep_merge(workspace.base_config, scenario.config_overrides)

    def _deep_merge(
        self, base: Dict[str, Any], overrides: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deep merge two dictionaries."""
        result = base.copy()

        for key, value in overrides.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def update_base_config_key(
        self, workspace_id: str, key_path: str, value: Any
    ) -> bool:
        """
        Update a specific key in the workspace's base_config.yaml.

        Args:
            workspace_id: The workspace ID
            key_path: Dot-separated path to the key (e.g., "setup.census_parquet_path")
            value: The value to set

        Returns:
            True if successful, False if workspace doesn't exist
        """
        base_config_path = self._base_config_path(workspace_id)
        if not base_config_path.exists():
            return False

        # Load existing config
        with open(base_config_path) as f:
            config = yaml.safe_load(f) or {}

        # Navigate to the key and set value
        keys = key_path.split(".")
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

        # Save back to file
        with open(base_config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        return True
