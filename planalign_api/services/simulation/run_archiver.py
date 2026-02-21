"""Post-simulation run archival: metadata, database copy, Excel export, retention."""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ...constants import DEFAULT_MAX_RUNS_PER_SCENARIO
from ...storage.workspace_storage import WorkspaceStorage
from .result_handlers import export_results_to_excel

logger = logging.getLogger(__name__)


def archive_run(
    *,
    scenario_path: Path,
    run_id: str,
    scenario_id: str,
    scenario_name: str,
    workspace_id: str,
    config: Dict[str, Any],
    start_time: datetime,
    elapsed_seconds: float,
    start_year: int,
    end_year: int,
    events_generated: int,
    seed: int,
) -> Optional[Path]:
    """Persist run artifacts (config, metadata, database copy, Excel export).

    Args:
        scenario_path: Root path of the scenario directory.
        run_id: Unique run identifier.
        scenario_id: Scenario identifier.
        scenario_name: Human-readable scenario name.
        workspace_id: Workspace identifier.
        config: Full simulation configuration dict.
        start_time: When the simulation started.
        elapsed_seconds: Total runtime in seconds.
        start_year: First simulation year.
        end_year: Last simulation year.
        events_generated: Total events generated.
        seed: Random seed used.

    Returns:
        Path to the Excel export if created, else None.
    """
    run_dir = scenario_path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save config YAML
    _save_config(run_dir, config)

    # Save run metadata
    _save_metadata(
        run_dir,
        run_id=run_id,
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        workspace_id=workspace_id,
        start_time=start_time,
        elapsed_seconds=elapsed_seconds,
        start_year=start_year,
        end_year=end_year,
        events_generated=events_generated,
        seed=seed,
    )

    # Copy database snapshot
    _copy_database(scenario_path, run_dir)

    # Export to Excel
    excel_path = export_results_to_excel(
        scenario_path=scenario_path,
        scenario_name=scenario_name,
        config=config,
        seed=seed,
        run_dir=run_dir,
    )
    if excel_path:
        logger.info(f"Excel export created: {excel_path}")
    else:
        logger.warning("Excel export skipped or failed")

    return excel_path


def prune_old_runs(
    storage: WorkspaceStorage,
    workspace_id: str,
    scenario_id: str,
    config: Dict[str, Any],
) -> None:
    """Remove old runs beyond the retention limit.

    Args:
        storage: Workspace storage instance.
        workspace_id: Workspace identifier.
        scenario_id: Scenario identifier.
        config: Simulation configuration (reads ``storage.max_runs_per_scenario``).
    """
    try:
        storage_config = config.get("storage", {})
        max_runs = int(
            storage_config.get("max_runs_per_scenario", DEFAULT_MAX_RUNS_PER_SCENARIO)
        )
        cleanup_result = storage.cleanup_old_runs(
            workspace_id, scenario_id, max_runs=max_runs
        )
        if cleanup_result["removed_count"] > 0:
            freed_mb = cleanup_result["bytes_freed"] / (1024 * 1024)
            logger.info(
                f"Run retention: pruned {cleanup_result['removed_count']} old run(s), "
                f"freed {freed_mb:.1f}MB"
            )
    except Exception as e:
        logger.warning(f"Run retention cleanup failed (non-fatal): {e}")


# -- private helpers ----------------------------------------------------------


def _save_config(run_dir: Path, config: Dict[str, Any]) -> None:
    try:
        config_path = run_dir / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        logger.debug(f"Config YAML saved to: {config_path}")
    except Exception as e:
        logger.warning(f"Failed to save config YAML: {e}")


def _save_metadata(
    run_dir: Path,
    *,
    run_id: str,
    scenario_id: str,
    scenario_name: str,
    workspace_id: str,
    start_time: datetime,
    elapsed_seconds: float,
    start_year: int,
    end_year: int,
    events_generated: int,
    seed: int,
) -> None:
    run_metadata = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "workspace_id": workspace_id,
        "started_at": start_time.isoformat(),
        "completed_at": datetime.now().isoformat(),
        "duration_seconds": elapsed_seconds,
        "start_year": start_year,
        "end_year": end_year,
        "events_generated": events_generated,
        "seed": seed,
        "status": "completed",
    }
    try:
        metadata_path = run_dir / "run_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(run_metadata, f, indent=2)
        logger.debug(f"Run metadata saved to: {metadata_path}")
    except Exception as e:
        logger.warning(f"Failed to save run metadata: {e}")


def _copy_database(scenario_path: Path, run_dir: Path) -> None:
    db_src = scenario_path / "simulation.duckdb"
    if db_src.exists():
        db_dest = run_dir / "simulation.duckdb"
        try:
            shutil.copy2(db_src, db_dest)
            logger.debug(f"Database copied to: {db_dest}")
        except Exception as e:
            logger.warning(f"Failed to copy database to run directory: {e}")
