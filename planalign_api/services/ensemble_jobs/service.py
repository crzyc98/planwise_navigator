"""Studio seed-ensemble jobs: estimate, start, track and cancel."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional
from uuid import uuid4

import anyio.from_thread

from planalign_ensemble.models import EnsembleSpec
from planalign_ensemble.planner import plan_ensemble

from ...models.ensemble_job import (
    TERMINAL_STATUSES,
    EnsembleError,
    EnsembleEstimate,
    EnsembleJob,
    EnsembleProgress,
    EnsembleRequest,
)
from ...models.scenario import Scenario
from ...storage.workspace_storage import WorkspaceStorage
from ..path_guard import PathGuardError, require_canonical_uuid
from ..simulation.run_execution import (
    prepare_dbt_project,
    scenario_pack_seeds,
    stamp_pack_provenance,
    validate_census,
    write_config,
    write_seeds,
)
from .runner import (
    CommandFactory,
    EnsembleJobRunner,
    EnsembleRegistry,
    JobPaths,
    build_cli_command,
    default_registry,
    terminate_orphan,
)
from .store import ENSEMBLE_DB_FILENAME, EnsembleJobStore, is_job_id

logger = logging.getLogger(__name__)

CANCEL_WAIT_SECONDS = 8.0
# A 5-year production-path run on the ~7k-employee reference census takes
# ~132-141s wall (docs/perf/run_cost_profile_production.md), so ~30s per
# simulated year. Used only when the scenario has no completed run to measure.
DEFAULT_SECONDS_PER_RUN_YEAR = 30.0

# Strong references keep running jobs from being garbage-collected mid-run.
_tasks: set[asyncio.Task[None]] = set()


class EnsembleJobError(Exception):
    """A request the service refuses; ``status`` is the HTTP equivalent."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class EnsembleJobService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        *,
        max_workers: int = 1,
        registry: EnsembleRegistry = default_registry,
        command_factory: CommandFactory = build_cli_command,
    ):
        self.storage = storage
        self.store = EnsembleJobStore(storage.workspaces_root)
        self.registry = registry
        self.max_workers = max_workers
        self.runner = EnsembleJobRunner(self.store, registry, command_factory)

    # -- requests ------------------------------------------------------------

    def estimate(
        self, workspace_id: str, scenario_id: str, request: EnsembleRequest
    ) -> EnsembleEstimate:
        scenario = self._require_scenario(workspace_id, scenario_id)
        return self._estimate(scenario, self._config(scenario), request.seed_count)

    def start(
        self, workspace_id: str, scenario_id: str, request: EnsembleRequest
    ) -> EnsembleJob:
        """Prepare inputs and queue the job on the API's event loop.

        Called from a FastAPI worker thread (or from the loop itself in tests),
        so input preparation never blocks the event loop.
        """
        scenario = self._require_scenario(workspace_id, scenario_id)
        config = self._config(scenario)
        job = self._new_job(
            scenario, self._estimate(scenario, config, request.seed_count)
        )
        self.registry.claim(job.job_id)
        try:
            paths = self._prepare_inputs(job, scenario, config)
            self.store.save(job)
            _launch(lambda: self.runner.run(job, paths))
        except BaseException:
            self.registry.release(job.job_id)
            shutil.rmtree(
                self.store.job_dir(workspace_id, job.job_id), ignore_errors=True
            )
            raise
        return job

    def get(self, workspace_id: str, job_id: str) -> EnsembleJob:
        self._require_workspace(workspace_id)
        job = self.store.load(workspace_id, job_id) if is_job_id(job_id) else None
        if job is None:
            raise EnsembleJobError(404, f"ensemble job {job_id} not found")
        return job

    def list_jobs(
        self, workspace_id: str, scenario_id: Optional[str] = None
    ) -> list[EnsembleJob]:
        self._require_workspace(workspace_id)
        jobs = self.store.list_jobs(workspace_id)
        if scenario_id is None:
            return jobs
        return [job for job in jobs if job.scenario_id == scenario_id]

    def cancel(self, workspace_id: str, job_id: str) -> EnsembleJob:
        job = self.get(workspace_id, job_id)
        if job.status in TERMINAL_STATUSES:
            raise EnsembleJobError(409, f"ensemble job is already {job.status}")
        outcome, done = self.registry.cancel(job_id)
        if outcome == "queued":
            # The runner will never begin this job, so its inputs can go now.
            self.store.update(workspace_id, job_id, _cancel_queued)
            self.store.remove_work(workspace_id, job_id)
        elif outcome == "not_owned":
            fail_interrupted_job(self.store, job)
        elif done is not None:
            done.wait(CANCEL_WAIT_SECONDS)
        return self.get(workspace_id, job_id)

    # -- internals -----------------------------------------------------------

    def _estimate(
        self, scenario: Scenario, config: dict[str, Any], seed_count: int
    ) -> EnsembleEstimate:
        simulation = config.get("simulation") or {}
        start_year = int(simulation.get("start_year", 2025))
        end_year = int(simulation.get("end_year", 2027))
        plan = plan_ensemble(
            EnsembleSpec(
                scenario_id=scenario.id,
                seed_count=seed_count,
                base_seed=int(simulation.get("random_seed", 42)),
                start_year=start_year,
                end_year=end_year,
            )
        )
        workers = min(self.max_workers, seed_count)
        horizon = end_year - start_year + 1
        measured = self._measured_seconds_per_year(scenario)
        per_year = measured if measured is not None else DEFAULT_SECONDS_PER_RUN_YEAR
        per_run = per_year * horizon
        return EnsembleEstimate(
            seed_count=seed_count,
            seeds=list(plan.seeds),
            start_year=start_year,
            end_year=end_year,
            run_count=plan.total_run_count,
            workers=workers,
            seconds_per_run=round(per_run, 1),
            estimated_seconds=round(
                per_run * math.ceil(plan.total_run_count / workers), 1
            ),
            time_basis="measured" if measured is not None else "default",
            estimated_disk_mib=round(plan.estimated_disk_mib, 1),
        )

    def _measured_seconds_per_year(self, scenario: Scenario) -> Optional[float]:
        """Seconds per simulated year of the scenario's latest completed run."""
        runs = self.storage._scenario_path(scenario.workspace_id, scenario.id) / "runs"
        latest: Optional[tuple[str, float]] = None
        for path in runs.glob("*/run_metadata.json") if runs.is_dir() else ():
            sample = _completed_run_sample(path)
            if sample is not None and (latest is None or sample[0] > latest[0]):
                latest = sample
        return latest[1] if latest is not None else None

    def _new_job(self, scenario: Scenario, estimate: EnsembleEstimate) -> EnsembleJob:
        return EnsembleJob(
            job_id=f"ens_{uuid4().hex[:12]}",
            workspace_id=scenario.workspace_id,
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            status="queued",
            seed_count=estimate.seed_count,
            seeds=estimate.seeds,
            start_year=estimate.start_year,
            end_year=estimate.end_year,
            estimate=estimate,
            created_at=datetime.now(timezone.utc),
            progress=EnsembleProgress(seeds_total=estimate.seed_count),
        )

    def _prepare_inputs(
        self, job: EnsembleJob, scenario: Scenario, config: dict[str, Any]
    ) -> JobPaths:
        """Snapshot the scenario's effective config, seeds and dbt overlay."""
        from planalign_orchestrator.exceptions import ConfigurationError

        work = self.store.work_dir(job.workspace_id, job.job_id)
        work.mkdir(parents=True, exist_ok=True)
        scenario_path = self.storage._scenario_path(job.workspace_id, scenario.id)
        try:
            validate_census(self.storage, config, scenario.id, job.workspace_id)
        except ConfigurationError as exc:
            raise EnsembleJobError(422, exc.message) from exc
        stamp_pack_provenance(config, scenario_path)
        # The CLI names the ensemble's scenario after the config file's stem.
        config_path = work / f"{scenario.id}.yaml"
        write_config(config, config_path)
        write_seeds(config, work, scenario_pack_seeds(scenario_path))
        return JobPaths(
            work_dir=work,
            config=config_path,
            dbt_project=prepare_dbt_project(work),
            output_root=work / "output",
            database=self.store.job_dir(job.workspace_id, job.job_id)
            / ENSEMBLE_DB_FILENAME,
        )

    def _config(self, scenario: Scenario) -> dict[str, Any]:
        config = self.storage.get_merged_config(scenario.workspace_id, scenario.id)
        if not config:
            raise EnsembleJobError(500, "failed to load the scenario configuration")
        return config

    def _require_workspace(self, workspace_id: str) -> None:
        try:
            require_canonical_uuid(workspace_id, label="workspace_id")
        except PathGuardError as exc:
            raise EnsembleJobError(404, "workspace not found") from exc
        if self.storage.get_workspace(workspace_id) is None:
            raise EnsembleJobError(404, "workspace not found")

    def _require_scenario(self, workspace_id: str, scenario_id: str) -> Scenario:
        self._require_workspace(workspace_id)
        try:
            require_canonical_uuid(scenario_id, label="scenario_id")
        except PathGuardError as exc:
            raise EnsembleJobError(404, f"scenario {scenario_id} not found") from exc
        scenario = self.storage.get_scenario(workspace_id, scenario_id)
        if scenario is None:
            raise EnsembleJobError(404, f"scenario {scenario_id} not found")
        return scenario


def fail_interrupted_ensembles(storage: WorkspaceStorage) -> int:
    """Mark every ensemble left queued or running by a restart as failed.

    Like ``fail_interrupted_simulations`` this assumes one API process.
    Returns the number of jobs marked failed.
    """
    store = EnsembleJobStore(storage.workspaces_root)
    failed = 0
    for workspace in storage.list_workspaces():
        # One unreadable workspace must not stop the API from starting.
        try:
            for job in store.list_jobs(workspace.id):
                if job.status not in TERMINAL_STATUSES:
                    fail_interrupted_job(store, job)
                    failed += 1
        except Exception:
            logger.exception("Could not check workspace %s for ensembles", workspace.id)
    return failed


def fail_interrupted_job(store: EnsembleJobStore, job: EnsembleJob) -> None:
    """Stop any orphaned child, drop scratch, and record why the job ended."""
    pid = store.recorded_process(job.workspace_id, job.job_id)
    if pid is not None:
        terminate_orphan(pid, job.job_id)
        store.clear_process(job.workspace_id, job.job_id)
    store.remove_work(job.workspace_id, job.job_id)
    was = job.status

    def _mark(target: EnsembleJob) -> None:
        if target.status in TERMINAL_STATUSES:
            return
        target.status = "failed"
        target.completed_at = datetime.now(timezone.utc)
        target.error = EnsembleError(
            kind="interrupted",
            message=(
                f"Studio restarted while this ensemble was {was}. "
                "Start it again to get a result."
            ),
        )

    store.update(job.workspace_id, job.job_id, _mark)
    logger.warning("Marked ensemble %s failed: interrupted while %s", job.job_id, was)


def _cancel_queued(job: EnsembleJob) -> None:
    if job.status == "queued":
        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)


def _completed_run_sample(path: Path) -> Optional[tuple[str, float]]:
    """(completed_at, seconds per year) for one completed run, else None."""
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        years = int(meta["end_year"]) - int(meta["start_year"]) + 1
        duration = float(meta["duration_seconds"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if meta.get("status") != "completed" or years < 1 or duration <= 0:
        return None
    return str(meta.get("completed_at") or ""), duration / years


def _launch(job: Callable[[], Coroutine[Any, Any, None]]) -> None:
    """Run ``job`` as a task on the event loop, from the loop or a worker thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        anyio.from_thread.run_sync(_spawn, job)
        return
    _spawn(job)


def _spawn(job: Callable[[], Coroutine[Any, Any, None]]) -> None:
    task = asyncio.get_running_loop().create_task(job())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
