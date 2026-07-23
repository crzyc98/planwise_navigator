"""Per-invocation dbt timing capture for the run-cost profile (FR-003, FR-009).

Wraps a live ``DbtRunner`` instance's ``execute_command`` by runtime composition
— the product module is never modified. Every dbt subprocess the orchestrator
spawns flows through that one method (``run_models`` delegates to it), so one
wrap point captures the whole run. ``dbt/target/run_results.json`` is rewritten
by every invocation, so it is snapshotted immediately after each call.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, List, Optional

from .profile_config import Invocation, ModelTiming, canonical_payload_fingerprint


def _parse_run_results(target_dir: Path) -> List[ModelTiming]:
    """Extract per-node compile/execute timings from run_results.json."""
    path = target_dir / "run_results.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    timings: List[ModelTiming] = []
    for result in payload.get("results", []):
        phases = {t.get("name"): t for t in result.get("timing", [])}

        def _seconds(phase: Optional[dict]) -> float:
            if (
                not phase
                or not phase.get("started_at")
                or not phase.get("completed_at")
            ):
                return 0.0
            from datetime import datetime

            def _parse(ts: str) -> Optional[datetime]:
                try:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    return None

            start = _parse(phase["started_at"])
            end = _parse(phase["completed_at"])
            if start is None or end is None:
                return 0.0
            return max((end - start).total_seconds(), 0.0)

        timings.append(
            ModelTiming(
                unique_id=result.get("unique_id", "unknown"),
                execute_s=_seconds(phases.get("execute")),
                compile_s=_seconds(phases.get("compile")),
                status=str(result.get("status", "unknown")),
            )
        )
    return timings


class InvocationRecorder:
    """Records every dbt invocation made through a wrapped DbtRunner instance."""

    def __init__(
        self,
        runner,
        *,
        before_invocation: Optional[Callable[[List[str]], None]] = None,
        snapshot_run_sql_to: Optional[Path] = None,
    ) -> None:
        self.invocations: List[Invocation] = []
        self.current_stage: Optional[str] = None
        self._runner = runner
        self._target_dir = Path(runner.working_dir) / "target"
        self._before_invocation = before_invocation
        self._snapshot_run_sql_to = snapshot_run_sql_to
        self._original = runner.execute_command
        runner.execute_command = self._timed_execute_command  # instance-only patch

    def unwrap(self) -> None:
        self._runner.execute_command = self._original

    @property
    def schedule_fingerprint(self) -> str:
        payload = [
            {
                "seq": invocation.seq,
                "year": invocation.year,
                "stage": invocation.stage,
                "command": invocation.command,
            }
            for invocation in self.invocations
        ]
        return canonical_payload_fingerprint(payload)

    @property
    def per_node_execution_fingerprint(self) -> str:
        payload = [
            {
                "seq": invocation.seq,
                "nodes": [
                    {
                        "unique_id": model.unique_id,
                        "status": model.status,
                    }
                    for model in invocation.models
                ],
            }
            for invocation in self.invocations
        ]
        return canonical_payload_fingerprint(payload)

    def _timed_execute_command(self, command_args, **kwargs):
        if self._before_invocation is not None:
            self._before_invocation(list(command_args))
        start = time.perf_counter()
        try:
            result = self._original(command_args, **kwargs)
        finally:
            wall = time.perf_counter() - start
            self._record(list(command_args), kwargs, wall)
        return result

    def _record(self, command_args: List[str], kwargs: dict, wall: float) -> None:
        seq = len(self.invocations)
        self.invocations.append(
            Invocation(
                seq=seq,
                year=kwargs.get("simulation_year"),
                stage=self.current_stage,
                command=" ".join(command_args),
                wall_s=wall,
                models=_parse_run_results(self._target_dir),
            )
        )
        if self._snapshot_run_sql_to is not None:
            self._snapshot_run_sql(seq)

    def _snapshot_run_sql(self, seq: int) -> None:
        """Copy dbt's executed-SQL artifacts (target/run) for probe replay."""
        import shutil

        run_dir = self._target_dir / "run"
        if not run_dir.exists():
            return
        dest = self._snapshot_run_sql_to / f"invocation_{seq:03d}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(run_dir, dest)
        results = self._target_dir / "run_results.json"
        if results.exists():
            shutil.copy2(results, dest / "run_results.json")


def attach_stage_tracking(orchestrator, recorder: InvocationRecorder) -> None:
    """Keep recorder.current_stage in sync via PRE_STAGE/POST_STAGE hooks."""
    from planalign_orchestrator.pipeline.hooks import Hook, HookType

    def _enter(context: dict) -> None:
        stage = context.get("stage")
        recorder.current_stage = getattr(stage, "value", str(stage))

    def _leave(context: dict) -> None:
        recorder.current_stage = None

    orchestrator.hook_manager.register_hook(
        Hook(hook_type=HookType.PRE_STAGE, callback=_enter, name="profile_stage_enter")
    )
    orchestrator.hook_manager.register_hook(
        Hook(hook_type=HookType.POST_STAGE, callback=_leave, name="profile_stage_leave")
    )
