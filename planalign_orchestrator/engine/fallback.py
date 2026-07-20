"""In-process dbt delegation for the compiled engine (#470 hardened).

Every delegated dbt invocation is pinned to the run workspace: the generated
explicit profile (absolute database path — ambient ``DATABASE_PATH`` is
irrelevant), a fresh mutable ``--target-path`` under ``delegations/``, a
fresh ``--log-path``, and ``--threads 1`` (contract §3). Published bundles
are never passed as targets.

Terminology (spec FR-007): *delegation* is expected and typed (seed, build,
known-unsupported semantics found in preflight); an *unexpected fallback*
is a defensive late occurrence and must be zero across the acceptance
matrix. Generic execution errors never delegate.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence

from planalign_orchestrator.dbt_runner import DbtResult

from .workspace import DBT_DIR, RunArtifactWorkspace

logger = logging.getLogger(__name__)

RecordKind = Literal["delegation", "fallback"]


@dataclass
class FallbackRecord:
    """One invocation executed via the dbt path instead of the compiled path."""

    seq: int
    kind: RecordKind
    reason: str
    command: str
    year: Optional[int] = None
    wall_s: float = 0.0
    detail: str = ""


@dataclass
class RecordLog:
    """Run-scoped accumulator; read by the run summary and provenance."""

    records: List[FallbackRecord] = field(default_factory=list)

    def add(self, record: FallbackRecord) -> None:
        self.records.append(record)

    @property
    def delegations(self) -> List[FallbackRecord]:
        return [r for r in self.records if r.kind == "delegation"]

    @property
    def fallbacks(self) -> List[FallbackRecord]:
        return [r for r in self.records if r.kind == "fallback"]

    @property
    def fallback_count(self) -> int:
        """Unexpected fallbacks only (data-model rule; zero-fallback gate)."""
        return len(self.fallbacks)


def _vars_payload(
    simulation_year: Optional[int], dbt_vars: Optional[Dict[str, Any]]
) -> Optional[str]:
    merged: Dict[str, Any] = {}
    if simulation_year is not None:
        merged["simulation_year"] = simulation_year
    if dbt_vars:
        merged.update(dbt_vars)
    return json.dumps(merged) if merged else None


def build_delegation_args(
    command_args: Sequence[str],
    *,
    workspace: RunArtifactWorkspace,
    sequence: int,
    simulation_year: Optional[int] = None,
    dbt_vars: Optional[Dict[str, Any]] = None,
    threads: Optional[int] = None,
    target_dir: Optional[Path] = None,
    log_dir: Optional[Path] = None,
) -> List[str]:
    """Contract §3: fully explicit dbt arguments for one delegated invocation."""
    args: List[str] = list(command_args)
    args.extend(["--project-dir", str(DBT_DIR)])
    args.extend(["--profiles-dir", str(workspace.profiles_dir)])
    args.extend(
        ["--target-path", str(target_dir or workspace.new_delegation_dir(sequence))]
    )
    args.extend(["--log-path", str(log_dir or workspace.new_log_dir(sequence))])
    payload = _vars_payload(simulation_year, dbt_vars)
    if payload is not None:
        args.extend(["--vars", payload])
    if "--threads" not in args:
        args.extend(["--threads", str(threads or 1)])
    return args


def invoke_dbt_delegated(
    command_args: Sequence[str],
    *,
    workspace: RunArtifactWorkspace,
    sequence: int,
    db_manager: Optional[Any] = None,
    simulation_year: Optional[int] = None,
    dbt_vars: Optional[Dict[str, Any]] = None,
    threads: Optional[int] = None,
    target_dir: Optional[Path] = None,
    manifest: Optional[Any] = None,
) -> DbtResult:
    """Execute one dbt command in-process against the workspace's explicit DB.

    ``manifest`` skips dbt's project parse; callers must guarantee it was
    parsed with the exact same vars this invocation carries.
    """
    from dbt.cli.main import dbtRunner

    if db_manager is not None:
        workspace.assert_database(db_manager)
        try:
            db_manager.close_all()  # single-writer: release before dbt connects
        except Exception as exc:
            logger.warning("Non-fatal: close_all before delegation: %s", exc)

    args = build_delegation_args(
        command_args,
        workspace=workspace,
        sequence=sequence,
        simulation_year=simulation_year,
        dbt_vars=dbt_vars,
        threads=threads,
        target_dir=target_dir,
    )
    start = time.perf_counter()
    runner = dbtRunner(manifest=manifest) if manifest is not None else dbtRunner()
    result = runner.invoke(args)
    wall = time.perf_counter() - start

    success = bool(result.success)
    stderr = ""
    if not success and result.exception is not None:
        stderr = f"{type(result.exception).__name__}: {result.exception}"
    return DbtResult(
        success=success,
        stdout=f"[delegated dbt] {' '.join(command_args)}",
        stderr=stderr,
        execution_time=wall,
        return_code=0 if success else 1,
        command=list(command_args),
    )
