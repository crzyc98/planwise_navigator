"""CompiledRunner: #470-hardened state machine behind the DbtRunner seam.

State machine (contract §2):
``RECEIVED → PREFLIGHTING → {UNSUPPORTED → DELEGATING | PLANNED → EXECUTING
→ {COMMITTED | ROLLED_BACK}}``. Delegation happens ONLY on typed
``KnownUnsupportedSemantics``; generic execution errors roll back, close,
and fail with node/phase/statement context — they are never replayed
through dbt. Every dbt-equivalent invocation is pinned to the run's
isolated workspace and explicit database.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

from planalign_orchestrator.dbt_runner import DbtResult, DbtRunner

from .context import (
    RenderContext,
    database_path_digest,
    inspect_relations,
    relation_state_digest,
    vars_digest,
)
from .fallback import FallbackRecord, RecordLog, invoke_dbt_delegated
from .preflight import (
    HookPlan,
    InvocationRequest,
    KnownUnsupportedSemantics,
    Operation,
    classify_hook,
    classify_selection_failure,
    freeze_node_operations,
    parse_run_invocation,
)
from .workspace import DBT_DIR, RunArtifactWorkspace
from .records import InvocationExecutionRecord

logger = logging.getLogger(__name__)


class CompiledRunner(DbtRunner):
    """Drop-in DbtRunner executing supported run invocations directly."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.record_log = RecordLog()
        self._seq = 0
        self._workspace: Optional[RunArtifactWorkspace] = None
        self._plan_cache = None
        self._project_hooks: Optional[Tuple[List[str], List[HookPlan]]] = None
        self.execution_records: List[InvocationExecutionRecord] = []
        self.run_id = getattr(self, "run_id", "")

    # ------------------------------------------------------------------ #
    # Workspace / plan cache                                             #
    # ------------------------------------------------------------------ #

    @property
    def workspace(self) -> RunArtifactWorkspace:
        if self._workspace is None:
            self._workspace = RunArtifactWorkspace.create(
                db_manager=self.db_manager,
                run_id=self.run_id or None,
            )
        return self._workspace

    @property
    def plan_cache(self):
        if self._plan_cache is None:
            from .plan_cache import PlanCache

            self._plan_cache = PlanCache(
                workspace=self.workspace, db_manager=self.db_manager
            )
        return self._plan_cache

    # ------------------------------------------------------------------ #
    # DbtRunner seam                                                     #
    # ------------------------------------------------------------------ #

    def execute_command(
        self,
        command_args: Sequence[str],
        *,
        description: str = "Running dbt command",
        simulation_year: Optional[int] = None,
        dbt_vars: Optional[Dict[str, Any]] = None,
        threads: Optional[int] = None,
        stream_output: bool = True,
        on_line: Optional[Any] = None,
        retry: bool = True,
        max_attempts: int = 3,
        log_performance: bool = True,
    ) -> DbtResult:
        args = list(command_args)
        seq = self._seq
        self._seq += 1

        try:
            request = parse_run_invocation(
                args,
                sequence=seq,
                simulation_year=simulation_year,
                dbt_vars=dbt_vars,
                stage=description,
            )
        except KnownUnsupportedSemantics as unsupported:
            return self._delegate(
                args,
                seq,
                unsupported,
                simulation_year=simulation_year,
                dbt_vars=dbt_vars,
                threads=threads,
            )

        try:
            plan = self._preflight(request)
        except KnownUnsupportedSemantics as unsupported:
            return self._delegate(
                args,
                seq,
                unsupported,
                simulation_year=simulation_year,
                dbt_vars=dbt_vars,
                threads=threads,
            )
        except Exception as exc:
            self._record_unclassified_failure(seq, request, exc)
            raise

        try:
            return self._execute_direct(args, seq, request, plan)
        except KnownUnsupportedSemantics as late:
            # Defensive late-preflight occurrence (contract: ROLLED_BACK_
            # UNSUPPORTED -> DELEGATING). Nothing was written (the transaction
            # rolled back or never began); counts as an unexpected fallback.
            late.phase = "execute"
            logger.error("[compiled] unexpected late unsupported: %s", late)
            return self._delegate(
                args,
                seq,
                late,
                simulation_year=simulation_year,
                dbt_vars=dbt_vars,
                threads=threads,
            )
        except Exception as exc:
            self._record_unclassified_failure(seq, request, exc, plan=plan)
            raise

    @staticmethod
    def classify_direct_result(planned_nodes: Sequence[str]) -> str:
        """Contract §2: SUCCEEDED requires at least one dbt-resolved node."""
        return "SUCCEEDED" if planned_nodes else "EMPTY"

    # ------------------------------------------------------------------ #
    # Preflight                                                          #
    # ------------------------------------------------------------------ #

    def _preflight(self, request: InvocationRequest):
        from .plan_cache import SelectorResolutionError

        cache = self.plan_cache
        self.workspace.assert_database(self.db_manager)
        try:
            unique_ids = cache.resolve_selection(
                request.select, request.exclude, request.dbt_vars
            )
        except SelectorResolutionError as exc:
            raise classify_selection_failure(request.select, resolved_count=-1) from exc
        if not unique_ids:
            raise classify_selection_failure(request.select, resolved_count=0)

        manifest = cache.manifest_for(request.dbt_vars)
        relations = []
        for uid in unique_ids:
            node = manifest.nodes[uid]
            relations.append(
                (node.database or "main", node.schema, node.alias or node.name)
            )
        cache.require_compile_state(request.dbt_vars, unique_ids)
        states = inspect_relations(self.workspace.database_path, relations)
        state_by_uid = dict(zip(unique_ids, states))

        connection_hooks, informational, end_logs = self._classified_project_hooks(
            request.dbt_vars
        )
        render = RenderContext(
            static_project=cache.static_context,
            database_path_digest=database_path_digest(self.workspace.database_path),
            profile_target="compiled_run",
            schema="main",
            command_semantics={
                "command": request.command,
                "select": list(request.select),
                "exclude": list(request.exclude),
                "full_refresh": request.full_refresh,
            },
            vars_digest=vars_digest(request.dbt_vars),
            selected_unique_ids=tuple(unique_ids),
            relation_state_digest=relation_state_digest(states),
            render_identity=cache.vars_fingerprint(request.dbt_vars),
        )
        bundle = cache.ensure_bundle(
            context_digest=render.context_digest,
            dbt_vars=request.dbt_vars,
            unique_ids=unique_ids,
        )

        operations: List[Operation] = []
        executable: List[str] = []
        from .plan_cache import load_bundle_sql

        for uid in unique_ids:
            node = manifest.nodes[uid]
            if getattr(node.config, "materialized", None) == "ephemeral":
                continue
            sql = load_bundle_sql(bundle, uid)
            state = state_by_uid[uid]
            source_columns = self._probe_source_columns(node, sql, state)
            _, node_ops = freeze_node_operations(
                node=node,
                sql=sql,
                relation_state=state,
                dbt_vars=request.dbt_vars,
                source_columns=source_columns,
            )
            operations.extend(node_ops)
            executable.append(uid)

        from .preflight import InvocationPlan

        return InvocationPlan(
            request=request,
            context_digest=render.context_digest,
            bundle_digest=bundle.context_digest,
            nodes=tuple(executable),
            resolved_nodes=tuple(unique_ids),
            connection_hooks=tuple(connection_hooks),
            operations=tuple(operations),
            end_logs=tuple(end_logs),
            target_database=self.workspace.database_path,
        )

    def _probe_source_columns(
        self, node, sql: str, state
    ) -> Tuple[Tuple[str, str], ...]:
        """Read-only source-schema probe for incremental existing targets.

        Needed only where an INSERT projection must be proven against the
        target schema; probe failure is typed schema_change (delegate),
        never a mid-transaction surprise.
        """
        import duckdb

        materialized = getattr(node.config, "materialized", "view")
        if materialized != "incremental" or state.relation_type != "table":
            return ()
        try:
            with duckdb.connect(
                str(self.workspace.database_path), read_only=True
            ) as conn:
                rows = conn.execute(
                    f"DESCRIBE SELECT * FROM (\n{sql}\n) LIMIT 0"
                ).fetchall()
            return tuple((r[0], r[1]) for r in rows)
        except duckdb.Error as exc:
            raise KnownUnsupportedSemantics(
                "schema_change",
                f"{node.name}: source schema unprovable ({str(exc)[:120]})",
                affected_nodes=[node.unique_id],
            ) from exc

    def _classified_project_hooks(self, dbt_vars: Dict[str, Any]):
        if self._project_hooks is None:
            project = yaml.safe_load((DBT_DIR / "dbt_project.yml").read_text()) or {}
            connection: List[str] = []
            informational: List[HookPlan] = []
            end_logs: List[str] = []
            for raw in project.get("on-run-start", []) or []:
                plan = classify_hook(
                    str(raw),
                    scope="project_start",
                    dbt_vars=dbt_vars,
                    incremental=False,
                )
                if plan.kind == "connection_sql" and plan.rendered_sql:
                    connection.append(plan.rendered_sql)
                elif plan.kind == "informational_log":
                    informational.append(plan)
            for raw in project.get("on-run-end", []) or []:
                plan = classify_hook(
                    str(raw), scope="project_end", dbt_vars=dbt_vars, incremental=False
                )
                if plan.kind == "informational_log" and plan.message:
                    end_logs.append(plan.message)
                elif plan.kind == "connection_sql" and plan.rendered_sql:
                    connection.append(plan.rendered_sql)
            self._project_hooks = (connection, informational, end_logs)
        return (*self._project_hooks,)

    # ------------------------------------------------------------------ #
    # Execution paths                                                    #
    # ------------------------------------------------------------------ #

    def _execute_direct(self, args, seq, request, plan) -> DbtResult:
        from .transaction import (
            TransactionExecutionError,
            execute_invocation_transaction,
        )

        started_at = datetime.now(timezone.utc)
        if not plan.nodes:
            if plan.resolved_nodes:
                # dbt-equivalent no-op: selection resolved only ephemeral
                # models, which dbt run also skips silently.
                logger.info(
                    "[compiled] seq=%d ephemeral-only selection, no-op (%s)",
                    seq,
                    ", ".join(u.split(".")[-1] for u in plan.resolved_nodes),
                )
                self.execution_records.append(
                    self._execution_record(
                        seq=seq,
                        request=request,
                        plan=plan,
                        mode="direct",
                        reason_code=None,
                        started_at=started_at,
                        elapsed=0.0,
                        outcome="success",
                        completed_count=0,
                    )
                )
                return DbtResult(
                    success=True,
                    stdout="[compiled engine] 0 executable node(s) (ephemeral-only selection)",
                    stderr="",
                    execution_time=0.0,
                    return_code=0,
                    command=list(args),
                )
            raise KnownUnsupportedSemantics(
                "empty_selection", "no resolved nodes in frozen plan"
            )
        if self.db_manager is not None:
            try:
                self.db_manager.close_all()
            except Exception as exc:
                logger.warning("close_all before direct execution: %s", exc)
        start = time.perf_counter()
        try:
            execute_invocation_transaction(
                database_path=plan.target_database,
                connection_hooks=plan.connection_hooks,
                operations=plan.operations,
            )
        except TransactionExecutionError as exc:
            from planalign_orchestrator.dbt_runner import classify_dbt_error

            context = (
                f"compiled invocation seq={seq} year={request.simulation_year} "
                f"node={exc.node} phase={exc.phase} rollback_succeeded="
                f"{exc.rollback_succeeded}: {exc.original} | statement: {exc.statement}"
            )
            logger.error("[compiled] %s", context)
            self.execution_records.append(
                self._execution_record(
                    seq=seq,
                    request=request,
                    plan=plan,
                    mode="direct",
                    reason_code=None,
                    started_at=started_at,
                    elapsed=time.perf_counter() - start,
                    outcome="failed",
                    completed_count=exc.operations_completed,
                    rollback_attempted=exc.rollback_attempted,
                    rollback_succeeded=exc.rollback_succeeded,
                    error_context={
                        "type": type(exc.original).__name__,
                        "node": exc.node,
                        "phase": exc.phase,
                        "statement": exc.statement,
                    },
                )
            )
            raise classify_dbt_error("", "", 1, context) from exc
        wall = time.perf_counter() - start
        for message in plan.end_logs:
            logger.info("[compiled][on-run-end] %s", message)
        summary = ", ".join(uid.split(".")[-1] for uid in plan.nodes)
        logger.info(
            "[compiled] seq=%d %d node(s) in %.1fs: %s",
            seq,
            len(plan.nodes),
            wall,
            summary,
        )
        self.execution_records.append(
            self._execution_record(
                seq=seq,
                request=request,
                plan=plan,
                mode="direct",
                reason_code=None,
                started_at=started_at,
                elapsed=wall,
                outcome="success",
                completed_count=len(plan.nodes),
            )
        )
        return DbtResult(
            success=True,
            stdout=f"[compiled engine] {len(plan.nodes)} node(s): {summary}",
            stderr="",
            execution_time=wall,
            return_code=0,
            command=list(args),
        )

    def _delegation_manifest(
        self,
        args: List[str],
        simulation_year: Optional[int],
        dbt_vars: Optional[Dict[str, Any]],
    ) -> Optional[Any]:
        """Reuse the project-defaults manifest for var-less seed/build
        delegations (parsed once, amortized across the run). `run`
        delegations always cold-parse — dbt's run task proved intolerant of
        a caller-supplied manifest here, and a stale render is never worth
        the risk. Failures degrade to a cold parse, never block delegation.
        """
        if not args or args[0] not in ("seed", "build"):
            return None
        if simulation_year is not None or dbt_vars:
            return None
        try:
            return self.plan_cache.manifest_for({})
        except Exception as exc:  # cold parse is always a safe fallback
            logger.warning("delegation manifest reuse unavailable: %s", exc)
            return None

    def _delegate(
        self,
        args: List[str],
        seq: int,
        unsupported: KnownUnsupportedSemantics,
        *,
        simulation_year: Optional[int],
        dbt_vars: Optional[Dict[str, Any]],
        threads: Optional[int],
    ) -> DbtResult:
        kind = "delegation" if unsupported.phase == "preflight" else "fallback"
        started_at = datetime.now(timezone.utc)
        result = invoke_dbt_delegated(
            args,
            workspace=self.workspace,
            sequence=seq,
            db_manager=self.db_manager,
            simulation_year=simulation_year,
            dbt_vars=dbt_vars,
            threads=threads,
            manifest=self._delegation_manifest(args, simulation_year, dbt_vars),
        )
        self.record_log.add(
            FallbackRecord(
                seq=seq,
                kind=kind,  # type: ignore[arg-type]
                reason=unsupported.code,
                command=" ".join(args),
                year=simulation_year,
                wall_s=result.execution_time,
                detail=unsupported.detail,
            )
        )
        self.execution_records.append(
            InvocationExecutionRecord(
                run_id=self.run_id or self.workspace.run_id,
                sequence=seq,
                year=simulation_year,
                stage=None,
                mode="dbt_delegation",
                reason_code=unsupported.code,
                context_digest=None,
                bundle_digest=None,
                planned_nodes=unsupported.affected_nodes,
                attempted_nodes=(),
                completed_nodes=(),
                target_database_digest=database_path_digest(
                    self.workspace.database_path
                ),
                started_at=started_at.isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_seconds=result.execution_time,
                rollback_attempted=unsupported.phase == "execute",
                rollback_succeeded=unsupported.phase == "execute",
                outcome="delegated" if result.success else "failed",
                error_context=None
                if result.success
                else {"type": "dbt_delegation", "detail": result.stderr[-500:]},
            )
        )
        if not result.success:
            from planalign_orchestrator.dbt_runner import (
                classify_dbt_error,
                extract_dbt_failure_detail,
            )

            raise classify_dbt_error(
                result.stdout,
                result.stderr,
                result.return_code,
                extract_dbt_failure_detail(self.working_dir),
            )
        return result

    def _execution_record(
        self,
        *,
        seq: int,
        request: InvocationRequest,
        plan: Any,
        mode: str,
        reason_code: Optional[str],
        started_at: datetime,
        elapsed: float,
        outcome: str,
        completed_count: int,
        rollback_attempted: bool = False,
        rollback_succeeded: bool = False,
        error_context: Optional[Dict[str, Any]] = None,
    ) -> InvocationExecutionRecord:
        completed = tuple(plan.nodes[:completed_count])
        return InvocationExecutionRecord(
            run_id=self.run_id or self.workspace.run_id,
            sequence=seq,
            year=request.simulation_year,
            stage=request.stage,
            mode=mode,
            reason_code=reason_code,
            context_digest=getattr(plan, "context_digest", None),
            bundle_digest=getattr(plan, "bundle_digest", None),
            planned_nodes=tuple(plan.nodes),
            attempted_nodes=tuple(plan.nodes),
            completed_nodes=completed,
            target_database_digest=database_path_digest(plan.target_database),
            started_at=started_at.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=elapsed,
            rollback_attempted=rollback_attempted,
            rollback_succeeded=rollback_succeeded,
            outcome=outcome,
            error_context=error_context,
        )

    def _record_unclassified_failure(
        self,
        seq: int,
        request: InvocationRequest,
        error: BaseException,
        *,
        plan: Optional[Any] = None,
    ) -> None:
        if any(record.sequence == seq for record in self.execution_records):
            return
        nodes = tuple(getattr(plan, "nodes", ()))
        target = getattr(plan, "target_database", self.workspace.database_path)
        self.execution_records.append(
            InvocationExecutionRecord(
                run_id=self.run_id or self.workspace.run_id,
                sequence=seq,
                year=request.simulation_year,
                stage=request.stage,
                mode="direct",
                reason_code=None,
                context_digest=getattr(plan, "context_digest", None),
                bundle_digest=getattr(plan, "bundle_digest", None),
                planned_nodes=nodes,
                attempted_nodes=(),
                completed_nodes=(),
                target_database_digest=database_path_digest(target),
                started_at=datetime.now(timezone.utc).isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_seconds=0.0,
                rollback_attempted=False,
                rollback_succeeded=False,
                outcome="failed",
                error_context={
                    "type": type(error).__name__,
                    "detail": str(error)[:500],
                },
            )
        )
