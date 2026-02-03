"""Filesystem storage operations for workspaces and scenarios."""

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

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

        # E091: Debug logging for year range tracking
        base_sim = workspace.base_config.get("simulation", {})
        override_sim = scenario.config_overrides.get("simulation", {})
        logger.info(f"E091: Base config simulation: {base_sim}")
        logger.info(f"E091: Override config simulation: {override_sim}")

        # Deep merge base config with overrides
        merged = self._deep_merge(workspace.base_config, scenario.config_overrides)
        logger.info(f"E091: Merged config simulation: {merged.get('simulation', {})}")

        # Ensure employer_match and employer_core_contribution always have defaults
        # This handles workspaces created before these sections were added
        if "employer_match" not in merged:
            merged["employer_match"] = {
                "active_formula": "simple_match",
                "formulas": {
                    "simple_match": {
                        "name": "Simple Match",
                        "type": "simple",
                        "match_rate": 0.50,
                        "max_match_percentage": 0.06,
                    },
                },
            }
        if "employer_core_contribution" not in merged:
            merged["employer_core_contribution"] = {
                "enabled": True,
                "status": "flat",
                "contribution_rate": 0.03,
            }

        return merged

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

    # ==================== Workspace Repair Operations ====================

    def repair_workspaces(self) -> Dict[str, Any]:
        """
        Scan and repair corrupted workspace and scenario JSON files.

        This method checks all workspaces for corrupted JSON files and attempts
        to repair them by:
        1. Detecting JSON parse errors
        2. Backing up corrupted files
        3. Recreating minimal valid JSON from available metadata

        Returns:
            Dictionary with repair report:
            - workspaces_scanned: Number of workspaces checked
            - scenarios_scanned: Number of scenarios checked
            - repairs: List of repair actions taken
            - errors: List of unrecoverable errors
        """
        report = {
            "workspaces_scanned": 0,
            "scenarios_scanned": 0,
            "repairs": [],
            "errors": [],
        }

        logger.info("Starting workspace repair scan...")

        for workspace_dir in sorted(self.workspaces_root.iterdir()):
            if not workspace_dir.is_dir() or workspace_dir.name.startswith("."):
                continue

            workspace_id = workspace_dir.name
            report["workspaces_scanned"] += 1

            # Check and repair workspace.json
            workspace_json = workspace_dir / "workspace.json"
            repair_result = self._repair_json_file(
                workspace_json,
                self._create_minimal_workspace_json,
                {"workspace_id": workspace_id, "workspace_dir": workspace_dir},
            )
            if repair_result:
                report["repairs"].append(repair_result)

            # Check and repair scenario files
            scenarios_dir = workspace_dir / "scenarios"
            if scenarios_dir.exists():
                for scenario_dir in scenarios_dir.iterdir():
                    if not scenario_dir.is_dir():
                        continue

                    scenario_id = scenario_dir.name
                    report["scenarios_scanned"] += 1

                    scenario_json = scenario_dir / "scenario.json"
                    repair_result = self._repair_json_file(
                        scenario_json,
                        self._create_minimal_scenario_json,
                        {
                            "workspace_id": workspace_id,
                            "scenario_id": scenario_id,
                            "scenario_dir": scenario_dir,
                        },
                    )
                    if repair_result:
                        report["repairs"].append(repair_result)

        logger.info(
            f"Workspace repair complete: {report['workspaces_scanned']} workspaces, "
            f"{report['scenarios_scanned']} scenarios, {len(report['repairs'])} repairs"
        )

        return report

    def _repair_json_file(
        self,
        json_path: Path,
        create_minimal_fn,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to repair a JSON file if corrupted.

        Args:
            json_path: Path to the JSON file
            create_minimal_fn: Function to create minimal valid JSON
            context: Context data for the creation function

        Returns:
            Repair action dict if repaired, None if file was OK or doesn't exist
        """
        if not json_path.exists():
            # File doesn't exist - create it if parent directory exists
            if json_path.parent.exists():
                logger.warning(f"Missing JSON file, creating: {json_path}")
                try:
                    minimal_data = create_minimal_fn(context)
                    with open(json_path, "w") as f:
                        json.dump(minimal_data, f, indent=2)
                    return {
                        "file": str(json_path),
                        "action": "created",
                        "reason": "file_missing",
                    }
                except Exception as e:
                    logger.error(f"Failed to create {json_path}: {e}")
                    return {
                        "file": str(json_path),
                        "action": "failed",
                        "reason": str(e),
                    }
            return None

        # Try to load the JSON file
        try:
            with open(json_path, "r") as f:
                content = f.read()

            # Check for empty file
            if not content.strip():
                raise json.JSONDecodeError("Empty file", content, 0)

            # Try to parse
            data = json.loads(content)

            # Validate required fields exist
            if json_path.name == "workspace.json":
                required = ["id", "name", "created_at", "updated_at"]
            else:  # scenario.json
                required = ["id", "workspace_id", "name", "created_at"]

            missing = [f for f in required if f not in data]
            if missing:
                raise ValueError(f"Missing required fields: {missing}")

            return None  # File is OK

        except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
            logger.warning(f"Corrupted JSON file detected: {json_path} - {e}")

            # Backup the corrupted file
            backup_path = json_path.with_suffix(".json.corrupted")
            backup_num = 1
            while backup_path.exists():
                backup_path = json_path.with_suffix(f".json.corrupted.{backup_num}")
                backup_num += 1

            try:
                shutil.copy2(json_path, backup_path)
                logger.info(f"Backed up corrupted file to: {backup_path}")
            except Exception as backup_err:
                logger.error(f"Failed to backup corrupted file: {backup_err}")

            # Try to salvage partial data
            salvaged_data = self._try_salvage_json(json_path)

            # Create minimal valid JSON
            try:
                minimal_data = create_minimal_fn(context, salvaged_data)
                with open(json_path, "w") as f:
                    json.dump(minimal_data, f, indent=2)

                return {
                    "file": str(json_path),
                    "action": "repaired",
                    "reason": str(e),
                    "backup": str(backup_path),
                    "salvaged_fields": list(salvaged_data.keys()) if salvaged_data else [],
                }
            except Exception as repair_err:
                logger.error(f"Failed to repair {json_path}: {repair_err}")
                return {
                    "file": str(json_path),
                    "action": "failed",
                    "reason": str(repair_err),
                }

    def _try_salvage_json(self, json_path: Path) -> Dict[str, Any]:
        """
        Try to salvage partial data from a corrupted JSON file.

        Uses multiple strategies:
        1. Try parsing with error recovery
        2. Extract key-value pairs with regex
        3. Return empty dict if nothing salvageable
        """
        salvaged = {}

        try:
            with open(json_path, "r", errors="replace") as f:
                content = f.read()

            # Try to find common field patterns
            import re

            # Look for "id": "value" patterns
            id_match = re.search(r'"id"\s*:\s*"([^"]+)"', content)
            if id_match:
                salvaged["id"] = id_match.group(1)

            # Look for "name": "value" patterns
            name_match = re.search(r'"name"\s*:\s*"([^"]+)"', content)
            if name_match:
                salvaged["name"] = name_match.group(1)

            # Look for "workspace_id": "value" patterns
            ws_id_match = re.search(r'"workspace_id"\s*:\s*"([^"]+)"', content)
            if ws_id_match:
                salvaged["workspace_id"] = ws_id_match.group(1)

            # Look for "description": "value" patterns
            desc_match = re.search(r'"description"\s*:\s*"([^"]*)"', content)
            if desc_match:
                salvaged["description"] = desc_match.group(1)

            # Look for ISO date patterns for created_at/updated_at
            date_pattern = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
            dates = re.findall(date_pattern, content)
            if dates:
                salvaged["_salvaged_dates"] = dates

        except Exception as e:
            logger.debug(f"Could not salvage data from {json_path}: {e}")

        return salvaged

    def _create_minimal_workspace_json(
        self, context: Dict[str, Any], salvaged: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create minimal valid workspace.json from context and salvaged data."""
        salvaged = salvaged or {}
        now = datetime.utcnow().isoformat()

        # Try to use salvaged dates
        dates = salvaged.get("_salvaged_dates", [])
        created_at = dates[0] if dates else now
        updated_at = dates[-1] if dates else now

        return {
            "id": salvaged.get("id", context["workspace_id"]),
            "name": salvaged.get("name", f"Recovered Workspace ({context['workspace_id'][:8]})"),
            "description": salvaged.get("description", "Workspace recovered from corrupted data"),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def _create_minimal_scenario_json(
        self, context: Dict[str, Any], salvaged: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create minimal valid scenario.json from context and salvaged data."""
        salvaged = salvaged or {}
        now = datetime.utcnow().isoformat()

        # Try to use salvaged dates
        dates = salvaged.get("_salvaged_dates", [])
        created_at = dates[0] if dates else now

        return {
            "id": salvaged.get("id", context["scenario_id"]),
            "workspace_id": salvaged.get("workspace_id", context["workspace_id"]),
            "name": salvaged.get("name", f"Recovered Scenario ({context['scenario_id'][:8]})"),
            "description": salvaged.get("description", "Scenario recovered from corrupted data"),
            "config_overrides": {},
            "status": "not_run",
            "created_at": created_at,
        }

    # ==================== Export Operations ====================

    def get_workspace_files_for_export(self, workspace_id: str) -> List[Path]:
        """Get list of all files in a workspace for export.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            List of Path objects for all files in the workspace directory

        Raises:
            ValueError: If workspace does not exist
        """
        workspace_path = self._workspace_path(workspace_id)
        if not workspace_path.exists():
            raise ValueError(f"Workspace not found: {workspace_id}")

        files = []
        for file_path in workspace_path.rglob("*"):
            if file_path.is_file():
                files.append(file_path)

        return files

    def is_simulation_running(self, workspace_id: str) -> bool:
        """Check if any simulation is currently running for a workspace.

        This checks for running scenarios by looking at scenario status fields.

        Args:
            workspace_id: UUID of the workspace

        Returns:
            True if any scenario has a 'running' status, False otherwise
        """
        scenarios_dir = self._scenarios_path(workspace_id)
        if not scenarios_dir.exists():
            return False

        for scenario_dir in scenarios_dir.iterdir():
            if not scenario_dir.is_dir():
                continue

            scenario_json = scenario_dir / "scenario.json"
            if not scenario_json.exists():
                continue

            try:
                with open(scenario_json) as f:
                    data = json.load(f)
                if data.get("status") == "running":
                    return True
            except (json.JSONDecodeError, IOError):
                continue

        return False
