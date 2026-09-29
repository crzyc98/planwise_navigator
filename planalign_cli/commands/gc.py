"""Reclaim local disk: prune archived Studio runs and aged var/ artifacts (#660).

Two artifact classes grow without bound on a dev machine:

* Studio scenario runs beyond ``storage.max_runs_per_scenario`` (the product
  path prunes on completion; this reclaims any backlog).
* Isolated DuckDBs and scratch trees under ``var/`` left by perf campaigns,
  ensembles, and validation harnesses. Their reports, campaign JSON, census
  parquet, and ensemble aggregates are the durable output and are kept.
* Backtest scratch (``workspaces/*/param_fits/*/work``) left by Studio fit &
  backtest jobs that were interrupted (#588). Their packs are kept.

Dry run by default; ``--yes`` deletes.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import typer
import yaml  # type: ignore[import]  # types-PyYAML not in CI deps
from rich.console import Console

from planalign_api.config import get_settings
from planalign_api.constants import DEFAULT_MAX_RUNS_PER_SCENARIO
from planalign_api.storage.workspace_storage import WorkspaceStorage

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_ARTIFACT_MAX_AGE_DAYS = 14

# (var/ subdirectory, glob) pairs naming reclaimable artifacts. Anything not
# matched -- reports, campaign.json, census parquet, ensemble.duckdb -- is kept.
ARTIFACT_RULES: tuple[tuple[str, str], ...] = (
    ("perf_profile", "**/*.duckdb*"),
    ("state_pipeline_validation", "**/*.duckdb*"),
    ("test-artifacts", "**/*.duckdb*"),
    ("ensembles", "*/seed_*.duckdb*"),
    ("ensembles", "*/seed_*_artifacts"),
    # Scratch trees from the opt-in compiled execution engine (#470).
    ("compiled_execution", "*"),
)


@dataclass(frozen=True)
class Reclaimable:
    path: Path
    size_bytes: int


def _path_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def find_stale_artifacts(var_dir: Path, max_age_days: int) -> List[Reclaimable]:
    """Return var/ artifacts matched by ARTIFACT_RULES and older than the cutoff."""
    cutoff = time.time() - max_age_days * 86400
    root = var_dir.resolve()
    found: Dict[Path, Reclaimable] = {}
    for subdir, pattern in ARTIFACT_RULES:
        base = var_dir / subdir
        if not base.is_dir():
            continue
        for path in base.glob(pattern):
            is_contained = root in path.resolve().parents
            if path.is_symlink() or not is_contained or path in found:
                continue
            if path.stat().st_mtime < cutoff:
                found[path] = Reclaimable(path, _path_bytes(path))
    return sorted(found.values(), key=lambda item: item.path)


def find_stale_param_fit_scratch(
    workspaces_root: Path, max_age_days: int
) -> List[Reclaimable]:
    """Studio fit/backtest ``work/`` trees older than the cutoff (#588).

    A finished job removes its own scratch; what remains belongs to a job the
    API was stopped in the middle of. Packs and job records are never touched.
    """
    if not workspaces_root.is_dir():
        return []
    cutoff = time.time() - max_age_days * 86400
    found = [
        Reclaimable(path, _path_bytes(path))
        for path in sorted(workspaces_root.glob("*/param_fits/*/work"))
        if path.is_dir() and not path.is_symlink() and path.stat().st_mtime < cutoff
    ]
    return found


def delete_artifacts(items: List[Reclaimable]) -> None:
    for item in items:
        if item.path.is_dir():
            shutil.rmtree(item.path)
        else:
            item.path.unlink(missing_ok=True)


def prune_workspace_runs(
    workspaces_root: Path, max_runs: int, dry_run: bool
) -> Dict[str, int]:
    """Apply the per-scenario run cap across every Studio workspace."""
    totals = {"runs": 0, "bytes": 0}
    if not workspaces_root.is_dir():
        return totals
    storage = WorkspaceStorage(workspaces_root=workspaces_root)
    for scenario_dir in sorted(workspaces_root.glob("*/scenarios/*")):
        if not scenario_dir.is_dir() or scenario_dir.is_symlink():
            continue
        workspace_id = scenario_dir.parent.parent.name
        result = storage.cleanup_old_runs(
            workspace_id, scenario_dir.name, max_runs=max_runs, dry_run=dry_run
        )
        totals["runs"] += result["removed_count"]
        totals["bytes"] += result["bytes_freed"]
    return totals


def load_storage_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.is_file():
        return {}
    data = yaml.safe_load(config_path.read_text()) or {}
    return data.get("storage") or {}


def _gb(size_bytes: int) -> str:
    return f"{size_bytes / 1024**3:.2f} GB"


def run_gc(
    yes: bool = False,
    older_than_days: int | None = None,
    workspaces_root: Path | None = None,
) -> None:
    """Report (or with ``yes``, delete) reclaimable runs and var/ artifacts."""
    storage_config = load_storage_config(
        PROJECT_ROOT / "config" / "simulation_config.yaml"
    )
    max_runs = int(
        storage_config.get("max_runs_per_scenario", DEFAULT_MAX_RUNS_PER_SCENARIO)
    )
    max_age = older_than_days
    if max_age is None:
        max_age = int(
            storage_config.get("artifact_max_age_days", DEFAULT_ARTIFACT_MAX_AGE_DAYS)
        )
    root = workspaces_root or get_settings().workspaces_root
    verb = "Removed" if yes else "Would remove"

    runs = prune_workspace_runs(root, max_runs, dry_run=not yes)
    console.print(
        f"{verb} {runs['runs']} Studio run(s) beyond {max_runs} per scenario "
        f"({_gb(runs['bytes'])})"
    )

    var_dir = PROJECT_ROOT / "var"
    artifacts = find_stale_artifacts(var_dir, max_age)
    artifact_bytes = sum(item.size_bytes for item in artifacts)
    by_subdir: Dict[str, List[int]] = {}
    for item in artifacts:
        subdir = item.path.relative_to(var_dir).parts[0]
        by_subdir.setdefault(subdir, []).append(item.size_bytes)
    for subdir, sizes in sorted(by_subdir.items()):
        console.print(f"  var/{subdir}: {len(sizes)} item(s), {_gb(sum(sizes))}")
    if yes:
        delete_artifacts(artifacts)
    console.print(
        f"{verb} {len(artifacts)} var/ artifact(s) older than {max_age} days "
        f"({_gb(artifact_bytes)})"
    )

    scratch = find_stale_param_fit_scratch(root, max_age)
    if yes:
        delete_artifacts(scratch)
    console.print(
        f"{verb} {len(scratch)} fit/backtest scratch tree(s) older than {max_age} "
        f"days ({_gb(sum(item.size_bytes for item in scratch))})"
    )
    if not yes:
        console.print("[yellow]Dry run.[/yellow] Re-run with --yes to delete.")


def gc_command(
    yes: bool = typer.Option(False, "--yes", help="Delete (default is a dry run)"),
    older_than_days: int
    | None = typer.Option(
        None,
        "--older-than-days",
        min=0,
        help="var/ artifact age cutoff (default: storage.artifact_max_age_days)",
    ),
    workspaces_root: Path
    | None = typer.Option(None, "--workspaces-root", help="Studio workspace root"),
) -> None:
    """Reclaim disk from old Studio runs and aged var/ campaign artifacts."""
    run_gc(yes, older_than_days, workspaces_root)
