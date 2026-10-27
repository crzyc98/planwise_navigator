"""Dependency closure contracts for normal and calibration workflows."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from planalign_orchestrator.pipeline.workflow import WorkflowBuilder
from tests.helpers.dbt_manifest import load_production_manifest, model_nodes

ROOT = Path(__file__).parents[3]
GRAPH = yaml.safe_load(
    (ROOT / "tests/fixtures/state_pipeline_graph_contract.yaml").read_text()
)
REMOVED_MODELS = {
    "int_employee_state_by_year",
    "int_workforce_snapshot_optimized",
}


def _selected(builder, year: int) -> set[str]:
    return {
        model
        for stage in builder(year, 2025)
        for model in stage.models
        if not model.endswith(".*")
    }


@pytest.mark.parametrize(
    "workflow,builder",
    [
        ("normal", WorkflowBuilder.build_year_workflow),
        ("calibration", WorkflowBuilder.build_calibration_year_workflow),
    ],
)
@pytest.mark.parametrize("year", [2025, 2026])
def test_workflow_is_closed_over_materialized_dependencies(
    workflow: str, builder, year: int
):
    manifest = load_production_manifest()
    nodes = manifest["nodes"]
    models = model_nodes(manifest)
    selected = _selected(builder, year)
    prepublished = set(GRAPH["prepublished_models"][workflow])

    assert REMOVED_MODELS.isdisjoint(selected)
    for model in selected:
        node = models.get(model)
        if node is None:
            continue
        for dependency_id in node["depends_on"]["nodes"]:
            dependency = nodes.get(dependency_id)
            if dependency is None or dependency.get("resource_type") != "model":
                continue
            if dependency["config"]["materialized"] == "ephemeral":
                continue
            assert dependency["name"] in selected | prepublished, (
                f"{workflow} {year}: {model} requires unpublished "
                f"{dependency['name']}"
            )


def test_removed_models_are_absent_from_manifest_and_both_workflows():
    models = model_nodes(load_production_manifest())
    assert REMOVED_MODELS.isdisjoint(models)
    for builder in (
        WorkflowBuilder.build_year_workflow,
        WorkflowBuilder.build_calibration_year_workflow,
    ):
        assert REMOVED_MODELS.isdisjoint(_selected(builder, 2025))
        assert REMOVED_MODELS.isdisjoint(_selected(builder, 2026))
