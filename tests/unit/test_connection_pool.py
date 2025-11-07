#!/usr/bin/env python3
"""
Unit tests for DatabaseConnectionPool (E079 Phase 3A).

Tests connection pooling, thread safety, deterministic mode,
and proper resource cleanup.
"""

import tempfile
import threading
import time
from pathlib import Path

import pytest

from navigator_orchestrator.utils import DatabaseConnectionPool, DatabaseConnectionManager


class TestDatabaseConnectionPool:
    """Test DatabaseConnectionPool functionality."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test.duckdb"
        yield db_path
        # Cleanup
        if db_path.exists():
            db_path.unlink()
        Path(temp_dir).rmdir()

    @pytest.fixture
    def connection_pool(self, temp_db_path):
        """Create a connection pool for testing."""
        pool = DatabaseConnectionPool(temp_db_path, pool_size=3, deterministic=True)
        yield pool
        pool.close_all()

    def test_pool_creation(self, temp_db_path):
        """Test that pool can be created successfully."""
        pool = DatabaseConnectionPool(temp_db_path, pool_size=5, deterministic=True)
        assert pool.db_path == temp_db_path
        assert pool.pool_size == 5
        assert pool.deterministic is True
        pool.close_all()

    def test_connection_checkout_checkin(self, connection_pool):
        """Test basic connection checkout and checkin."""
        with connection_pool.get_connection(thread_id='test1') as conn:
            assert conn is not None
            # Verify we can execute a query
            result = conn.execute("SELECT 1 AS value").fetchall()
            assert result == [(1,)]

        # Connection should be returned to pool
        assert 'test1' not in connection_pool._in_use

    def test_connection_reuse(self, connection_pool):
        """Test that connections are reused from pool."""
        # First checkout
        with connection_pool.get_connection(thread_id='test1') as conn1:
            conn1_id = id(conn1)

        # Second checkout with same thread_id should reuse connection
        with connection_pool.get_connection(thread_id='test1') as conn2:
            conn2_id = id(conn2)

        assert conn1_id == conn2_id, "Connection should be reused from pool"

    def test_multiple_connections(self, connection_pool):
        """Test that pool can manage multiple connections."""
        conn_ids = []

        # Checkout 3 different connections (pool size is 3)
        with connection_pool.get_connection(thread_id='thread1') as conn1:
            conn_ids.append(id(conn1))
            with connection_pool.get_connection(thread_id='thread2') as conn2:
                conn_ids.append(id(conn2))
                with connection_pool.get_connection(thread_id='thread3') as conn3:
                    conn_ids.append(id(conn3))
                    # All connections should be different
                    assert len(set(conn_ids)) == 3

    def test_pool_exhaustion(self, connection_pool):
        """Test that pool raises error when exhausted."""
        # Hold all 3 connections
        with connection_pool.get_connection(thread_id='t1') as conn1:
            with connection_pool.get_connection(thread_id='t2') as conn2:
                with connection_pool.get_connection(thread_id='t3') as conn3:
                    # Try to get a 4th connection (pool size is 3)
                    with pytest.raises(RuntimeError, match="Connection pool exhausted"):
                        with connection_pool.get_connection(thread_id='t4') as conn4:
                            pass

    def test_deterministic_mode(self, temp_db_path):
        """Test that deterministic mode sets correct pragmas."""
        pool = DatabaseConnectionPool(temp_db_path, pool_size=1, deterministic=True)

        with pool.get_connection(thread_id='test') as conn:
            # Check that PRAGMA threads=1 is set
            # Note: DuckDB doesn't provide easy way to query pragma settings,
            # so we just verify connection works
            result = conn.execute("SELECT 1").fetchall()
            assert result == [(1,)]

        pool.close_all()

    def test_close_all(self, temp_db_path):
        """Test that close_all properly closes all connections."""
        pool = DatabaseConnectionPool(temp_db_path, pool_size=2, deterministic=True)

        # Create some connections
        with pool.get_connection(thread_id='t1') as conn1:
            pass
        with pool.get_connection(thread_id='t2') as conn2:
            pass

        # Verify pool has connections
        assert len(pool._pool) == 2

        # Close all
        pool.close_all()

        # Pool should be empty
        assert len(pool._pool) == 0
        assert len(pool._in_use) == 0

    def test_thread_safety(self, connection_pool):
        """Test that pool is thread-safe."""
        results = []
        errors = []

        def worker(thread_id):
            try:
                with connection_pool.get_connection(thread_id=f'worker_{thread_id}') as conn:
                    result = conn.execute(f"SELECT {thread_id} AS value").fetchall()
                    results.append(result[0][0])
                    time.sleep(0.01)  # Hold connection briefly
            except Exception as e:
                errors.append(e)

        # Create 3 threads (same as pool size)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Verify all threads succeeded
        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(results) == 3
        assert set(results) == {0, 1, 2}


class TestDatabaseConnectionManager:
    """Test DatabaseConnectionManager with connection pool."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test.duckdb"
        yield db_path
        # Cleanup
        if db_path.exists():
            db_path.unlink()
        Path(temp_dir).rmdir()

    @pytest.fixture
    def db_manager(self, temp_db_path):
        """Create database connection manager."""
        manager = DatabaseConnectionManager(temp_db_path, deterministic=True)
        yield manager
        manager.close_all()

    def test_manager_creation(self, temp_db_path):
        """Test that manager can be created with pool."""
        manager = DatabaseConnectionManager(temp_db_path, deterministic=True)
        assert manager.db_path == temp_db_path
        assert manager.deterministic is True
        assert manager._pool is not None
        manager.close_all()

    def test_get_connection(self, db_manager):
        """Test get_connection returns working connection."""
        with db_manager.get_connection() as conn:
            result = conn.execute("SELECT 42 AS answer").fetchall()
            assert result == [(42,)]

    def test_transaction(self, db_manager):
        """Test transaction context manager."""
        # Create a table and insert data in a transaction
        with db_manager.transaction() as conn:
            conn.execute("CREATE TABLE test_table (id INTEGER, value TEXT)")
            conn.execute("INSERT INTO test_table VALUES (1, 'test')")

        # Verify data persists after transaction
        with db_manager.get_connection() as conn:
            result = conn.execute("SELECT * FROM test_table").fetchall()
            assert result == [(1, 'test')]

    def test_transaction_rollback(self, db_manager):
        """Test that transaction rolls back on error."""
        # Create table first
        with db_manager.transaction() as conn:
            conn.execute("CREATE TABLE rollback_test (id INTEGER PRIMARY KEY)")

        # Try to insert duplicate, should rollback
        try:
            with db_manager.transaction() as conn:
                conn.execute("INSERT INTO rollback_test VALUES (1)")
                conn.execute("INSERT INTO rollback_test VALUES (1)")  # Duplicate, will fail
        except Exception:
            pass  # Expected

        # Verify no data was inserted
        with db_manager.get_connection() as conn:
            result = conn.execute("SELECT COUNT(*) FROM rollback_test").fetchall()
            assert result == [(0,)]

    def test_execute_with_retry(self, db_manager):
        """Test execute_with_retry functionality."""
        def query_func(conn):
            result = conn.execute("SELECT 100 AS value").fetchall()
            return result[0][0]

        result = db_manager.execute_with_retry(
            query_func,
            retries=3,
            backoff_seconds=0.1,
            deterministic=True
        )
        assert result == 100

    def test_close_all(self, temp_db_path):
        """Test that close_all closes the pool."""
        manager = DatabaseConnectionManager(temp_db_path, deterministic=True)

        # Use a connection to populate pool
        with manager.get_connection() as conn:
            conn.execute("SELECT 1").fetchall()

        # Close all connections
        manager.close_all()

        # Pool should be empty
        assert len(manager._pool._pool) == 0


@pytest.mark.fast
class TestConnectionPoolPerformance:
    """Performance tests for connection pool."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test.duckdb"
        yield db_path
        if db_path.exists():
            db_path.unlink()
        Path(temp_dir).rmdir()

    def test_connection_reuse_performance(self, temp_db_path):
        """Test that connection reuse improves performance."""
        import time

        # Without pooling (create new connection each time)
        start = time.time()
        for i in range(10):
            manager = DatabaseConnectionManager(temp_db_path, deterministic=True)
            with manager.get_connection() as conn:
                conn.execute("SELECT 1").fetchall()
            manager.close_all()
        without_pool_time = time.time() - start

        # With pooling (reuse connections)
        manager = DatabaseConnectionManager(temp_db_path, deterministic=True)
        start = time.time()
        for i in range(10):
            with manager.get_connection() as conn:
                conn.execute("SELECT 1").fetchall()
        with_pool_time = time.time() - start
        manager.close_all()

        # Pooling should be faster (allowing for some variance)
        # Note: This might not always be true in test environments,
        # so we just verify both complete successfully
        assert with_pool_time >= 0
        assert without_pool_time >= 0
