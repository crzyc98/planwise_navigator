"""Complete, fail-closed invocation preflight (#470, research R6/R7).

Everything semantic is decided here, before any write: command/option
parsing with an allowlist (no token silently ignored), hook classification
(pure ``log()`` is an informational lifecycle record, not a delegation
trigger), relation-state freezing, and per-node DDL/DML precomputation.
The output is either a frozen ``InvocationPlan`` or a typed
``KnownUnsupportedSemantics`` — the only object that authorizes dbt
delegation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .context import RelationState

HookKind = str  # connection_sql | transactional_sql | informational_log


class KnownUnsupportedSemantics(Exception):
    """Typed unsupported result; the sole authorization for dbt delegation."""

    def __init__(
        self,
        code: str,
        detail: str = "",
        *,
        phase: str = "preflight",
        affected_nodes: Sequence[str] = (),
    ) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.phase = phase
        self.affected_nodes = tuple(affected_nodes)


@dataclass(frozen=True)
class HookPlan:
    scope: str  # project_start | node_pre | node_post | project_end
    kind: HookKind
    rendered_sql: Optional[str] = None
    message: Optional[str] = None


@dataclass(frozen=True)
class InvocationRequest:
    sequence: int
    command: str
    select: Tuple[str, ...]
    exclude: Tuple[str, ...]
    full_refresh: bool
    simulation_year: Optional[int]
    dbt_vars: Dict[str, Any]
    stage: Optional[str] = None


@dataclass(frozen=True)
class Operation:
    kind: str  # transactional_sql
    sql: str
    node: Optional[str] = None
    phase: str = "model"  # pre_hook | model | post_hook


@dataclass(frozen=True)
class InvocationPlan:
    request: InvocationRequest
    context_digest: str
    bundle_digest: str
    nodes: Tuple[str, ...]  # executable nodes (ephemeral excluded)
    resolved_nodes: Tuple[str, ...]  # dbt-resolved selection (incl. ephemeral)
    connection_hooks: Tuple[str, ...]
    operations: Tuple[Operation, ...]
    end_logs: Tuple[str, ...]
    target_database: Path


# --------------------------------------------------------------------- #
# Command parsing (fail-closed)                                          #
# --------------------------------------------------------------------- #

_VALUE_FLAGS = {"--select", "-s", "--exclude", "--threads", "--vars"}
_BOOL_FLAGS = {"--full-refresh"}


def parse_run_invocation(
    command_args: Sequence[str],
    *,
    sequence: int,
    simulation_year: Optional[int],
    dbt_vars: Optional[Dict[str, Any]],
    stage: Optional[str] = None,
) -> InvocationRequest:
    """Parse a dbt-equivalent command; any unconsumed token is typed unsupported."""
    tokens = list(command_args)
    if not tokens:
        raise KnownUnsupportedSemantics("command", "empty command")
    command = tokens[0]
    if command != "run":
        raise KnownUnsupportedSemantics("command", f"'{command}' delegates to dbt")

    select: List[str] = []
    exclude: List[str] = []
    full_refresh = False
    bucket: Optional[List[str]] = None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in ("--select", "-s"):
            bucket = select
        elif token == "--exclude":
            bucket = exclude
        elif token == "--full-refresh":
            full_refresh = True
            bucket = None
        elif token == "--threads":
            index += 1  # value consumed; engine always executes sequentially
            bucket = None
        elif token.startswith("--"):
            raise KnownUnsupportedSemantics("option", f"unsupported flag {token}")
        elif bucket is not None:
            bucket.append(token)
        else:
            raise KnownUnsupportedSemantics("option", f"unexpected token {token}")
        index += 1

    if simulation_year is None or not dbt_vars:
        raise KnownUnsupportedSemantics(
            "option", "run invocation without simulation year/vars"
        )
    if full_refresh:
        raise KnownUnsupportedSemantics(
            "full_refresh",
            "full-refresh semantics require dbt (compiled SQL froze the "
            "incremental branch)",
        )
    merged = dict(dbt_vars)
    merged.setdefault("simulation_year", simulation_year)
    return InvocationRequest(
        sequence=sequence,
        command=command,
        select=tuple(select),
        exclude=tuple(exclude),
        full_refresh=full_refresh,
        simulation_year=simulation_year,
        dbt_vars=merged,
        stage=stage,
    )


_STATE_METHODS = ("state:", "result:", "source_status:")
_GRAPH_PREFIXES = ("@",)


def classify_selection_failure(
    select_tokens: Sequence[str], resolved_count: int
) -> KnownUnsupportedSemantics:
    """Zero-node or unresolvable selection → typed unsupported (never success)."""
    for token in select_tokens:
        if token.startswith(_STATE_METHODS) or token.startswith(_GRAPH_PREFIXES):
            return KnownUnsupportedSemantics(
                "selector_context", f"selector '{token}' needs context dbt owns"
            )
    if resolved_count == 0:
        return KnownUnsupportedSemantics(
            "empty_selection",
            f"selection {list(select_tokens)} resolved to zero nodes; "
            "dbt owns the no-node policy",
        )
    return KnownUnsupportedSemantics(
        "selector_context", f"selection {list(select_tokens)} could not be proven"
    )


# --------------------------------------------------------------------- #
# Hook classification                                                    #
# --------------------------------------------------------------------- #

_LOG_ONLY = re.compile(r"^\{\{\s*log\s*\(\s*(?P<args>.*?)\s*\)\s*\}\}$", re.S)
_PRAGMA_SET = re.compile(r"^\s*(PRAGMA|SET)\b", re.IGNORECASE)
_MESSAGE = re.compile(r"""^\s*(['"])(?P<msg>.*?)\1""", re.S)


@dataclass(frozen=True)
class ThisRelation:
    """`{{ this }}` with attribute access, matching dbt's Relation surface."""

    database: str
    schema: str
    identifier: str

    def __str__(self) -> str:
        return f'"{self.database}"."{self.schema}"."{self.identifier}"'


class _AdapterShim:
    """Supports the repo's `adapter.get_relation(...)` existence-guard idiom
    using preflight-frozen relation state; any other adapter use raises."""

    def __init__(self, relation_exists: bool) -> None:
        self._exists = relation_exists

    def get_relation(self, database=None, schema=None, identifier=None):
        return object() if self._exists else None

    def __getattr__(self, name: str):
        raise KnownUnsupportedSemantics("hook", f"adapter.{name} not modeled")


def classify_hook(
    hook: str,
    *,
    scope: str,
    dbt_vars: Dict[str, Any],
    incremental: bool,
    this: Any = "",
    relation_exists: bool = False,
) -> HookPlan:
    """Classify one hook string; unsupported constructs raise typed unsupported."""
    text = hook.strip()
    log_match = _LOG_ONLY.match(text)
    if log_match:
        message_match = _MESSAGE.match(log_match.group("args"))
        return HookPlan(
            scope=scope,
            kind="informational_log",
            message=message_match.group("msg")
            if message_match
            else log_match.group("args"),
        )
    rendered = _render_minimal(
        text,
        this=this,
        dbt_vars=dbt_vars,
        incremental=incremental,
        relation_exists=relation_exists,
    )
    if rendered is None or not rendered.strip():
        # guard evaluated false (e.g. is_incremental() on first build)
        return HookPlan(scope=scope, kind="transactional_sql", rendered_sql="")
    stripped = rendered.strip()
    if _PRAGMA_SET.match(stripped):
        return HookPlan(scope=scope, kind="connection_sql", rendered_sql=stripped)
    if stripped.upper().startswith("DELETE FROM") or stripped.upper() == "SELECT 1":
        return HookPlan(scope=scope, kind="transactional_sql", rendered_sql=stripped)
    raise KnownUnsupportedSemantics(
        "hook", f"unclassified hook effect: {stripped[:80]}"
    )


def _render_minimal(
    text: str,
    *,
    this: Any,
    dbt_vars: Dict[str, Any],
    incremental: bool,
    relation_exists: bool = False,
) -> Optional[str]:
    """Render with the minimal supported Jinja context; unknowns are typed."""
    import jinja2

    env = jinja2.Environment(undefined=jinja2.StrictUndefined)

    def _var(name: str, default: Any = None) -> Any:
        if name in dbt_vars:
            return dbt_vars[name]
        if default is None:
            raise KnownUnsupportedSemantics("hook", f"var('{name}') has no value")
        return default

    try:
        return env.from_string(text).render(
            this=this,
            var=_var,
            is_incremental=lambda: incremental,
            adapter=_AdapterShim(relation_exists),
        )
    except KnownUnsupportedSemantics:
        raise
    except jinja2.exceptions.UndefinedError as exc:
        raise KnownUnsupportedSemantics("hook", f"unsupported construct: {exc}")
    except jinja2.exceptions.TemplateError as exc:
        raise KnownUnsupportedSemantics("hook", f"failed to render: {exc}")


SUPPORTED_MATERIALIZATIONS = {"view", "table", "incremental", "ephemeral"}
SUPPORTED_STRATEGIES = {None, "append", "delete+insert"}


def freeze_node_operations(
    *,
    node: Any,
    sql: str,
    relation_state: RelationState,
    dbt_vars: Dict[str, Any],
    source_columns: Sequence[str] = (),
) -> Tuple[List[HookPlan], List[Operation]]:
    """Precompute every statement for one node; typed unsupported on any gap."""
    from .materialize import plan_node_operations  # frozen-op builder

    materialized = getattr(node.config, "materialized", "view")
    if materialized not in SUPPORTED_MATERIALIZATIONS:
        raise KnownUnsupportedSemantics(
            "materialization",
            f"{node.name}: {materialized}",
            affected_nodes=[node.unique_id],
        )
    strategy = getattr(node.config, "incremental_strategy", None)
    if materialized == "incremental" and strategy not in SUPPORTED_STRATEGIES:
        raise KnownUnsupportedSemantics(
            "incremental_strategy",
            f"{node.name}: {strategy}",
            affected_nodes=[node.unique_id],
        )
    incremental_mode = (
        materialized == "incremental" and relation_state.relation_type == "table"
    )
    hooks: List[HookPlan] = []
    raw_hooks = list(getattr(node.config, "pre_hook", []) or [])
    this = ThisRelation(
        relation_state.database, relation_state.schema, relation_state.identifier
    )
    for raw in raw_hooks:
        text = raw.sql if hasattr(raw, "sql") else str(raw)
        hooks.append(
            classify_hook(
                text,
                scope="node_pre",
                dbt_vars=dbt_vars,
                incremental=incremental_mode,
                this=this,
                relation_exists=relation_state.relation_type != "missing",
            )
        )
    post_hooks = list(getattr(node.config, "post_hook", []) or [])
    if post_hooks:
        raise KnownUnsupportedSemantics(
            "hook",
            f"{node.name}: post-hooks not modeled",
            affected_nodes=[node.unique_id],
        )
    operations = plan_node_operations(
        node=node,
        sql=sql,
        relation_state=relation_state,
        pre_hooks=hooks,
        incremental_mode=incremental_mode,
        source_columns=source_columns,
    )
    return hooks, operations
