"""Post-simulation run archival: metadata, database copy, Excel export, retention."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import duckdb
import yaml  # type: ignore[import]  # types-PyYAML not in CI deps

from planalign_core.constants import DATABASE_FILENAME, STATUS_COMPLETED

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
    run_dir: Optional[Path] = None,
    finalize_provenance: Optional[Callable[[], None]] = None,
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
        run_dir: Pre-created run directory (created early for log persistence).
            If omitted, computed as scenario_path/runs/run_id.

    Returns:
        Path to the Excel export if created, else None.
    """
    if run_dir is None:
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
    if finalize_provenance is not None:
        finalize_provenance()

    run_database = run_dir / DATABASE_FILENAME
    if not run_database.is_file():
        raise FileNotFoundError(f"run-local database is missing: {run_database}")
    try:
        with duckdb.connect(str(run_database), read_only=True) as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise RuntimeError("run-local database is not readable") from exc

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


def archive_failed_run(
    *,
    scenario_path: Path,
    run_id: str,
    scenario_id: str,
    scenario_name: str,
    workspace_id: str,
    config: Dict[str, Any],
    start_time: datetime,
    run_status: str,
    error_message: Optional[str] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    run_dir: Optional[Path] = None,
) -> None:
    """Persist metadata for a failed/cancelled run (feature 094).

    Without metadata the run directory is invisible to the run-history
    endpoints, which hides the simulation.log and the failure reason.
    No database copy or Excel export is attempted — results are not valid.
    """
    if run_dir is None:
        run_dir = scenario_path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    _save_config(run_dir, config)
    _save_metadata(
        run_dir,
        run_id=run_id,
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        workspace_id=workspace_id,
        start_time=start_time,
        elapsed_seconds=(datetime.now() - start_time).total_seconds(),
        start_year=start_year,
        end_year=end_year,
        events_generated=0,
        seed=config.get("simulation", {}).get("random_seed"),
        run_status=run_status,
        error_message=error_message,
    )
    logger.info(f"Archived {run_status} run metadata for {run_id}")


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
        _atomic_write_text(
            config_path,
            yaml.dump(config, default_flow_style=False, sort_keys=False),
        )
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
    start_year: Optional[int],
    end_year: Optional[int],
    events_generated: int,
    seed: Optional[int],
    run_status: str = STATUS_COMPLETED,
    error_message: Optional[str] = None,
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
        "status": run_status,
        "error_message": error_message,
    }
    metadata_path = run_dir / "run_metadata.json"
    _atomic_write_text(metadata_path, json.dumps(run_metadata, indent=2) + "\n")
    logger.debug(f"Run metadata saved to: {metadata_path}")


def _atomic_write_text(path: Path, payload: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
