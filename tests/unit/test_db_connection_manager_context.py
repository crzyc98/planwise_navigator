"""Regression tests for the Studio publish failure (leaked read-write DB connection).

A completed Studio run failed at ``publish_current_result -> _validate_target`` with
``duckdb.ConnectionException: Can't open a connection to same database file with a
different configuration than existing connections``. Root cause: the Excel export created
a ``DatabaseConnectionManager`` (read-write pool) on the run DB and never released it, so a
later ``duckdb.connect(run_db, read_only=True)`` on the same file, in the same process,
was rejected.

The fix makes ``DatabaseConnectionManager`` a context manager that releases its pool on
exit, and the Excel export uses it via ``with``. These tests lock that behavior.
"""

import duckdb
import pytest

from planalign_orchestrator.utils import DatabaseConnectionManager


def _make_db(path) -> None:
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE t AS SELECT 42 AS x")
    con.close()


def test_context_manager_releases_pool_so_readonly_connect_succeeds(tmp_path):
    """After the ``with`` block, no read-write pool connection remains, so a read-only
    connection to the same file (as publish_current_result does) succeeds."""
    db = tmp_path / "run.duckdb"
    _make_db(db)

    with DatabaseConnectionManager(db, deterministic=False) as manager:
        with manager.get_connection() as conn:  # opens a read-write pool connection
            assert conn.execute("SELECT x FROM t").fetchone()[0] == 42

    # This is exactly what _validate_target does after the Excel export.
    ro = duckdb.connect(str(db), read_only=True)
    try:
        assert ro.execute("SELECT x FROM t").fetchone()[0] == 42
    finally:
        ro.close()


def test_open_pool_blocks_readonly_until_closed(tmp_path):
    """Documents the failure mode the fix prevents: an open read-write pool connection
    blocks a read-only connect to the same file, until the pool is released."""
    db = tmp_path / "run.duckdb"
    _make_db(db)

    manager = DatabaseConnectionManager(db, deterministic=False)
    try:
        with manager.get_connection() as conn:  # pool retains this connection open
            conn.execute("SELECT 1").fetchone()

        # Same-process, same-file, different access mode -> DuckDB rejects it.
        with pytest.raises(duckdb.Error):
            duckdb.connect(str(db), read_only=True)

        # Releasing the pool clears the conflict.
        manager.close_all()
        ro = duckdb.connect(str(db), read_only=True)
        ro.close()
    finally:
        manager.close_all()  # idempotent; ensures cleanup on any failure
