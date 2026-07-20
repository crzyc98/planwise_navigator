"""Frozen node-operation planning (#470). No semantic discovery at run time.

This module PLANS the adapter-equivalent statements for the repository's
four supported shapes; it never opens a connection. Execution happens in
``transaction.py`` inside one BEGIN/COMMIT per invocation. Source-schema
verification for incremental inserts happens in preflight via a read-only
probe; unresolvable drift is a typed delegation, not a runtime surprise.
"""

from __future__ import annotations

from typing import Any, List, Sequence

from .context import RelationState
from .preflight import HookPlan, KnownUnsupportedSemantics, Operation


def _q(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _target(state: RelationState) -> str:
    return f"{_q(state.schema)}.{_q(state.identifier)}"


def plan_node_operations(
    *,
    node: Any,
    sql: str,
    relation_state: RelationState,
    pre_hooks: Sequence[HookPlan],
    incremental_mode: bool,
    source_columns: Sequence[Any] = (),
) -> List[Operation]:
    """Freeze the complete DDL/DML sequence for one node."""
    materialized = getattr(node.config, "materialized", "view")
    uid = node.unique_id
    target = _target(relation_state)
    operations: List[Operation] = []

    def op(sql_text: str, phase: str) -> None:
        operations.append(
            Operation(kind="transactional_sql", sql=sql_text, node=uid, phase=phase)
        )

    if materialized == "ephemeral":
        return []

    for hook in pre_hooks:
        if hook.kind == "transactional_sql" and hook.rendered_sql:
            op(hook.rendered_sql, "pre_hook")

    if materialized == "view":
        if relation_state.relation_type == "table":
            op(f"DROP TABLE {target}", "model")
        op(f"CREATE OR REPLACE VIEW {target} AS (\n{sql}\n)", "model")
        return operations

    if materialized == "table":
        if relation_state.relation_type == "view":
            op(f"DROP VIEW {target}", "model")
        elif relation_state.relation_type == "table":
            op(f"DROP TABLE {target}", "model")
        op(f"CREATE TABLE {target} AS (\n{sql}\n)", "model")
        return operations

    # incremental
    if not incremental_mode:
        if relation_state.relation_type == "view":
            raise KnownUnsupportedSemantics(
                "materialization",
                f"{node.name}: incremental target is a view",
                affected_nodes=[uid],
            )
        op(f"CREATE TABLE {target} AS (\n{sql}\n)", "model")
        return operations

    target_columns = [column[0] for column in relation_state.columns]
    source_names = [
        column[0] if isinstance(column, (tuple, list)) else column
        for column in source_columns
    ]
    if source_names and sorted(source_names) != sorted(target_columns):
        raise KnownUnsupportedSemantics(
            "schema_change",
            f"{node.name}: select columns differ from target "
            f"({sorted(set(source_names) ^ set(target_columns))})",
            affected_nodes=[uid],
        )
    source_types = {
        column[0]: str(column[1]).upper()
        for column in source_columns
        if isinstance(column, (tuple, list)) and len(column) >= 2
    }
    target_types = {
        column[0]: str(column[1]).upper() for column in relation_state.columns
    }
    type_changes = {
        name: (target_types[name], source_types[name])
        for name in source_types.keys() & target_types.keys()
        if source_types[name] != target_types[name]
    }
    if type_changes:
        raise KnownUnsupportedSemantics(
            "schema_change",
            f"{node.name}: select types differ from target ({type_changes})",
            affected_nodes=[uid],
        )
    projection = ", ".join(_q(c) for c in target_columns)
    strategy = getattr(node.config, "incremental_strategy", None) or "append"
    if strategy == "append":
        op(
            f"INSERT INTO {target} ({projection}) "
            f"SELECT {projection} FROM (\n{sql}\n)",
            "model",
        )
        return operations
    if strategy == "delete+insert":
        tmp = _q(f"{relation_state.identifier}__planalign_tmp")
        op(f"CREATE OR REPLACE TEMP TABLE {tmp} AS (\n{sql}\n)", "model")
        unique_key = getattr(node.config, "unique_key", None) or []
        if isinstance(unique_key, str):
            unique_key = [unique_key]
        if unique_key:
            # Keys may be plain columns or SQL expressions (e.g.
            # "a || '_' || b"). DuckDB 1.0 lacks multi-column tuple-IN, so:
            # simple columns use a qualified EXISTS semi-join; a single
            # expression key uses single-column IN; anything else delegates.
            import re

            simple = [k for k in unique_key if re.fullmatch(r"\w+", k)]
            if len(simple) == len(unique_key):
                predicate = " AND ".join(
                    f"{tmp}.{_q(k)} = {target}.{_q(k)}" for k in unique_key
                )
                op(
                    f"DELETE FROM {target} WHERE EXISTS "
                    f"(SELECT 1 FROM {tmp} WHERE {predicate})",
                    "model",
                )
            elif len(unique_key) == 1:
                expr = f"({unique_key[0]})"
                op(
                    f"DELETE FROM {target} WHERE {expr} IN "
                    f"(SELECT DISTINCT {expr} FROM {tmp})",
                    "model",
                )
            else:
                raise KnownUnsupportedSemantics(
                    "incremental_strategy",
                    f"{node.name}: multi-key unique_key with expressions",
                    affected_nodes=[uid],
                )
        else:
            op(f"DELETE FROM {target}", "model")
        op(
            f"INSERT INTO {target} ({projection}) " f"SELECT {projection} FROM {tmp}",
            "model",
        )
        op(f"DROP TABLE {tmp}", "model")
        return operations
    raise KnownUnsupportedSemantics(
        "incremental_strategy", f"{node.name}: {strategy}", affected_nodes=[uid]
    )
