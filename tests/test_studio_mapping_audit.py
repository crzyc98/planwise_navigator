"""Characterize Studio mappings for #866; do not silently activate controls.

The opt-in integration test uses the same config/seed/CLI preparation as Studio,
with a checked-in synthetic census and one fresh database per setting.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import duckdb
import pytest
import yaml

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.services.simulation.run_execution import (
    build_command,
    build_env,
    prepare_dbt_project,
    write_config,
    write_seeds,
)
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_orchestrator.config import SimulationConfig, load_simulation_config
from planalign_orchestrator.config.export import to_dbt_vars

ROOT = Path(__file__).resolve().parents[1]
BASE_NEW_HIRE = {
    "strategy": "percentile",
    "target_percentile": 50,
    "compensation_variance_percent": 5,
    "level_distribution_mode": "adaptive",
    "level_distribution": [{"level": 1, "percentage": 1.0}],
    "level_market_adjustments": [{"level": 1, "adjustment_percent": 0}],
}
DISPLAYED_MATCH_POLICY = {
    "match_min_tenure_years": 0,
    "match_min_hours_annual": 1000,
    "match_require_year_end_active": True,
    "match_allow_terminated_new_hires": False,
    "match_allow_experienced_terminations": False,
    "match_allow_new_hires": True,
}
CASES = [
    ("new_hire", "strategy", "fixed"),
    ("new_hire", "target_percentile", 90),
    ("new_hire", "compensation_variance_percent", 30),
    ("new_hire", "level_distribution_mode", "fixed"),
    ("new_hire", "level_distribution", [{"level": 5, "percentage": 1.0}]),
    ("new_hire", "level_market_adjustments", [{"level": 1, "adjustment_percent": 50}]),
    ("compensation", "promotion_budget_percent", 25),
    ("compensation", "target_compensation_growth_percent", 25),
]


@pytest.mark.fast
def test_resolved_form_fixture_matches_real_export() -> None:
    fixture_path = (
        ROOT / "planalign_studio/components/config/fixtures/resolvedEngineInputs.json"
    )
    fixture = json.loads(fixture_path.read_text())
    variables = to_dbt_vars(SimulationConfig(**fixture["config"]))
    assert {key: variables[key] for key in fixture["variables"]} == fixture["variables"]


def _storage(tmp_path: Path) -> tuple[WorkspaceStorage, str, str]:
    config = yaml.safe_load((ROOT / "tests/fixtures/invariant_config.yaml").read_text())
    config["simulation"].update(end_year=2025, random_seed=42)
    config["optimization"]["e068c_threading"] = {
        "dbt_threads": 1,
        "event_shards": 1,
        "max_parallel_years": 1,
    }
    config["new_hire"] = copy.deepcopy(BASE_NEW_HIRE)
    config["compensation"].update(
        promotion_budget_percent=1.5, target_compensation_growth_percent=5
    )
    storage = WorkspaceStorage(tmp_path / "workspaces")
    workspace = storage.create_workspace(WorkspaceCreate(name="Mapping audit"), config)
    scenario = storage.create_scenario(workspace.id, ScenarioCreate(name="Synthetic"))
    return storage, workspace.id, scenario.id


def _prepare(
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario_id: str,
    run_dir: Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    run_dir.mkdir(parents=True)
    merged = storage.get_merged_config(workspace_id, scenario_id)
    assert merged is not None
    write_config(merged, run_dir / "config.yaml")
    write_seeds(merged, run_dir)
    config = load_simulation_config(run_dir / "config.yaml")
    seeds = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (run_dir / "seeds").glob("*.csv")
    }
    return to_dbt_vars(config), seeds


@pytest.mark.fast
@pytest.mark.parametrize("section,key,value", CASES)
def test_saved_setting_reaches_run_config_but_not_consumed_inputs(
    tmp_path: Path,
    section: str,
    key: str,
    value: Any,
) -> None:
    storage, workspace_id, scenario_id = _storage(tmp_path)
    baseline, baseline_seeds = _prepare(
        storage, workspace_id, scenario_id, tmp_path / "base"
    )
    storage.update_scenario(
        workspace_id, scenario_id, config_overrides={section: {key: value}}
    )
    saved = storage.get_scenario(workspace_id, scenario_id)
    assert saved is not None and saved.config_overrides[section][key] == value
    changed, changed_seeds = _prepare(
        storage, workspace_id, scenario_id, tmp_path / "changed"
    )
    run_config = yaml.safe_load((tmp_path / "changed/config.yaml").read_text())
    assert run_config[section][key] == value
    assert baseline_seeds == changed_seeds
    if key == "level_market_adjustments":
        assert changed.pop(key) == value
        baseline.pop(key)
    assert baseline == changed


def _outputs(database: Path) -> dict[str, Any]:
    result = {}
    with duckdb.connect(str(database), read_only=True) as connection:
        for table in ("fct_yearly_events", "fct_workforce_snapshot"):
            columns = [
                row[1]
                for row in connection.execute(
                    f"PRAGMA table_info('{table}')"
                ).fetchall()
            ]
            stable = [
                c
                for c in columns
                if c
                not in {
                    "created_at",
                    "updated_at",
                    "snapshot_created_at",
                    "event_id",
                    "event_uuid",
                }
            ]
            names = ", ".join(f'"{c}"' for c in stable)
            rows = connection.execute(f"SELECT {names} FROM {table}").fetchall()
            serialized = sorted(json.dumps(row, default=str) for row in rows)
            result[table] = {
                "rows": len(rows),
                "sha256": hashlib.sha256("\n".join(serialized).encode()).hexdigest(),
            }
        result["hire_count"] = connection.execute(
            "SELECT COUNT(*) FROM fct_yearly_events WHERE LOWER(event_type) = 'hire'"
        ).fetchone()[0]
    return result


def _run_production(run_dir: Path, end_year: int = 2025) -> Path:
    database = run_dir / "simulation.duckdb"
    project = prepare_dbt_project(run_dir)
    env = build_env(ROOT, database_path=database)
    env.update(
        DBT_TARGET_PATH=str(run_dir / "target"), DBT_LOG_PATH=str(run_dir / "logs")
    )
    with (run_dir / "output.log").open("w") as output:
        completed = subprocess.run(
            build_command(run_dir / "config.yaml", database, 2025, end_year, project),
            cwd=ROOT,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=600,
        )
    assert completed.returncode == 0, f"See {run_dir / 'output.log'}"
    return database


def _attach_synthetic_census(
    storage: WorkspaceStorage,
    workspace_id: str,
    census: Path,
) -> dict[str, Any]:
    with duckdb.connect() as connection:
        connection.read_csv(
            str(ROOT / "tests/fixtures/invariant_census.csv")
        ).write_parquet(str(census))
    base = storage.get_workspace(workspace_id).base_config
    base["setup"]["census_parquet_path"] = str(census)
    storage.update_workspace(workspace_id, base_config=base)
    return base


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("PLANALIGN_MAPPING_AUDIT") != "1",
    reason="Opt-in full production runs",
)
def test_production_mapping_ab(tmp_path: Path) -> None:
    storage, workspace_id, scenario_id = _storage(tmp_path)
    _attach_synthetic_census(storage, workspace_id, tmp_path / "synthetic.parquet")
    evidence = {}
    for case in [None, *CASES]:
        name = case[1] if case else "baseline"
        overrides = {case[0]: {case[1]: case[2]}} if case else {}
        storage.update_scenario(workspace_id, scenario_id, config_overrides=overrides)
        run_dir = tmp_path / name
        _prepare(storage, workspace_id, scenario_id, run_dir)
        database = _run_production(run_dir)
        evidence[name] = _outputs(database)
        (tmp_path / "evidence.json").write_text(json.dumps(evidence, indent=2))
        assert evidence[name]["hire_count"] > 0
        assert evidence[name] == evidence["baseline"], name


@pytest.mark.fast
@pytest.mark.parametrize("key", ["voluntary_enrollment_rate", "new_hire_opt_out_rate"])
@pytest.mark.parametrize("mode", ["missing", "demographic", "zero"])
def test_studio_flat_rate_clear_distinguishes_missing_null_zero(
    tmp_path: Path,
    key: str,
    mode: str,
) -> None:
    storage, workspace_id, scenario_id = _storage(tmp_path)
    base = storage.get_workspace(workspace_id).base_config
    base["enrollment"]["auto_enrollment"][key] = 0.73
    storage.update_workspace(workspace_id, base_config=base)
    payload = {} if mode == "missing" else {key: None if mode == "demographic" else 0}
    storage.update_scenario(
        workspace_id, scenario_id, config_overrides={"dc_plan": payload}
    )
    merged = storage.get_merged_config(workspace_id, scenario_id)
    assert merged["dc_plan"] == payload
    exported, _ = _prepare(storage, workspace_id, scenario_id, tmp_path / "run")
    if mode == "demographic":
        assert key not in exported
    else:
        assert exported[key] == (0.73 if mode == "missing" else 0)


def _new_hire_enrollment(database: Path) -> dict[str, Any]:
    with duckdb.connect(str(database), read_only=True) as connection:
        population = connection.execute(
            "SELECT simulation_year, COUNT(*), COUNT(*) FILTER (WHERE is_enrolled_flag) "
            "FROM fct_workforce_snapshot "
            "WHERE YEAR(employee_hire_date) = simulation_year GROUP BY 1 ORDER BY 1"
        ).fetchall()
        probabilities = connection.execute(
            "SELECT DISTINCT final_enrollment_probability FROM int_voluntary_enrollment_decision "
            "WHERE YEAR(employee_hire_date) = simulation_year ORDER BY 1"
        ).fetchall()
    return {
        "years": {
            str(row[0]): {"new_hires": row[1], "enrolled": row[2]} for row in population
        },
        "voluntary_probabilities": [float(row[0]) for row in probabilities],
    }


@pytest.mark.integration
@pytest.mark.parametrize("key", ["voluntary_enrollment_rate", "new_hire_opt_out_rate"])
@pytest.mark.skipif(
    os.environ.get("PLANALIGN_MAPPING_AUDIT") != "1",
    reason="Opt-in full production runs",
)
def test_production_enrollment_modes(tmp_path: Path, key: str) -> None:
    storage, workspace_id, scenario_id = _storage(tmp_path)
    base = _attach_synthetic_census(
        storage, workspace_id, tmp_path / "synthetic.parquet"
    )
    base["simulation"]["end_year"] = 2026
    auto = base["enrollment"]["auto_enrollment"]
    auto.update(enabled=key == "new_hire_opt_out_rate", **{key: 1.0})
    base["deferral_match_response"] = {"enabled": False}
    storage.update_workspace(workspace_id, base_config=base)
    evidence = {}
    for mode, payload in [
        ("missing", {}),
        ("demographic", {key: None}),
        ("zero", {key: 0}),
    ]:
        storage.update_scenario(
            workspace_id, scenario_id, config_overrides={"dc_plan": payload}
        )
        run_dir = tmp_path / mode
        _prepare(storage, workspace_id, scenario_id, run_dir)
        evidence[mode] = _new_hire_enrollment(_run_production(run_dir, end_year=2026))
        (tmp_path / "evidence.json").write_text(json.dumps(evidence, indent=2))
    _assert_enrollment_modes(evidence, key)


def _assert_enrollment_modes(evidence: dict[str, Any], key: str) -> None:
    for year in ("2025", "2026"):
        cohorts = {mode: result["years"][year] for mode, result in evidence.items()}
        assert all(result["new_hires"] > 0 for result in cohorts.values())
        if key == "voluntary_enrollment_rate":
            assert cohorts["zero"]["enrolled"] == 0
            assert (
                0 < cohorts["demographic"]["enrolled"] < cohorts["missing"]["enrolled"]
            )
        else:
            assert cohorts["missing"]["enrolled"] < cohorts["demographic"]["enrolled"]
            assert cohorts["demographic"]["enrolled"] <= cohorts["zero"]["enrolled"]
    if key == "voluntary_enrollment_rate":
        assert evidence["missing"]["voluntary_probabilities"] == [1.0]
        # The decision relation retains only will_enroll=true rows.
        assert evidence["zero"]["voluntary_probabilities"] == []


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("PLANALIGN_MAPPING_AUDIT") != "1",
    reason="Opt-in full production runs",
)
def test_production_displayed_match_eligibility(tmp_path: Path) -> None:
    """Legacy controls preserve outcomes; edited requirements govern matches."""
    storage, workspace_id, scenario_id = _storage(tmp_path)
    base = _attach_synthetic_census(
        storage, workspace_id, tmp_path / "synthetic.parquet"
    )
    base["simulation"]["end_year"] = 2026
    base["employer_match"].update(
        apply_eligibility=False,
        eligibility={
            "minimum_tenure_years": 3,
            "minimum_hours_annual": 500,
            "require_active_at_year_end": False,
            "allow_new_hires": False,
            "allow_terminated_new_hires": True,
            "allow_experienced_terminations": True,
        },
    )
    storage.update_workspace(workspace_id, base_config=base)
    evidence = {}
    for mode, payload in [
        ("legacy", {}),
        ("displayed", DISPLAYED_MATCH_POLICY),
        ("edited", {**DISPLAYED_MATCH_POLICY, "match_min_hours_annual": 10000}),
    ]:
        storage.update_scenario(
            workspace_id, scenario_id, config_overrides={"dc_plan": payload}
        )
        run_dir = tmp_path / mode
        variables, _ = _prepare(storage, workspace_id, scenario_id, run_dir)
        if payload:
            match = variables["employer_match"]
            assert match["apply_eligibility"] is True
            assert match["eligibility"]["minimum_tenure_years"] == 0
            assert match["eligibility"]["allow_terminated_new_hires"] is False
        database = _run_production(run_dir, end_year=2026)
        with duckdb.connect(str(database), read_only=True) as connection:
            evidence[mode] = connection.execute(
                "SELECT simulation_year, COUNT(*), SUM(employer_match_amount) "
                "FROM fct_workforce_snapshot GROUP BY simulation_year ORDER BY simulation_year"
            ).fetchall()
    assert evidence["displayed"] == evidence["legacy"]
    assert [row[0] for row in evidence["edited"]] == [2025, 2026]
    assert all(row[2] > 0 for row in evidence["legacy"])
    assert all(row[2] == 0 for row in evidence["edited"])
