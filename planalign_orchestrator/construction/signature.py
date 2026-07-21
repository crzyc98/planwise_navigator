"""Observable construction signatures and executed work schedules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConstructionSignature:
    """Comparable record of a resolved orchestrator construction."""

    entry_point: str
    runner_kind: str
    database_path: str
    dbt_project_dir: str | None
    thread_count: int
    initialization_policy: str
    installed_hook_names: tuple[str, ...]
    execution_engine: str

    @property
    def signature_hash(self) -> str:
        """Hash semantic construction while excluding run-specific identity."""
        payload = {
            "runner_kind": self.runner_kind,
            "project_relationship": (
                "shared" if self.dbt_project_dir is None else "overlay"
            ),
            "thread_count": self.thread_count,
            "initialization_policy": self.initialization_policy,
            "installed_hook_names": sorted(self.installed_hook_names),
            "execution_engine": self.execution_engine,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScheduleStep:
    """One dbt invocation in execution order."""

    seq: int
    command: str
    stage: str | None
    year: int | None
    runner_kind: str


@dataclass
class WorkSchedule:
    """Ordered dbt work executed by one simulation run."""

    steps: list[ScheduleStep] = field(default_factory=list)

    @property
    def invocation_count(self) -> int:
        return len(self.steps)

    def record(
        self,
        *,
        command: str,
        stage: str | None,
        year: int | None,
        runner_kind: str,
    ) -> ScheduleStep:
        step = ScheduleStep(
            seq=len(self.steps) + 1,
            command=command,
            stage=stage,
            year=year,
            runner_kind=runner_kind,
        )
        self.steps.append(step)
        return step
