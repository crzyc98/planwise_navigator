from pathlib import Path

from navigator_orchestrator.utils import (DatabaseConnectionManager,
                                          ExecutionMutex, time_block)


def test_execution_mutex_context(tmp_path: Path):
    # Use a unique lock file per test run
    mtx = ExecutionMutex(lock_name=f"test_lock_{tmp_path.name}")
    with mtx:
        assert mtx.acquired is True
    assert mtx.acquired is False


def test_database_connection_manager_roundtrip(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    mgr = DatabaseConnectionManager(db_path=db_path)

    def _run(conn):
        conn.execute("CREATE TABLE t(i INTEGER)")
        conn.execute("INSERT INTO t VALUES (1), (2), (3)")
        return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]

    count = mgr.execute_with_retry(_run)
    assert count == 3


def test_time_block_prints(capsys):
    with time_block("unit_test_block"):
        pass
    out = capsys.readouterr().out
    assert "unit_test_block" in out
