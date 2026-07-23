"""Manifest-backed stage ownership and staged-output contracts."""

from __future__ import annotations

import inspect
from pathlib import Path

import yaml

from planalign_core.constants import (
    STATE_PIPELINE_AUDIT_SINKS,
    STATE_PIPELINE_OWNERSHIP_MODELS,
)
from planalign_orchestrator.pipeline import event_generation_executor
from tests.helpers.dbt_manifest import load_production_manifest, model_nodes

ROOT = Path(__file__).parents[3]
GRAPH = yaml.safe_load(
    (ROOT / "tests/fixtures/state_pipeline_graph_contract.yaml").read_text()
)


def _fixture_ownership() -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for ownership, config in GRAPH["ownership_classes"].items():
        members = config.get("fixture_members")
        if not members:
            members = GRAPH[config["expected_members_from"]]
        result[ownership] = tuple(members)
    return result


def test_ownership_constants_match_checked_fixture():
    assert STATE_PIPELINE_OWNERSHIP_MODELS == _fixture_ownership()
    assert STATE_PIPELINE_AUDIT_SINKS == {
        item["model"] for item in GRAPH["intentional_audit_sinks"]
    }


def test_manifest_ownership_classes_are_exact_and_mutually_exclusive():
    models = model_nodes(load_production_manifest())
    expected = _fixture_ownership()
    ownership_tags = set(expected)

    for ownership, expected_members in expected.items():
        actual = {name for name, node in models.items() if ownership in node["tags"]}
        assert actual == set(expected_members)

    for model in {name for members in expected.values() for name in members}:
        assigned = ownership_tags.intersection(models[model]["tags"])
        assert len(assigned) == 1, f"{model} has ownership tags {assigned}"


def test_event_executor_has_no_manual_model_exclusions():
    source = inspect.getsource(event_generation_executor.EventGenerationExecutor)
    assert '"--exclude"' not in source
    assert "tag:EVENT_GENERATION" in source


def test_every_owned_stage_node_has_consumer_or_audit_sink():
    manifest = load_production_manifest()
    models = model_nodes(manifest)
    by_id = {node["unique_id"]: node for node in models.values()}
    staged = {name for members in _fixture_ownership().values() for name in members}

    for model in staged:
        consumers = {
            by_id[child]["name"]
            for child in manifest["child_map"].get(models[model]["unique_id"], [])
            if child in by_id
        }
        assert (
            consumers or model in STATE_PIPELINE_AUDIT_SINKS
        ), f"{model} has no model consumer and is not a checked audit sink"
