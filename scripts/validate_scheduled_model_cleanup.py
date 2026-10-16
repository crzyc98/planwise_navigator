"""Reproduce issue #875 parity with isolated synthetic three-year simulations.

Run ``baseline`` before applying the cleanup, then ``candidate`` and ``compare``
against the same artifact directory. No shared database or private census is used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from planalign_orchestrator import ConstructionSpec, build_orchestrator
from planalign_orchestrator.change_validation import compare_marts
from planalign_orchestrator.config import SimulationConfig, load_simulation_config
from tests.fixtures.invariant_simulation import (
    CENSUS_CSV,
    CONFIG_YAML,
    SHARED_DEV_DB,
    _database_environment,
    file_signature,
)
from tests.fixtures.plan_design_parameters.config import apply_two_design_parameters

ROOT = Path(__file__).resolve().parents[1]
CASES = ("standard", "broad_cutoff", "suppression", "escalation", "grandfathered")
EDGE_CASES = {
    "broad_cutoff": "broad_auto_enrollment_cutoff",
    "suppression": "new_hire_eligibility_suppression",
    "escalation": "auto_escalation_low_cap",
}
RELATIONS = (
    "fct_yearly_events",
    "fct_employer_match_events",
    "fct_workforce_snapshot",
    "int_enrollment_state_accumulator",
    "int_deferral_rate_state_accumulator",
    "int_employee_contributions",
    "int_employee_match_calculations",
    "int_employer_core_contributions",
    "int_plan_design_assignment_accumulator",
)
UNSCHEDULED_RELATIONS = {
    "int_workforce_active_for_events",
    "int_workforce_pre_enrollment",
    "int_eligibility_determination",
    "int_deferral_escalation_state_accumulator",
}


def prepare_config(case: str, directory: Path) -> SimulationConfig:
    """Resolve one checked-in synthetic input without changing global config."""
    config_path, census = CONFIG_YAML, CENSUS_CSV
    if case in EDGE_CASES:
        fixture = ROOT / "tests/fixtures/edge_config" / EDGE_CASES[case]
        config_path, census = fixture.with_suffix(".yaml"), fixture.with_suffix(".csv")
    config = load_simulation_config(config_path, env_overrides=False)
    config.simulation.end_year = 2027
    parquet = directory / "census.parquet"
    with duckdb.connect() as connection:
        connection.read_csv(str(census)).write_parquet(str(parquet))
    config.setup["census_parquet_path"] = str(parquet)
    if case == "broad_cutoff":
        config.enrollment.auto_enrollment.scope = "all_eligible_employees"
    if case == "grandfathered":
        config = apply_two_design_parameters(config)
    (directory / "config.json").write_text(config.model_dump_json(indent=2))
    return config


def run_case(phase: str, case: str, artifacts: Path) -> None:
    """Run the entire production pipeline with one dbt thread and fresh storage."""
    directory = artifacts / phase / case
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / "simulation.duckdb"
    if database.exists():
        raise ValueError(f"Refusing to reuse database: {database}")
    config = prepare_config(case, directory)
    with _database_environment(database):
        orchestrator = build_orchestrator(
            ConstructionSpec(
                config=config,
                database=database,
                dbt_artifacts_dir=directory / "dbt",
                threads=1,
                entry_point="invariant_test",
                validation_mode=True,
            )
        ).orchestrator
        orchestrator.execute_multi_year_simulation(start_year=2025, end_year=2027)
    with duckdb.connect(str(database), read_only=True) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        if phase == "baseline":
            # The product executor selects EVENT_GENERATION by tag; the legacy
            # eligibility model is only selected by the alternate workflow path.
            assert UNSCHEDULED_RELATIONS - {"int_eligibility_determination"} <= tables
        else:
            assert UNSCHEDULED_RELATIONS.isdisjoint(tables)
        assert (
            connection.execute(
                "SELECT COUNT(DISTINCT simulation_year) FROM fct_workforce_snapshot"
            ).fetchone()[0]
            == 3
        )
        if case == "grandfathered":
            assert (
                connection.execute(
                    "SELECT COUNT(DISTINCT plan_design_id) "
                    "FROM int_plan_design_assignment_accumulator"
                ).fetchone()[0]
                == 2
            )


def compare(artifacts: Path) -> None:
    """Require schema and duplicate-preserving, bidirectional row parity."""
    results = {}
    for case in CASES:
        base, candidate = (
            artifacts / phase / case for phase in ("baseline", "candidate")
        )
        configs = [
            json.loads((path / "config.json").read_text()) for path in (base, candidate)
        ]
        for config in configs:
            config["setup"].pop("census_parquet_path")
        assert configs[0] == configs[1]
        assert (base / "census.parquet").read_bytes() == (
            candidate / "census.parquet"
        ).read_bytes()
        results[case] = {}
        for relation in RELATIONS:
            audit_columns = ("created_at", "snapshot_created_at")
            if relation == "int_employee_contributions":
                audit_columns += ("calculated_at",)
            results[case].update(
                compare_marts(
                    base / "simulation.duckdb",
                    candidate / "simulation.duckdb",
                    [relation],
                    excluded=audit_columns,
                )
            )
    (artifacts / "parity.json").write_text(json.dumps(results, indent=2))
    assert all(
        diff == (0, 0) for result in results.values() for diff in result.values()
    ), results
    print(json.dumps(results, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("baseline", "candidate", "compare"))
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    args = parser.parse_args()
    artifacts = args.artifacts.resolve()
    shared_signature = file_signature(SHARED_DEV_DB)
    try:
        if args.phase == "compare":
            compare(artifacts)
        else:
            for case in args.cases:
                run_case(args.phase, case, artifacts)
    finally:
        assert file_signature(SHARED_DEV_DB) == shared_signature


if __name__ == "__main__":
    main()
