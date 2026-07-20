"""#470 T014: frozen node-operation planning (no connection, no discovery)."""

from types import SimpleNamespace

import pytest

from planalign_orchestrator.engine.context import RelationState
from planalign_orchestrator.engine.materialize import plan_node_operations
from planalign_orchestrator.engine.preflight import HookPlan, KnownUnsupportedSemantics

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def _node(name, materialized, *, strategy=None, unique_key=None):
    config = SimpleNamespace(
        materialized=materialized,
        incremental_strategy=strategy,
        unique_key=unique_key,
        pre_hook=[],
        post_hook=[],
    )
    return SimpleNamespace(unique_id=f"model.pkg.{name}", name=name, config=config)


def _state(name, relation_type, columns=()):
    return RelationState(
        database="db",
        schema="main",
        identifier=name,
        relation_type=relation_type,
        columns=tuple(columns),
    )


def _sqls(ops):
    return [o.sql for o in ops]


def test_view_over_existing_table_drops_then_creates():
    ops = plan_node_operations(
        node=_node("v1", "view"),
        sql="SELECT 1",
        relation_state=_state("v1", "table"),
        pre_hooks=[],
        incremental_mode=False,
    )
    assert _sqls(ops)[0].startswith('DROP TABLE "main"."v1"')
    assert 'CREATE OR REPLACE VIEW "main"."v1"' in _sqls(ops)[1]


def test_table_rebuild_drops_existing():
    ops = plan_node_operations(
        node=_node("t1", "table"),
        sql="SELECT 1",
        relation_state=_state("t1", "table"),
        pre_hooks=[],
        incremental_mode=False,
    )
    assert _sqls(ops) == [
        'DROP TABLE "main"."t1"',
        'CREATE TABLE "main"."t1" AS (\nSELECT 1\n)',
    ]


def test_incremental_first_build_is_ctas():
    ops = plan_node_operations(
        node=_node("i1", "incremental", strategy="append"),
        sql="SELECT 1",
        relation_state=_state("i1", "missing"),
        pre_hooks=[],
        incremental_mode=False,
    )
    assert _sqls(ops) == ['CREATE TABLE "main"."i1" AS (\nSELECT 1\n)']


def test_incremental_append_orders_prehook_then_insert():
    hook = HookPlan(
        scope="node_pre",
        kind="transactional_sql",
        rendered_sql='DELETE FROM "main"."i2" WHERE simulation_year = 2025',
    )
    ops = plan_node_operations(
        node=_node("i2", "incremental", strategy="append"),
        sql="SELECT 1 AS a",
        relation_state=_state("i2", "table", [("a", "INTEGER", "YES")]),
        pre_hooks=[hook],
        incremental_mode=True,
        source_columns=("a",),
    )
    sqls = _sqls(ops)
    assert sqls[0].startswith("DELETE FROM")
    assert sqls[1].startswith('INSERT INTO "main"."i2" ("a")')


def test_delete_insert_sequence_with_key():
    ops = plan_node_operations(
        node=_node(
            "i3",
            "incremental",
            strategy="delete+insert",
            unique_key=["employee_id", "simulation_year"],
        ),
        sql="SELECT 1",
        relation_state=_state(
            "i3",
            "table",
            [("employee_id", "VARCHAR", "YES"), ("simulation_year", "INTEGER", "YES")],
        ),
        pre_hooks=[],
        incremental_mode=True,
        source_columns=("employee_id", "simulation_year"),
    )
    sqls = _sqls(ops)
    assert "CREATE OR REPLACE TEMP TABLE" in sqls[0]
    assert sqls[1].startswith('DELETE FROM "main"."i3" WHERE EXISTS')
    assert '"employee_id" = "main"."i3"."employee_id"' in sqls[1]
    assert sqls[2].startswith("INSERT INTO")
    assert sqls[3].startswith("DROP TABLE")


def test_delete_insert_expression_key_uses_raw_expression():
    ops = plan_node_operations(
        node=_node(
            "i6",
            "incremental",
            strategy="delete+insert",
            unique_key=["scenario_id || '_' || employee_id"],
        ),
        sql="SELECT 1",
        relation_state=_state(
            "i6",
            "table",
            [("scenario_id", "VARCHAR", "YES"), ("employee_id", "VARCHAR", "YES")],
        ),
        pre_hooks=[],
        incremental_mode=True,
        source_columns=("scenario_id", "employee_id"),
    )
    delete_sql = _sqls(ops)[1]
    assert "(scenario_id || '_' || employee_id)" in delete_sql
    assert '"scenario_id || ' not in delete_sql  # never quoted as identifier


def test_ephemeral_plans_nothing():
    assert (
        plan_node_operations(
            node=_node("e1", "ephemeral"),
            sql="SELECT 1",
            relation_state=_state("e1", "missing"),
            pre_hooks=[],
            incremental_mode=False,
        )
        == []
    )


def test_schema_drift_is_typed_unsupported():
    with pytest.raises(KnownUnsupportedSemantics) as excinfo:
        plan_node_operations(
            node=_node("i4", "incremental", strategy="append"),
            sql="SELECT 1 AS a, 2 AS b",
            relation_state=_state("i4", "table", [("a", "INTEGER", "YES")]),
            pre_hooks=[],
            incremental_mode=True,
            source_columns=("a", "b"),
        )
    assert excinfo.value.code == "schema_change"


def test_schema_type_drift_is_typed_unsupported():
    with pytest.raises(KnownUnsupportedSemantics) as excinfo:
        plan_node_operations(
            node=_node("i4", "incremental", strategy="append"),
            sql="SELECT CAST('2025-01-01' AS TIMESTAMP) AS changed_at",
            relation_state=_state("i4", "table", [("changed_at", "DATE", "YES")]),
            pre_hooks=[],
            incremental_mode=True,
            source_columns=(("changed_at", "TIMESTAMP"),),
        )
    assert excinfo.value.code == "schema_change"


def test_unknown_strategy_is_typed_unsupported():
    with pytest.raises(KnownUnsupportedSemantics) as excinfo:
        plan_node_operations(
            node=_node("i5", "incremental", strategy="merge"),
            sql="SELECT 1",
            relation_state=_state("i5", "table", [("a", "INTEGER", "YES")]),
            pre_hooks=[],
            incremental_mode=True,
        )
    assert excinfo.value.code == "incremental_strategy"
