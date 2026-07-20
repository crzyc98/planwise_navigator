"""#470 regression 4: invocation atomicity — partial writes roll back.

RED against the prototype: `execute_nodes` writes node-by-node on a
long-lived connection with no transaction, so a failure at node 2 leaves
node 1's writes behind.
"""

import duckdb
import pytest

from tests.fixtures.compiled_execution import table_names

pytestmark = [pytest.mark.fast, pytest.mark.orchestrator]


def _op(sql):
    return {"kind": "transactional_sql", "sql": sql}


def test_failure_mid_invocation_leaves_database_unchanged(seeded_db):
    from planalign_orchestrator.engine.transaction import execute_invocation_transaction

    before = table_names(seeded_db)
    operations = [
        _op("CREATE TABLE probe_new AS SELECT 1 AS v"),
        _op("INSERT INTO probe_existing VALUES (3)"),
        _op("SELECT * FROM table_that_does_not_exist"),  # fails here
    ]
    with pytest.raises(Exception) as excinfo:
        execute_invocation_transaction(
            database_path=seeded_db, connection_hooks=[], operations=operations
        )
    result = getattr(excinfo.value, "rollback_succeeded", None)
    assert result is True or result is None  # rollback outcome surfaced when typed

    assert table_names(seeded_db) == before, "partial writes must roll back"
    with duckdb.connect(str(seeded_db), read_only=True) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM probe_existing").fetchone()[0]
    assert rows == 2


def test_successful_invocation_commits_all_operations(seeded_db):
    from planalign_orchestrator.engine.transaction import execute_invocation_transaction

    outcome = execute_invocation_transaction(
        database_path=seeded_db,
        connection_hooks=["PRAGMA threads=4"],
        operations=[
            _op("CREATE TABLE probe_new AS SELECT 1 AS v"),
            _op("INSERT INTO probe_existing VALUES (3)"),
        ],
    )
    assert outcome.committed is True
    assert "probe_new" in table_names(seeded_db)
    with duckdb.connect(str(seeded_db), read_only=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM probe_existing").fetchone()[0] == 3


def test_connection_closed_after_failure(seeded_db):
    """The invocation connection must be released even on failure (no lock leak)."""
    from planalign_orchestrator.engine.transaction import execute_invocation_transaction

    with pytest.raises(Exception):
        execute_invocation_transaction(
            database_path=seeded_db,
            connection_hooks=[],
            operations=[_op("SELECT * FROM nope")],
        )
    # If the engine leaked its connection, this second writer would fail.
    with duckdb.connect(str(seeded_db)) as conn:
        conn.execute("CREATE TABLE lock_probe (x INTEGER)")
