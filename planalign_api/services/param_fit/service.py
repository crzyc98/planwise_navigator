"""Studio parameter fit & backtest service (#588): the one entry point routers use."""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import datetime, timezone
from typing import Any, Optional, Sequence
from uuid import uuid4

import yaml

from ...models.param_fit import (
    TERMINAL_STATUSES,
    ApplyPreview,
    ApplyRequest,
    FitOptionsModel,
    HistorySet,
    JobError,
    JobInputs,
    ParamFitJob,
    ParamFitJobSummary,
    ParamFitRequest,
    SplitPreview,
    ThresholdsModel,
)
from ...models.scenario import Scenario, ScenarioCreate
from ...storage.workspace_storage import WorkspaceStorage
from ..provenance.capture import config_fingerprint
from ..simulation.run_execution import scenario_pack_seeds, write_seeds
from . import apply as pack_apply
from .history import HistoryError, HistoryStore, UploadedFile
from .jobs import JobStore
from .results import (
    load_result,
    pack_summary,
    report_path,
    safe_read_pack_state,
)
from .runner import (
    CommandFactory,
    JobPaths,
    JobRunner,
    ProcessRegistry,
    build_cli_command,
    default_registry,
    terminate_orphan,
)

logger = logging.getLogger(__name__)
CANCEL_WAIT_SECONDS = 8.0

# Services are built per request; the check-then-launch of the one-backtest-
# per-workspace rule must still be atomic across them.
_launch_lock = threading.Lock()


class ParamFitError(Exception):
    """A request the service refuses; ``status`` is the HTTP equivalent."""

    def __init__(self, status: int, detail: str, **extra: Any):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.extra = extra


class ParamFitService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        *,
        max_jobs_per_workspace: int = 20,
        registry: ProcessRegistry = default_registry,
        command_factory: CommandFactory = build_cli_command,
    ):
        self.storage = storage
        root = storage.workspaces_root
        self.history = HistoryStore(root)
        self.jobs = JobStore(root)
        self.registry = registry
        self.max_jobs = max_jobs_per_workspace
        self.runner = JobRunner(
            self.jobs, registry, command_factory, on_finished=self._prune
        )

    # -- history -------------------------------------------------------------

    def create_history(
        self, workspace_id: str, files: Sequence[UploadedFile]
    ) -> HistorySet:
        self._require_workspace(workspace_id)
        try:
            return self.history.create(workspace_id, files)
        except HistoryError as exc:
            raise ParamFitError(422, str(exc)) from exc

    def list_history(self, workspace_id: str) -> list[HistorySet]:
        self._require_workspace(workspace_id)
        return self.history.list_sets(workspace_id)

    def get_history(self, workspace_id: str, history_id: str) -> HistorySet:
        self._require_workspace(workspace_id)
        try:
            history = self.history.get(workspace_id, history_id)
        except HistoryError as exc:
            raise ParamFitError(422, str(exc)) from exc
        if history is None:
            raise ParamFitError(404, "history set not found")
        return history

    def delete_history(self, workspace_id: str, history_id: str) -> None:
        self._require_workspace(workspace_id)
        in_use = any(
            job.inputs.history_id == history_id
            for job in self._jobs(workspace_id)
            if job.status not in TERMINAL_STATUSES
        )
        if in_use:
            raise ParamFitError(409, "a queued or running job uses this history set")
        if not self.history.delete(workspace_id, history_id):
            raise ParamFitError(404, "history set not found")

    # -- jobs ----------------------------------------------------------------

    def start(self, workspace_id: str, request: ParamFitRequest) -> ParamFitJob:
        self._require_workspace(workspace_id)
        history = self.get_history(workspace_id, request.history_id)
        scenario = self._require_scenario(workspace_id, request.base_scenario_id)
        split = self._split_for(history, request)
        merged = self.storage.get_merged_config(workspace_id, scenario.id) or {}
        job = self._new_job(workspace_id, request, history, scenario, merged, split)
        with _launch_lock:
            if request.mode == "backtest" and self._has_active_backtest(workspace_id):
                raise ParamFitError(
                    409,
                    "A backtest is already running in this workspace. Wait for it "
                    "to finish or cancel it before starting another.",
                )
            # Claimed before the record exists, so a concurrent read can never
            # mistake the new job for one interrupted by a restart.
            self.registry.claim(job.job_id)
            try:
                paths = self._prepare_inputs(job, merged, scenario)
                self.jobs.save(job)
            except BaseException:
                self.registry.release(job.job_id)
                shutil.rmtree(
                    self.jobs.job_dir(workspace_id, job.job_id), ignore_errors=True
                )
                raise
        self.runner.start(job, paths)
        return job

    def get(self, workspace_id: str, job_id: str) -> ParamFitJob:
        self._require_workspace(workspace_id)
        job = self._reconciled(workspace_id, job_id)
        if job.status == "completed":
            job.result = self._result(job)
        return job

    def list_jobs(self, workspace_id: str) -> list[ParamFitJobSummary]:
        self._require_workspace(workspace_id)
        return [self._summary(job) for job in self._jobs(workspace_id)]

    def cancel(self, workspace_id: str, job_id: str) -> ParamFitJob:
        self._require_workspace(workspace_id)
        job = self._reconciled(workspace_id, job_id)
        if job.status in TERMINAL_STATUSES:
            raise ParamFitError(409, f"job is already {job.status}")
        done = self.registry.cancel(job_id)
        if done is not None:
            done.wait(CANCEL_WAIT_SECONDS)
        return self._reconciled(workspace_id, job_id)

    def report(self, workspace_id: str, job_id: str, kind: str) -> str:
        job = self.get(workspace_id, job_id)
        pack_dir = self.jobs.pack_dir(workspace_id, job.job_id)
        path = report_path(pack_dir, kind) if job.status == "completed" else None
        if path is None:
            raise ParamFitError(404, f"no {kind} report for this job")
        return path.read_text(encoding="utf-8")

    # -- apply ---------------------------------------------------------------

    def apply_preview(
        self, workspace_id: str, job_id: str, source_scenario_id: str
    ) -> ApplyPreview:
        context = self._apply_context(workspace_id, job_id, source_scenario_id)
        return ApplyPreview(
            source_scenario_id=source_scenario_id,
            source_config_fingerprint=config_fingerprint(context["source_config"]),
            pack_id=context["state"].pack.manifest.pack_id,
            pack_fingerprint=context["state"].pack.manifest.fingerprint,
            backtest_verdict=(context["state"].backtest or {}).get("verdict"),
            required_acknowledgements=context["required"],
            diff=pack_apply.config_diff(
                context["source_config"], context["result_config"]
            ),
            seed_files=sorted(context["state"].pack.seed_files),
            suggested_name=self._suggested_name(workspace_id, context),
        )

    def apply(self, workspace_id: str, job_id: str, request: ApplyRequest) -> Scenario:
        context = self._apply_context(workspace_id, job_id, request.source_scenario_id)
        state = context["state"]
        self._check_fingerprints(request, context)
        missing = [
            ack for ack in context["required"] if ack not in request.acknowledgements
        ]
        if missing:
            raise ParamFitError(
                422,
                "Explicit acknowledgement required before applying this pack.",
                missing_acknowledgements=missing,
            )
        existing = [s.name for s in self.storage.list_scenarios(workspace_id)]
        if request.name.lower() in {name.lower() for name in existing}:
            raise ParamFitError(
                409,
                "scenario name already exists",
                suggested_name=pack_apply.unique_name(request.name, existing),
            )
        create = ScenarioCreate(
            name=request.name,
            description=request.description,
            config_overrides=context["overrides"],
            provenance=self._apply_provenance(job_id, request, context),
        )
        pack_dir = self.jobs.pack_dir(workspace_id, job_id)
        scenario = pack_apply.create_pack_scenario(
            self.storage, workspace_id, create, pack_dir
        )
        if scenario is None:
            raise ParamFitError(404, "workspace not found")
        logger.info(
            "Applied pack %s from job %s as scenario %s",
            state.pack.manifest.pack_id,
            job_id,
            scenario.id,
        )
        return scenario

    # -- internals -----------------------------------------------------------

    def _apply_context(
        self, workspace_id: str, job_id: str, source_scenario_id: str
    ) -> dict[str, Any]:
        job = self.get(workspace_id, job_id)
        if job.status != "completed":
            raise ParamFitError(409, "only a completed job's pack can be applied")
        source = self._require_scenario(workspace_id, source_scenario_id)
        pack_dir = self.jobs.pack_dir(workspace_id, job_id)
        state = safe_read_pack_state(pack_dir)
        if state is None:
            raise ParamFitError(409, "this job's pack is missing or unreadable")
        blocking = [
            reason
            for reason in (job.result.stale if job.result else [])
            if reason.reason in ("history_changed", "pack_modified")
        ]
        if blocking:
            raise ParamFitError(
                409,
                "The pack is stale and cannot be applied.",
                stale=[reason.model_dump() for reason in blocking],
            )
        overrides = pack_apply.build_overrides(
            dict(source.config_overrides), state, pack_dir
        )
        thin = (job.result.summary if job.result else {}).get("thin_count")
        return {
            "job": job,
            "source": source,
            "state": state,
            "overrides": overrides,
            "source_config": self.storage.get_merged_config(workspace_id, source.id)
            or {},
            "result_config": self.storage.merge_overrides(workspace_id, overrides)
            or {},
            "required": pack_apply.required_acknowledgements(state, thin),
        }

    def _check_fingerprints(
        self, request: ApplyRequest, context: dict[str, Any]
    ) -> None:
        stale: list[dict[str, str]] = []
        if request.pack_fingerprint != context["state"].pack.manifest.fingerprint:
            stale.append(
                {
                    "reason": "pack_modified",
                    "message": "The pack changed since you reviewed it.",
                }
            )
        if request.source_config_fingerprint != config_fingerprint(
            context["source_config"]
        ):
            stale.append(
                {
                    "reason": "source_scenario_changed",
                    "message": (
                        f"Scenario '{context['source'].name}' changed since you "
                        "reviewed the diff. Review it again."
                    ),
                }
            )
        if stale:
            raise ParamFitError(
                409, "The reviewed inputs are stale; nothing was created.", stale=stale
            )

    def _apply_provenance(
        self, job_id: str, request: ApplyRequest, context: dict[str, Any]
    ) -> dict[str, Any]:
        manifest = context["state"].pack.manifest
        return {
            "source": "param_pack",
            "param_fit_job_id": job_id,
            "pack_id": manifest.pack_id,
            "pack_fingerprint": manifest.fingerprint,
            "source_digest": manifest.source_digest,
            "snapshot_years": list(manifest.snapshot_years),
            "source_scenario_id": request.source_scenario_id,
            "source_config_fingerprint": request.source_config_fingerprint,
            "backtest_verdict": (context["state"].backtest or {}).get("verdict"),
            "acknowledgements": sorted(set(request.acknowledgements)),
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }

    def _suggested_name(self, workspace_id: str, context: dict[str, Any]) -> str:
        years = context["state"].pack.manifest.snapshot_years
        base = f"{context['source'].name} — fitted {years[0]}–{years[-1]}"
        existing = [s.name for s in self.storage.list_scenarios(workspace_id)]
        if base.lower() not in {name.lower() for name in existing}:
            return base[:100]
        return pack_apply.unique_name(base, existing)[:100]

    def _new_job(
        self,
        workspace_id: str,
        request: ParamFitRequest,
        history: HistorySet,
        scenario: Scenario,
        merged: dict[str, Any],
        split: Optional[SplitPreview],
    ) -> ParamFitJob:
        return ParamFitJob(
            job_id=f"fit_{uuid4().hex[:12]}",
            workspace_id=workspace_id,
            mode=request.mode,
            status="queued",
            created_at=datetime.now(timezone.utc),
            request=request,
            inputs=JobInputs(
                history_id=history.history_id,
                source_digest=history.source_digest,
                snapshots=history.snapshots,
                split=split,
                base_scenario_id=scenario.id,
                base_scenario_name=scenario.name,
                base_scenario_fingerprint=config_fingerprint(merged),
                moved_settings=moved_settings(request),
            ),
        )

    def _prepare_inputs(
        self, job: ParamFitJob, merged: dict[str, Any], scenario: Scenario
    ) -> JobPaths:
        """Snapshot the base scenario's effective config and seeds for the CLI."""
        inputs = self.jobs.inputs_dir(job.workspace_id, job.job_id)
        inputs.mkdir(parents=True, exist_ok=True)
        base_config = inputs / "base_config.yaml"
        base_config.write_text(
            yaml.safe_dump(merged, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        scenario_dir = self.storage._scenario_path(job.workspace_id, scenario.id)
        write_seeds(merged, inputs, scenario_pack_seeds(scenario_dir))
        return JobPaths(
            history_files=self.history.files_dir(
                job.workspace_id, job.inputs.history_id
            ),
            base_config=base_config,
            seeds_dir=inputs / "seeds",
            pack_dir=self.jobs.pack_dir(job.workspace_id, job.job_id),
            work_dir=self.jobs.work_dir(job.workspace_id, job.job_id),
        )

    def _split_for(
        self, history: HistorySet, request: ParamFitRequest
    ) -> Optional[SplitPreview]:
        if request.mode != "backtest":
            return None
        option = next(
            item
            for item in history.splits
            if item.holdout_years == request.holdout_years
        )
        if option.split is None:
            raise ParamFitError(422, option.error or "invalid backtest split")
        return option.split

    def _has_active_backtest(self, workspace_id: str) -> bool:
        return any(
            job.mode == "backtest" and job.status not in TERMINAL_STATUSES
            for job in self._jobs(workspace_id)
        )

    def _jobs(self, workspace_id: str) -> list[ParamFitJob]:
        return [self._reconcile(job) for job in self.jobs.list_jobs(workspace_id)]

    def _reconciled(self, workspace_id: str, job_id: str) -> ParamFitJob:
        job = self.jobs.load(workspace_id, job_id)
        if job is None:
            raise ParamFitError(404, f"job {job_id} not found")
        return self._reconcile(job)

    def _reconcile(self, job: ParamFitJob) -> ParamFitJob:
        """A non-terminal job this process does not own was interrupted."""
        if job.status in TERMINAL_STATUSES or self.registry.owns(job.job_id):
            return job

        def _interrupt(target: ParamFitJob) -> None:
            target.status = "failed"
            target.completed_at = datetime.now(timezone.utc)
            target.error = JobError(
                kind="interrupted",
                message=(
                    "Studio stopped while this job was running. Start it again "
                    "to get a result."
                ),
                status=500,
            )

        pid = self.jobs.recorded_process(job.workspace_id, job.job_id)
        if pid is not None:
            terminate_orphan(pid, job.job_id)
            self.jobs.clear_process(job.workspace_id, job.job_id)
        updated = self.jobs.update(job.workspace_id, job.job_id, _interrupt)
        self.jobs.remove_artifacts(job.workspace_id, job.job_id)
        return updated or job

    def _result(self, job: ParamFitJob):
        pack_dir = self.jobs.pack_dir(job.workspace_id, job.job_id)
        return load_result(
            job,
            pack_dir,
            current_history_digest=self.history.current_digest(
                job.workspace_id, job.inputs.history_id
            ),
            current_base_config=self.storage.get_merged_config(
                job.workspace_id, job.inputs.base_scenario_id
            ),
        )

    def _summary(self, job: ParamFitJob) -> ParamFitJobSummary:
        pack_id, verdict = (None, None)
        if job.status == "completed":
            pack_id, verdict = pack_summary(
                self.jobs.pack_dir(job.workspace_id, job.job_id)
            )
        return ParamFitJobSummary(
            job_id=job.job_id,
            mode=job.mode,
            status=job.status,
            created_at=job.created_at,
            completed_at=job.completed_at,
            history_id=job.inputs.history_id,
            snapshot_years=[snapshot.year for snapshot in job.inputs.snapshots],
            base_scenario_id=job.inputs.base_scenario_id,
            base_scenario_name=job.inputs.base_scenario_name,
            progress=job.progress,
            error=job.error,
            pack_id=pack_id,
            verdict=verdict,
        )

    def _prune(self, workspace_id: str) -> None:
        removed = self.jobs.prune_finished(
            workspace_id, self.max_jobs, protect=self.registry.owned()
        )
        if removed:
            logger.info("Pruned %d finished param-fit job(s)", len(removed))

    def _require_workspace(self, workspace_id: str) -> None:
        if self.storage.get_workspace(workspace_id) is None:
            raise ParamFitError(404, "workspace not found")

    def _require_scenario(self, workspace_id: str, scenario_id: str) -> Scenario:
        scenario = self.storage.get_scenario(workspace_id, scenario_id)
        if scenario is None:
            raise ParamFitError(404, f"scenario {scenario_id} not found")
        return scenario


def moved_settings(request: ParamFitRequest) -> dict[str, Any]:
    """Settings moved off their defaults, so a reviewer sees the dial was turned."""
    moved: dict[str, Any] = {}
    defaults = FitOptionsModel().model_dump()
    for key, value in request.fit_options.model_dump().items():
        if value != defaults[key]:
            moved[f"fit_options.{key}"] = value
    if request.mode == "backtest":
        default_thresholds = ThresholdsModel().model_dump()
        for family, pair in request.thresholds.model_dump().items():
            if pair != default_thresholds[family]:
                moved[f"thresholds.{family}"] = pair
    return moved
