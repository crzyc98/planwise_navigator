"""CI guard against enabled dbt models that no production path can build."""

from __future__ import annotations

import pytest

from planalign_orchestrator.generators import EventRegistry
from planalign_orchestrator.hazard_cache_manager import HazardCacheManager
from planalign_orchestrator.pipeline.workflow import WorkflowBuilder
from tests.helpers.dbt_manifest import load_production_manifest, model_nodes

pytestmark = [
    pytest.mark.fast,
    pytest.mark.config,
    pytest.mark.xdist_group("dbt_manifest"),
]

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

# SQL-terminal outputs must have a non-SQL consumer or an explicit standalone
# purpose. See docs/guides/dbt_terminal_outputs.md for the consumer audit.
TERMINAL_OUTPUT_PURPOSES = {
    "dim_hazard_table": "standalone combined hazard inspection",
    "fct_compensation_growth": "CalibrationRunner._read_year compensation metrics",
    "fct_employer_match_events": "TimelineService employer contribution history",
    "hazard_cache_metadata": "HazardCacheManager cache currency checks",
    "int_deferral_change_events": "int_current_year_events when deferral_rate_changes_enabled (#986)",
    "stg_census_duplicates_audit": "standalone census deduplication audit",
    "stg_comp_targets": "compensation calibration target inspection",
    "stg_config_age_bands": "EventGenerator age-band lookup",
    "stg_config_raise_timing_distribution": "standalone raise-timing inspection",
    "stg_config_raises_hazard": "standalone raise-hazard configuration inspection",
    "stg_config_tenure_bands": "EventGenerator tenure-band lookup",
    "stg_config_timing_validation_rules": "standalone timing-rule inspection",
    "stg_scenario_meta": "standalone scenario metadata inspection",
}

REMOVED_ORPHANS = {
    "int_workforce_pre_enrollment",
    "int_eligibility_determination",
    "int_deferral_escalation_state_accumulator",
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
    for event_type in EventRegistry.list_all():
        roots.update(getattr(EventRegistry.get_class(event_type), "dbt_models", []))
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


def _terminal_roots(models: dict[str, dict], roots: set[str]) -> set[str]:
    consumed = {
        dependency
        for node in models.values()
        if _is_production_model(node)
        for dependency in node["depends_on"]["nodes"]
        if dependency != node["unique_id"]
    }
    return {
        name
        for name in roots
        if name in models
        and models[name]["unique_id"] not in consumed
        and _is_production_model(models[name])
    }


def test_scheduled_terminal_models_have_documented_output_purposes() -> None:
    manifests = [model_nodes(load_production_manifest(year)) for year in (2025, 2026)]
    # A year-conditional ref is a real consumer even when absent in Year 1.
    terminal = set.intersection(
        *(_terminal_roots(models, _production_roots(models)) for models in manifests)
    )
    assert terminal == set(TERMINAL_OUTPUT_PURPOSES), (
        "Scheduled terminal models need a documented output purpose; update "
        "docs/guides/dbt_terminal_outputs.md with the actual consumer or remove "
        f"the materialization. Undocumented: {sorted(terminal - TERMINAL_OUTPUT_PURPOSES.keys())}; "
        f"stale purposes: {sorted(TERMINAL_OUTPUT_PURPOSES.keys() - terminal)}"
    )
    assert all(TERMINAL_OUTPUT_PURPOSES.values())


def test_scheduling_an_unconsumed_model_does_not_hide_it() -> None:
    model = {
        "unique_id": "model.planalign.unused",
        "original_file_path": "models/intermediate/unused.sql",
        "depends_on": {"nodes": ["model.planalign.unused"]},
    }
    assert _terminal_roots({"unused": model}, {"unused"}) == {"unused"}
    # Even a diagnostic consumer does not justify a production materialization.
    diagnostic = {
        "unique_id": "model.planalign.diagnostic",
        "original_file_path": "models/monitoring/diagnostic.sql",
        "depends_on": {"nodes": [model["unique_id"]]},
    }
    assert _terminal_roots({"unused": model, "diagnostic": diagnostic}, {"unused"}) == {
        "unused"
    }
    consumer = {**diagnostic, "original_file_path": "models/marts/output.sql"}
    assert not _terminal_roots({"unused": model, "output": consumer}, {"unused"})


def test_compounding_diagnostic_keeps_its_opt_in_workforce_helper() -> None:
    models = model_nodes(load_production_manifest())
    helper = models["int_workforce_active_for_events"]
    assert helper["original_file_path"].startswith("models/analysis/")
    assert helper["name"] not in _workflow_roots()
    assert (
        helper["unique_id"]
        in models["test_compensation_compounding_validation"]["depends_on"]["nodes"]
    )


def test_every_enabled_production_model_is_reachable() -> None:
    manifest = load_production_manifest()
    models = model_nodes(manifest)
    assert _workflow_roots() <= models.keys(), "Scheduled model declarations must exist"
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
