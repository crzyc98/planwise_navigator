"""Production SQL graph and publication schedule contracts for Feature 122."""

import json
import re
from pathlib import Path

import yaml

from planalign_core.constants import (
    MODEL_FCT_WORKFORCE_SNAPSHOT,
    MODEL_FCT_YEARLY_EVENTS,
    MODEL_INT_WORKFORCE_STATE_ACCUMULATOR,
)
from planalign_orchestrator.pipeline.workflow import WorkflowBuilder, WorkflowStage
from tests.helpers.dbt_manifest import load_production_manifest, model_nodes

ROOT = Path(__file__).parents[3]
GRAPH = yaml.safe_load(
    (ROOT / "tests/fixtures/state_pipeline_graph_contract.yaml").read_text()
)


def _refs(path: Path) -> set[str]:
    return set(re.findall(r"ref\(['\"]([^'\"]+)['\"]\)", path.read_text()))


def _state_models(workflow):
    return next(
        stage.models
        for stage in workflow
        if stage.name is WorkflowStage.STATE_ACCUMULATION
    )


def _successful_model_counts(run_results: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in run_results.get("results", []):
        if result.get("status") != "success":
            continue
        name = result["unique_id"].split(".")[-1]
        counts[name] = counts.get(name, 0) + 1
    return counts


def test_current_year_assembly_has_exact_active_sql_candidates():
    assembly = ROOT / "dbt/models/intermediate/int_current_year_events.sql"
    assert _refs(assembly) == set(GRAPH["event_candidates"])


def test_fact_is_thin_publisher_and_not_in_state_schedules():
    fact = ROOT / "dbt/models/marts/fct_yearly_events.sql"
    assert _refs(fact) == {"int_current_year_events"}
    for year in (2025, 2026):
        assert MODEL_FCT_YEARLY_EVENTS not in _state_models(
            WorkflowBuilder.build_year_workflow(year, 2025)
        )
        assert MODEL_FCT_YEARLY_EVENTS not in _state_models(
            WorkflowBuilder.build_calibration_year_workflow(year, 2025)
        )


def test_run_results_publication_count_contract_is_measured_per_year():
    for year in (2025, 2026, 2027):
        payload = {
            "results": [
                {
                    "unique_id": f"model.planalign.{MODEL_FCT_YEARLY_EVENTS}",
                    "status": "success",
                },
                {
                    "unique_id": f"model.planalign.{MODEL_FCT_WORKFORCE_SNAPSHOT}",
                    "status": "success",
                },
            ],
            "metadata": {"simulation_year": year},
        }
        counts = _successful_model_counts(json.loads(json.dumps(payload)))
        assert counts[MODEL_FCT_YEARLY_EVENTS] == 1
        assert counts[MODEL_FCT_WORKFORCE_SNAPSHOT] == 1


def test_workforce_accumulator_has_strict_scope_and_domain_contract():
    path = ROOT / "dbt/models/intermediate/int_workforce_state_accumulator.sql"
    sql = path.read_text()
    assert _refs(path) == {
        "int_baseline_workforce",
        "int_hiring_events",
        "stg_census_data",
        MODEL_FCT_YEARLY_EVENTS,
    }
    assert "FROM {{ this }}" in sql
    assert "simulation_year = {{ simulation_year - 1 }}" in sql
    assert "var('scenario_id', 'default')" in sql
    assert "var('plan_design_id', 'default')" in sql
    assert "'default' AS scenario_id" not in sql
    assert "'main' AS plan_design_id" not in sql

    schema = yaml.safe_load((ROOT / "dbt/models/intermediate/schema.yml").read_text())
    model = next(
        item
        for item in schema["models"]
        if item["name"] == MODEL_INT_WORKFORCE_STATE_ACCUMULATOR
    )
    columns = {column["name"] for column in model["columns"]}
    assert {
        "scenario_id",
        "plan_design_id",
        "employee_id",
        "simulation_year",
    } <= columns
    assert not columns & {
        "is_enrolled",
        "enrollment_date",
        "deferral_rate",
        "account_balance",
        "employer_match_amount",
        "employer_core_amount",
    }


def test_deferral_accumulator_uses_the_configured_scenario_scope():
    path = ROOT / "dbt/models/intermediate/int_deferral_rate_state_accumulator.sql"
    sql = path.read_text()

    assert "var('scenario_id', 'default')" in sql
    assert "'{{ scenario_id }}'::VARCHAR as scenario_id" in sql
    assert "'default'::VARCHAR as scenario_id" not in sql


def test_workforce_accumulator_is_shadow_scheduled_for_normal_and_calibration():
    for builder in (
        WorkflowBuilder.build_year_workflow,
        WorkflowBuilder.build_calibration_year_workflow,
    ):
        assert MODEL_INT_WORKFORCE_STATE_ACCUMULATOR in _state_models(
            builder(2025, 2025)
        )


def test_prior_workforce_helpers_use_only_declared_projection_source():
    for model in (
        "int_active_employees_prev_year_snapshot",
        "int_prev_year_workforce_summary",
        "int_prev_year_workforce_by_level",
    ):
        sql = (ROOT / f"dbt/models/intermediate/{model}.sql").read_text()
        assert "source('orchestrator_state', 'workforce_state_projection')" in sql
        assert "adapter.get_relation" not in sql
        assert "fct_workforce_snapshot" not in sql


def test_prior_active_helper_preserves_historical_enrollment_semantics():
    sql = (
        ROOT / "dbt/models/intermediate/int_active_employees_prev_year_snapshot.sql"
    ).read_text()

    assert "authoritative_enrollment_date" in sql
    assert "enrollment.enrollment_date" in sql
    assert ") IS NOT NULL THEN TRUE" in sql
    assert "authoritative_is_enrolled" not in sql


def test_employer_eligibility_consumes_canonical_workforce_state():
    path = ROOT / "dbt/models/intermediate/int_employer_eligibility.sql"

    assert _refs(path) == {MODEL_INT_WORKFORCE_STATE_ACCUMULATOR}
    workflow = WorkflowBuilder.build_year_workflow(2025, 2025)
    event_models = next(
        stage.models
        for stage in workflow
        if stage.name is WorkflowStage.EVENT_GENERATION
    )
    state_models = _state_models(workflow)
    assert "int_employer_eligibility" not in event_models
    assert state_models.index(
        MODEL_INT_WORKFORCE_STATE_ACCUMULATOR
    ) < state_models.index("int_employer_eligibility")


def test_employee_contributions_consume_authoritative_domain_state():
    path = ROOT / "dbt/models/intermediate/int_employee_contributions.sql"

    assert _refs(path) == {
        "config_irs_limits",
        "int_deferral_rate_state_accumulator",
        "int_enrollment_state_accumulator",
        MODEL_FCT_YEARLY_EVENTS,
        MODEL_INT_WORKFORCE_STATE_ACCUMULATOR,
    }


def test_employer_core_consumes_workforce_state_and_eligibility():
    path = ROOT / "dbt/models/intermediate/int_employer_core_contributions.sql"

    assert _refs(path) == {
        "config_irs_limits",
        MODEL_FCT_YEARLY_EVENTS,
        "int_employer_eligibility",
        MODEL_INT_WORKFORCE_STATE_ACCUMULATOR,
    }


def test_employee_match_consumes_canonical_workforce_and_benefit_inputs():
    path = ROOT / "dbt/models/intermediate/int_employee_match_calculations.sql"

    assert _refs(path) == {
        "config_irs_limits",
        "int_employee_contributions",
        "int_employer_eligibility",
        MODEL_INT_WORKFORCE_STATE_ACCUMULATOR,
    }


def test_workforce_snapshot_is_domain_state_composition():
    path = ROOT / "dbt/models/marts/fct_workforce_snapshot.sql"

    assert _refs(path) == {
        "config_irs_limits",
        "int_baseline_workforce",
        "int_deferral_rate_state_accumulator",
        "int_employee_contributions",
        "int_employee_match_calculations",
        "int_employer_core_contributions",
        "int_employer_eligibility",
        "int_enrollment_state_accumulator",
        MODEL_INT_WORKFORCE_STATE_ACCUMULATOR,
    }


def test_removed_legacy_state_models_are_absent_from_sql_and_workflows():
    removed = {
        "int_employee_state_by_year",
        "int_workforce_snapshot_optimized",
    }
    sql_models = {path.stem for path in (ROOT / "dbt/models").rglob("*.sql")}
    assert removed.isdisjoint(sql_models)

    for builder in (
        WorkflowBuilder.build_year_workflow,
        WorkflowBuilder.build_calibration_year_workflow,
    ):
        selected = {model for stage in builder(2025, 2025) for model in stage.models}
        assert removed.isdisjoint(selected)


def test_manifest_has_exact_candidate_ownership_and_complete_assembly():
    manifest = load_production_manifest()
    models = model_nodes(manifest)
    tagged = {
        name for name, node in models.items() if "EVENT_CANDIDATE" in node["tags"]
    }

    assert tagged == set(GRAPH["event_candidates"])
    assert _refs(ROOT / "dbt/models/intermediate/int_current_year_events.sql") == tagged


def test_event_candidate_ancestry_has_no_current_year_publication_feedback():
    manifest = load_production_manifest()
    nodes = manifest["nodes"]
    models = model_nodes(manifest)
    forbidden_tags = {
        "EVENT_PUBLICATION",
        "DOMAIN_STATE",
        "BENEFIT_CALCULATION",
        "SNAPSHOT_PUBLICATION",
    }

    def ancestors(unique_id: str) -> set[str]:
        pending = list(nodes[unique_id]["depends_on"]["nodes"])
        found: set[str] = set()
        while pending:
            parent = pending.pop()
            if parent in found or parent not in nodes:
                continue
            found.add(parent)
            pending.extend(nodes[parent].get("depends_on", {}).get("nodes", []))
        return found

    for candidate in GRAPH["event_candidates"]:
        node = models[candidate]
        for ancestor_id in ancestors(node["unique_id"]):
            ancestor = nodes[ancestor_id]
            assert forbidden_tags.isdisjoint(ancestor.get("tags", [])), (
                f"{candidate} has current-year state/publication ancestor "
                f"{ancestor['name']}"
            )


def test_temporal_escape_hatches_are_only_declared_prior_projections():
    manifest = load_production_manifest()
    sources = manifest["sources"]
    allowed_sources = set(GRAPH["temporal_projection_sources"])
    allowed_consumers = {
        "stg_prior_enrollment_state",
        "int_active_employees_prev_year_snapshot",
        "int_prev_year_workforce_summary",
        "int_prev_year_workforce_by_level",
    }
    observed: set[str] = set()

    for node in model_nodes(manifest).values():
        projection_deps = {
            sources[dependency]["name"]
            for dependency in node["depends_on"]["nodes"]
            if dependency in sources and sources[dependency]["name"] in allowed_sources
        }
        if projection_deps:
            assert node["name"] in allowed_consumers
            observed.update(projection_deps)

    assert observed == allowed_sources


def test_active_state_pipeline_has_no_dynamic_snapshot_lookup():
    manifest = load_production_manifest()
    ownership_tags = set(GRAPH["ownership_classes"])
    for node in model_nodes(manifest).values():
        if ownership_tags.isdisjoint(node["tags"]):
            continue
        executable = re.sub(r"--[^\n]*", "", node["raw_code"])
        assert "adapter.get_relation" not in executable
        assert "adapter.load_relation" not in executable
