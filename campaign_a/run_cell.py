"""Campaign A execution harness (no scoring).

Run with ``python3 scripts/dev.py -- python -m campaign_a.run_cell ...``.
Only an explicit CLI invocation runs simulations; importing this module is inert.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

import yaml

from planalign_api.models.scenario import ScenarioCreate
from planalign_api.models.workspace import WorkspaceCreate
from planalign_api.routers import calibration
from planalign_api.services.file_service import FileService
from planalign_api.services.provenance.capture import config_fingerprint, sha256_file
from planalign_api.services.simulation import SimulationService
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_orchestrator.calibration_optimizer import (
    AutoCalibrationSettings,
    AutoCalibrator,
)
from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
)

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaign_a"
RUN_ROOT = Path("/tmp/nhcal")
Json = dict[str, Any]


@contextmanager
def execution_environment(
    directory: Path, database: Path | None = None
) -> Iterator[None]:
    """Keep router copies and all engine DB writes inside this cell (serial CLI)."""
    if database is not None and not database.parent.resolve().is_relative_to(
        directory.resolve()
    ):
        raise ValueError("Database escapes cell directory")
    previous_temp = tempfile.tempdir
    previous_database = os.environ.get("DATABASE_PATH")
    tempfile.tempdir = str(directory)
    if database is not None:
        os.environ["DATABASE_PATH"] = str(database)
    try:
        yield
    finally:
        tempfile.tempdir = previous_temp
        if previous_database is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = previous_database


STAGES = (
    "baseline",
    "prerequisite_repair",
    "hire_date_fix",
    "search_fix",
    "indexed_cola",
    "prior_hire_turnover",
    "turnover_indexed_3pct",
    "backfill_by_level",
    "two_dial",
    "promo_backfill",
)
# Analyst starting-pay growth assumption per stage. indexed_cola matches the
# 2% config COLA; 3% reflects typical US salary-structure and market wage growth.
SALARY_GROWTH_BY_STAGE = {
    "indexed_cola": 0.02,
    "turnover_indexed_3pct": 0.03,
    "backfill_by_level": 0.03,
    "two_dial": 0.03,
    "promo_backfill": 0.03,
}
# Amendment 2026-10-31b: calibration also solves starting-pay growth.
TWO_DIAL_STAGES = {"two_dial", "promo_backfill"}


def save_record(cell: Json, seed: int, stage: str, record: Json) -> None:
    """Preserve other stages/seeds and existing scorer fields."""
    path = CAMPAIGN / "cells" / f"{cell['id']}.json"
    payload = json.loads(path.read_text()) if path.exists() else dict(cell)
    payload.setdefault("runs", {}).setdefault(stage, {})[str(seed)] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def census_inputs(storage: WorkspaceStorage, workspace: str, census: Path) -> Json:
    service = FileService(storage.workspaces_root)
    ages = service.analyze_age_distribution(workspace, str(census))
    compensation = service.analyze_compensation_by_level(
        workspace, str(census), lookback_years=4
    )
    rows = compensation[
        "levels" if compensation["has_level_data"] else "suggested_levels"
    ]
    ranges = [
        {
            "level": row["level"],
            "name": row["name"],
            "min_compensation": int(
                float(row.get("min_compensation", row.get("suggested_min"))) + 0.5
            ),
            "max_compensation": int(
                float(row.get("max_compensation", row.get("suggested_max"))) + 0.5
            ),
        }
        for row in rows
    ]
    return {
        "age_analysis": ages,
        "compensation_analysis": compensation,
        "base_ranges": ranges,
    }


def prepare_workspace(
    cell: Json, seed: int, directory: Path, stage: str
) -> tuple[WorkspaceStorage, str, str, Json]:
    manifest = json.loads((CAMPAIGN / "census_manifest.json").read_text())[
        cell["shape"]
    ]
    source = Path(manifest["path"])
    if sha256_file(source)[0] != manifest["sha256"]:
        raise ValueError("Frozen synthetic census hash mismatch")
    storage = WorkspaceStorage(directory / "workspaces")
    config = yaml.safe_load((ROOT / "config/simulation_config.yaml").read_text())
    config["simulation"].update(
        start_year=2026,
        end_year=2030,
        random_seed=seed,
        target_growth_rate=cell["hc_target_pct"] / 100,
    )
    config["workforce"].update(
        total_termination_rate=cell["total_termination_rate"],
        new_hire_termination_rate=cell["new_hire_termination_rate"],
    )
    config.setdefault("compensation", {})["target_compensation_growth_percent"] = cell[
        "comp_target_pct"
    ]
    workspace = storage.create_workspace(
        WorkspaceCreate(name=f"Campaign A {cell['id']}"), config
    )
    census = Path(workspace.storage_path) / "census.parquet"
    shutil.copyfile(source, census)
    if sha256_file(census)[0] != manifest["sha256"]:
        raise ValueError("Copied synthetic census hash mismatch")
    config.setdefault("setup", {}).update(
        census_parquet_path=str(census),
        plan_year_start_date="2025-01-01",
        plan_year_end_date="2025-12-31",
    )
    inputs = census_inputs(storage, workspace.id, census)
    ages, ranges = inputs["age_analysis"], inputs["base_ranges"]
    config.setdefault("new_hire", {}).update(
        age_distribution=ages["distribution"], job_level_compensation=ranges
    )
    if stage in SALARY_GROWTH_BY_STAGE:
        config["new_hire"]["salary_growth_rate"] = SALARY_GROWTH_BY_STAGE[stage]
    storage.update_workspace(workspace.id, base_config=config)
    scenario = storage.create_scenario(
        workspace.id, ScenarioCreate(name="Campaign target")
    )
    return (
        storage,
        workspace.id,
        scenario.id,
        dict(inputs, census_sha256=manifest["sha256"]),
    )


def attest_config(record: Json, submitted: Json) -> Json:
    """Fail closed unless only the service's census path resolution changed."""
    recorded = yaml.safe_load(Path(record["config_path"]).read_text())
    expected = copy.deepcopy(submitted)
    original_path = expected["setup"]["census_parquet_path"]
    recorded_path = recorded["setup"]["census_parquet_path"]
    if original_path != recorded_path:
        expected["setup"]["census_parquet_path"] = str(
            Path(original_path).resolve(strict=True)
        )
    if expected != recorded:
        raise ValueError("Submitted/recorded config mismatch")
    manifest = json.loads(Path(record["provenance_path"]).read_text())
    fingerprint = config_fingerprint(recorded)
    artifacts = {
        item["logical_name"]: item["sha256"] for item in manifest["archive_artifacts"]
    }
    if (
        manifest["run_id"] != record["run_id"]
        or manifest["configuration"]["fingerprint"] != fingerprint
        or artifacts.get("config.yaml") != sha256_file(Path(record["config_path"]))[0]
        or config_fingerprint(submitted) != record["config_fingerprint"]
    ):
        raise ValueError("Config attestation mismatch")
    return {
        "submitted_config_fingerprint": config_fingerprint(submitted),
        "attested_config_fingerprint": fingerprint,
        "config_attestation": {
            "status": "verified",
            "submitted_census_path": original_path,
            "attested_census_path": recorded_path,
            "only_change": (
                "setup.census_parquet_path" if submitted != recorded else None
            ),
            "config_sha256": artifacts["config.yaml"],
        },
    }


def run_full(
    storage: WorkspaceStorage, workspace: str, scenario: str, record: Json
) -> None:
    run_id = str(uuid4())
    config = storage.get_merged_config(workspace, scenario)
    assert config is not None
    database = (
        storage._scenario_path(workspace, scenario)
        / "runs"
        / run_id
        / "simulation.duckdb"
    )
    record.update(
        status="running",
        run_id=run_id,
        database=str(database),
        config_path=str(database.parent / "config.yaml"),
        provenance_path=str(database.parent / "provenance.json"),
        config_fingerprint=config_fingerprint(config),
    )
    submitted = copy.deepcopy(config)
    record["submitted_config_fingerprint"] = record["config_fingerprint"]
    started = time.monotonic()
    try:
        with execution_environment(storage.workspaces_root.parent, database):
            asyncio.run(
                SimulationService(storage).execute_simulation(
                    workspace, scenario, run_id, config
                )
            )
        context = storage.get_scenario_read_context(workspace, scenario)
        if (
            str(context.result_run_id) != run_id
            or context.database_path.resolve() != database.resolve()
        ):
            raise RuntimeError(
                f"Full simulation did not publish completed run {run_id}; inspect {database.parent}"
            )
        record.update(attest_config(record, submitted))
        record["status"] = "completed"
    finally:
        record["seconds"] = time.monotonic() - started


def calibration_request(
    workspace: str,
    scenario: str,
    cell: Json,
    inputs: Json,
    config: Json,
    stage: str = "baseline",
) -> calibration.AutoCalibrationRequest:
    two_dial = stage in TWO_DIAL_STAGES
    return calibration.AutoCalibrationRequest(
        workspace_id=workspace,
        scenario_id=scenario,
        start_year=2026,
        end_year=2030,
        settings=AutoCalibrationSettings(
            search_mode="new_hire_scale",
            lever_fallback=False,
            target_workforce_growth=cell["hc_target_pct"] / 100,
            target_comp_growth=cell["comp_target_pct"] / 100,
            base_job_level_compensation=inputs["base_ranges"],
            solve_salary_growth=two_dial,
            max_iterations=12 if two_dial else 8,
        ),
        params=CalibrationParameterSet(
            new_hire_age_distribution=config["new_hire"]["age_distribution"],
            total_termination_rate=cell["total_termination_rate"],
            new_hire_termination_rate=cell["new_hire_termination_rate"],
        ),
    )


def record_outcome(
    record: Json,
    outcome: calibration.AutoCalibrationResult,
    settings: AutoCalibrationSettings,
) -> None:
    record["outcome"] = outcome.model_dump(mode="json")
    record["annual_predictions"] = [
        row.model_dump(mode="json") for row in outcome.results
    ]
    record["ranges"] = outcome.best_params.job_level_compensation
    record["scale_clamped"] = outcome.best_scale in (
        settings.scale_min,
        settings.scale_max,
    )


def calibrate_and_apply(
    storage: WorkspaceStorage,
    workspace: str,
    scenario: str,
    cell: Json,
    inputs: Json,
    record: Json,
    stage: str = "baseline",
) -> None:
    config = storage.get_merged_config(workspace, scenario)
    assert config is not None
    request = calibration_request(workspace, scenario, cell, inputs, config, stage)
    directory = storage.workspaces_root.parent
    with execution_environment(directory):
        target = calibration._materialize_target(request, storage)
    record.update(
        status="running",
        context=target.context.model_dump(mode="json"),
        database=str(target.database_path),
        config_path=str(target.config_path),
        settings=request.settings.model_dump(mode="json"),
    )
    started = time.monotonic()
    try:
        with execution_environment(directory, target.database_path):
            outcome = AutoCalibrator(
                CalibrationRun(
                    start_year=2026,
                    end_year=2030,
                    config_path=target.config_path,
                    database_path=target.database_path,
                    params=request.params,
                ),
                request.settings,
                threads=1,
            ).optimize()
        record_outcome(record, outcome, request.settings)
        result = calibration.apply_calibration(
            calibration.CalibrationApplyRequest(
                context=target.context,
                best_params=outcome.best_params,
                target_comp_growth_pct=outcome.target_comp_growth_pct,
            ),
            storage,
        )
        record["apply"] = result.model_dump(mode="json")
        if result.total_failed or not result.workspace_updated:
            raise RuntimeError("Calibration apply failed")
        record["status"] = "completed"
    finally:
        record["seconds"] = time.monotonic() - started


def execute_phase(
    cell: Json,
    seed: int,
    stage: str,
    record: Json,
    name: str,
    action: Callable[[], None],
) -> None:
    phase = record[name]
    phase.update(status="running", started_at=datetime.now(timezone.utc).isoformat())
    save_record(cell, seed, stage, record)
    try:
        action()
    except Exception as exc:
        phase.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        phase["completed_at"] = datetime.now(timezone.utc).isoformat()
        save_record(cell, seed, stage, record)


def run_cell(cell_id: str, seed: int, stage: str) -> Json:
    cells = json.loads((CAMPAIGN / "matrix.json").read_text())
    cell = next((row for row in cells if row["id"] == cell_id), None)
    if cell is None or seed not in cell["seeds"] or stage not in STAGES:
        raise ValueError("Unknown cell, unfrozen seed, or unsupported stage")
    path = CAMPAIGN / "cells" / f"{cell_id}.json"
    if path.exists() and str(seed) in json.loads(path.read_text()).get("runs", {}).get(
        stage, {}
    ):
        raise FileExistsError("Existing cell stage/seed record; refusing overwrite")
    directory = RUN_ROOT / cell_id / f"{stage}_seed_{seed}_v2"
    directory.mkdir(parents=True, exist_ok=False)
    record: Json = {
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "directory": str(directory),
        "baseline": {},
        "calibration": {},
        "applied": {},
    }
    started = time.monotonic()
    try:
        save_record(cell, seed, stage, record)
        storage, workspace, scenario, inputs = prepare_workspace(
            cell, seed, directory, stage
        )
        record.update(workspace_id=workspace, scenario_id=scenario, inputs=inputs)
        execute_phase(
            cell,
            seed,
            stage,
            record,
            "baseline",
            lambda: run_full(storage, workspace, scenario, record["baseline"]),
        )
        execute_phase(
            cell,
            seed,
            stage,
            record,
            "calibration",
            lambda: calibrate_and_apply(
                storage,
                workspace,
                scenario,
                cell,
                inputs,
                record["calibration"],
                stage,
            ),
        )
        execute_phase(
            cell,
            seed,
            stage,
            record,
            "applied",
            lambda: run_full(storage, workspace, scenario, record["applied"]),
        )
        record["status"] = "completed"
    except Exception as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        record.update(
            seconds=time.monotonic() - started,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        save_record(cell, seed, stage, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument(
        "--stage",
        required=True,
        choices=list(STAGES),
    )
    args = parser.parse_args()
    run_cell(args.cell, args.seed, args.stage)


if __name__ == "__main__":
    main()
