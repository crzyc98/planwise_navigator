"""CI guard against enabled dbt models that no production path can build."""

from __future__ import annotations

import pytest

from planalign_orchestrator.hazard_cache_manager import HazardCacheManager
from planalign_orchestrator.pipeline.workflow import WorkflowBuilder
from tests.helpers.dbt_manifest import load_production_manifest, model_nodes

pytestmark = [pytest.mark.fast, pytest.mark.config]

# These directories contain opt-in diagnostics, not production pipeline models.
NON_PRODUCTION_PATH_PARTS = {
    "analysis",
    "data_quality",
    "debug",
    "monitoring",
    "reporting",
}

# Supported standalone relation initialized for ad-hoc inspection. Adding an
# entry requires an explicit product decision; this is not an orphan allow-list.
INTENTIONAL_STANDALONE_ROOTS = {
    "dim_hazard_table": "documented ad-hoc combined hazard lookup",
}

REMOVED_ORPHANS = {
    "debug_variables",
    "fct_payroll_ledger",
    "fct_policy_optimization",
    "fct_workforce_snapshot_gate_c",
    "int_active_employees_by_year",
    "int_cold_start_detection",
    "int_compensation_periods_debug",
    "int_eligibility_computation_period",
    "int_employee_event_stream",
    "int_employees_with_initial_state",
    "int_partitioned_workforce_data",
    "int_service_credit_accumulator",
    "int_simulation_run_log",
    "int_snapshot_base",
    "int_snapshot_compensation_legacy",
    "int_snapshot_hiring",
    "int_snapshot_merit",
    "int_snapshot_promotion",
    "int_snapshot_termination",
    "int_workforce_changes",
    "int_workforce_needs_by_level_gate_b",
    "int_workforce_needs_gate_a",
    "int_workforce_previous_year",
    "int_year_snapshot_preparation",
    "performance_metrics",
    "vw_performance_dashboard",
}


def _workflow_roots() -> set[str]:
    roots: set[str] = set()
    for builder in (
        WorkflowBuilder.build_year_workflow,
        WorkflowBuilder.build_calibration_year_workflow,
    ):
        for year in (2025, 2026):
            for stage in builder(year, 2025):
                roots.update(
                    model for model in stage.models if not model.endswith(".*")
                )
    return roots


def _production_roots(models: dict[str, dict]) -> set[str]:
    roots = _workflow_roots()
    roots.update(HazardCacheManager.CACHE_MODELS)
    roots.add(HazardCacheManager.METADATA_MODEL)
    roots.update(INTENTIONAL_STANDALONE_ROOTS)
    roots.update(
        name
        for name, node in models.items()
        if node["original_file_path"].startswith("models/staging/")
        or "EVENT_GENERATION" in node.get("tags", [])
    )
    return roots


def _dependency_closure(manifest: dict, roots: set[str]) -> set[str]:
    models = model_nodes(manifest)
    by_id = {node["unique_id"]: node for node in models.values()}
    pending = [models[name]["unique_id"] for name in roots if name in models]
    reachable: set[str] = set()
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        pending.extend(
            dependency
            for dependency in by_id[node_id]["depends_on"]["nodes"]
            if dependency in by_id
        )
    return {by_id[node_id]["name"] for node_id in reachable}


def _is_production_model(node: dict) -> bool:
    path_parts = set(node["original_file_path"].split("/"))
    return not path_parts.intersection(NON_PRODUCTION_PATH_PARTS)


def test_every_enabled_production_model_is_reachable() -> None:
    manifest = load_production_manifest()
    models = model_nodes(manifest)
    reachable = _dependency_closure(manifest, _production_roots(models))
    enabled_production = {
        name
        for name, node in models.items()
        if node["config"].get("enabled", True) and _is_production_model(node)
    }

    assert enabled_production <= reachable, (
        "Enabled dbt models have no production build path: "
        f"{sorted(enabled_production - reachable)}"
    )


def test_removed_orphans_are_absent_from_manifest() -> None:
    assert REMOVED_ORPHANS.isdisjoint(model_nodes(load_production_manifest()))
