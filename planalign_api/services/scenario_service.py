"""Scenario service - thin wrapper around storage."""

import copy
import logging
from typing import Any, Dict, List, Optional

from ..models.scenario import (
    Scenario,
    ScenarioApplyOutcome,
    ScenarioCreate,
    ScenarioUpdate,
    WorkforceParamsApplyResult,
)
from ..services.seed_config_validator import validate_seed_configs
from ..storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

# Top-level config sections that are workforce parameters (copied entirely)
WORKFORCE_SECTIONS = {"workforce", "compensation", "new_hire"}

# Top-level seed configs that are workforce parameters (atomic replacement)
WORKFORCE_SEED_CONFIGS = {"promotion_hazard", "age_bands", "tenure_bands"}

# Single keys extracted from the simulation section
WORKFORCE_SIMULATION_KEYS = {"target_growth_rate"}


def extract_workforce_params(config_overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Extract workforce-only parameters from a config_overrides dict.

    Includes: workforce, compensation, new_hire sections,
    simulation.target_growth_rate, and seed configs
    (promotion_hazard, age_bands, tenure_bands).

    Excludes: dc_plan, simulation identity fields, data_sources, advanced.
    """
    result: Dict[str, Any] = {}

    # Copy entire workforce sections
    for section in WORKFORCE_SECTIONS:
        if section in config_overrides:
            result[section] = copy.deepcopy(config_overrides[section])

    # Copy specific simulation keys
    sim = config_overrides.get("simulation", {})
    sim_workforce = {k: v for k, v in sim.items() if k in WORKFORCE_SIMULATION_KEYS}
    if sim_workforce:
        result["simulation"] = sim_workforce

    # Copy seed configs (atomic replacement)
    for key in WORKFORCE_SEED_CONFIGS:
        if key in config_overrides:
            result[key] = copy.deepcopy(config_overrides[key])

    return result


class ScenarioService:
    """Service for scenario operations."""

    def __init__(self, storage: WorkspaceStorage):
        self.storage = storage

    def list_scenarios(self, workspace_id: str) -> List[Scenario]:
        """List all scenarios in a workspace."""
        return self.storage.list_scenarios(workspace_id)

    def get_scenario(self, workspace_id: str, scenario_id: str) -> Optional[Scenario]:
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
        return self.storage.update_scenario(
            workspace_id,
            scenario_id,
            name=data.name,
            description=data.description,
            config_overrides=data.config_overrides,
        )

    def delete_scenario(self, workspace_id: str, scenario_id: str) -> bool:
        """Delete a scenario."""
        return self.storage.delete_scenario(workspace_id, scenario_id)

    def get_merged_config(
        self, workspace_id: str, scenario_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get merged configuration (base + overrides)."""
        return self.storage.get_merged_config(workspace_id, scenario_id)

    def apply_workforce_params(
        self,
        workspace_id: str,
        source_scenario_id: str,
        target_scenario_ids: list[str],
    ) -> Optional[WorkforceParamsApplyResult]:
        """Apply workforce parameters from source scenario to target scenarios.

        Copies workforce sections (compensation, workforce, new_hire,
        simulation.target_growth_rate, promotion_hazard, age_bands,
        tenure_bands) while preserving DC plan parameters in targets.
        """
        source = self.storage.get_scenario(workspace_id, source_scenario_id)
        if not source:
            return None  # Caller should raise 404

        workforce_params = extract_workforce_params(source.config_overrides)
        results: list[ScenarioApplyOutcome] = []

        for target_id in target_scenario_ids:
            outcome = self._apply_to_target(workspace_id, target_id, workforce_params)
            results.append(outcome)

        total_applied = sum(1 for r in results if r.success)
        total_failed = sum(1 for r in results if not r.success)

        return WorkforceParamsApplyResult(
            source_scenario_id=source_scenario_id,
            results=results,
            total_applied=total_applied,
            total_failed=total_failed,
        )

    def _apply_to_target(
        self,
        workspace_id: str,
        target_id: str,
        workforce_params: Dict[str, Any],
    ) -> ScenarioApplyOutcome:
        """Apply workforce params to a single target scenario."""
        try:
            target = self.storage.get_scenario(workspace_id, target_id)
            if not target:
                return ScenarioApplyOutcome(
                    scenario_id=target_id,
                    scenario_name=None,
                    success=False,
                    error="Scenario not found",
                )

            merged = copy.deepcopy(target.config_overrides)

            # Replace entire workforce sections
            for section in WORKFORCE_SECTIONS:
                if section in workforce_params:
                    merged[section] = copy.deepcopy(workforce_params[section])
                elif section in merged:
                    del merged[section]

            # Merge simulation.target_growth_rate (preserve other sim keys)
            if "simulation" in workforce_params:
                if "simulation" not in merged:
                    merged["simulation"] = {}
                for key, value in workforce_params["simulation"].items():
                    merged["simulation"][key] = value

            # Replace seed configs atomically
            for key in WORKFORCE_SEED_CONFIGS:
                if key in workforce_params:
                    merged[key] = copy.deepcopy(workforce_params[key])
                elif key in merged:
                    del merged[key]

            # Validate seed configs before writing
            validation_errors = validate_seed_configs(merged)
            if validation_errors:
                messages = [
                    f"{e.section}.{e.field}: {e.message}" for e in validation_errors
                ]
                return ScenarioApplyOutcome(
                    scenario_id=target_id,
                    scenario_name=target.name,
                    success=False,
                    error=f"Validation failed: {'; '.join(messages)}",
                )

            updated = self.storage.update_scenario(
                workspace_id,
                target_id,
                config_overrides=merged,
            )

            if not updated:
                return ScenarioApplyOutcome(
                    scenario_id=target_id,
                    scenario_name=target.name,
                    success=False,
                    error="Failed to update scenario",
                )

            return ScenarioApplyOutcome(
                scenario_id=target_id,
                scenario_name=target.name,
                success=True,
                error=None,
            )
        except Exception as e:
            logger.exception("Failed to apply workforce params to %s", target_id)
            return ScenarioApplyOutcome(
                scenario_id=target_id,
                scenario_name=None,
                success=False,
                error=str(e),
            )

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
