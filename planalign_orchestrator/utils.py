#!/usr/bin/env python3
"""
Utility helpers for the Navigator Orchestrator.

Includes:
- ExecutionMutex: simple file-based mutex to prevent concurrent runs
- DatabaseConnectionManager: DuckDB connection/transaction helpers with retry
- time_block: context manager for timing code blocks
"""

from __future__ import annotations

import atexit
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, Generator, Optional, Set, TypeVar

import duckdb

T = TypeVar("T")


class ExecutionMutex:
    """File-based mutex to prevent concurrent simulation runs.

    This mirrors the existing behavior from `shared_utils.ExecutionMutex` to keep
    compatibility while enabling local consumption from the orchestrator package.
    """

    def __init__(self, lock_name: str = "simulation_execution"):
        self.lock_file = Path(f".{lock_name}.lock")
        self.acquired = False

    def acquire(self, timeout: int = 30) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if not self.lock_file.exists():
                    with open(self.lock_file, "w") as f:
                        f.write(f"pid:{os.getpid()}\n")
                        f.write(f"timestamp:{time.time()}\n")
                    self.acquired = True
                    atexit.register(self.release)
                    return True
                # Remove stale lock older than 1 hour
                if time.time() - self.lock_file.stat().st_mtime > 3600:
                    print("⚠️  Removing stale lock file")
                    self.lock_file.unlink()
                    continue
                # Otherwise wait and retry
                time.sleep(2)
            except Exception as e:  # pragma: no cover - defensive
                print(f"❌ Error acquiring lock: {e}")
                return False
        print(f"❌ Failed to acquire execution lock after {timeout} seconds")
        return False

    def release(self) -> None:
        if self.acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except Exception as e:  # pragma: no cover - defensive
                print(f"⚠️  Warning: Could not remove lock file: {e}")
            finally:
                self.acquired = False

    def __enter__(self) -> "ExecutionMutex":
        if not self.acquire():
            raise RuntimeError("Could not acquire execution lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


class DatabaseConnectionPool:
    """Thread-safe connection pool for DuckDB with deterministic execution support.

    Maintains a pool of reusable connections to avoid the overhead of creating
    new connections for every database operation (~10-50ms per connection).

    Features:
    - Thread-safe checkout/checkin with Lock
    - Deterministic mode support (PRAGMA threads=1) for reproducibility
    - Context manager pattern for automatic cleanup
    - Graceful pool exhaustion handling
    """

    def __init__(self, db_path: Path, pool_size: int = 1, deterministic: bool = True):
        """Initialize connection pool.

        Args:
            db_path: Path to DuckDB database file
            pool_size: Maximum number of connections to maintain (default: 1)
                      E079 Performance Fix: Reduced from 5 to 1 because sequential
                      pipeline execution doesn't benefit from pooling (only adds overhead)
            deterministic: If True, configure connections for deterministic behavior
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.deterministic = deterministic
        self._pool: Dict[str, duckdb.DuckDBPyConnection] = {}
        self._lock = Lock()
        self._in_use: Set[str] = set()

    def _create_connection(self, thread_id: str) -> duckdb.DuckDBPyConnection:
        """Create a new connection with proper configuration.

        Args:
            thread_id: Thread identifier for connection tracking

        Returns:
            Configured DuckDB connection
        """
        conn = duckdb.connect(str(self.db_path))

        if self.deterministic:
            # DETERMINISM FIX: Configure connection for reproducible results
            try:
                # Set deterministic threading and memory settings
                conn.execute("PRAGMA threads=1")  # Force single-threaded execution
                conn.execute("PRAGMA enable_external_access=false")  # Disable external access
                conn.execute("PRAGMA preserve_insertion_order=true")  # Preserve order
                conn.execute("PRAGMA memory_limit='1GB'")  # Conservative limit

                if thread_id:
                    # Set a deterministic seed based on thread ID for any internal RNG
                    import hashlib
                    thread_seed = int(hashlib.md5(thread_id.encode()).hexdigest()[:8], 16) % (2**31)
                    # Note: DuckDB doesn't have a direct seed setting, but this prepares for future use

            except Exception as e:
                # Pragma settings may not be available in all DuckDB versions
                print(f"⚠️ Warning: Could not set deterministic database settings: {e}")

        return conn

    @contextmanager
    def get_connection(self, thread_id: Optional[str] = None) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Context manager for connection checkout/checkin.

        Usage:
            with pool.get_connection(thread_id='worker_1') as conn:
                result = conn.execute("SELECT COUNT(*) FROM table").fetchall()

        Args:
            thread_id: Optional thread identifier for connection affinity

        Yields:
            DuckDB connection from pool

        Raises:
            RuntimeError: If connection pool is exhausted
        """
        thread_id = thread_id or 'main'
        conn = None

        # Checkout connection from pool
        with self._lock:
            # Reuse existing connection for this thread if available
            if thread_id in self._pool and thread_id not in self._in_use:
                conn = self._pool[thread_id]
                self._in_use.add(thread_id)
            else:
                # Create new connection if pool not full
                if len(self._pool) < self.pool_size:
                    conn = self._create_connection(thread_id)
                    self._pool[thread_id] = conn
                    self._in_use.add(thread_id)
                else:
                    # Try to find an available connection
                    available_threads = set(self._pool.keys()) - self._in_use
                    if available_threads:
                        thread_id = available_threads.pop()
                        conn = self._pool[thread_id]
                        self._in_use.add(thread_id)
                    else:
                        raise RuntimeError(
                            f"Connection pool exhausted (size={self.pool_size}). "
                            "All connections are in use."
                        )

        try:
            yield conn
        finally:
            # Return connection to pool
            with self._lock:
                self._in_use.discard(thread_id)

    def close_all(self) -> None:
        """Close all connections in pool and clear pool state."""
        with self._lock:
            for conn in self._pool.values():
                try:
                    conn.close()
                except Exception as e:
                    print(f"⚠️ Warning: Error closing connection: {e}")
            self._pool.clear()
            self._in_use.clear()


class DatabaseConnectionManager:
    """Database connection manager using connection pool for performance.

    Uses DatabaseConnectionPool to reuse connections and avoid the overhead
    of creating new connections for every operation (~10-50ms per connection).

    Notes:
    - Thread-safe connection pooling with automatic cleanup
    - Maintains deterministic mode for reproducible results
    - Context manager pattern for safe connection handling
    """

    def __init__(self, db_path: Optional[Path] = None, deterministic: bool = True):
        """Initialize DatabaseConnectionManager with connection pool.

        Args:
            db_path: Path to the database file. Defaults to dbt/simulation.duckdb
            deterministic: If True, configure connections for deterministic behavior
        """
        self.db_path = db_path or Path("dbt/simulation.duckdb")
        self.deterministic = deterministic
        self._pool = DatabaseConnectionPool(
            db_path=self.db_path,
            pool_size=5,
            deterministic=deterministic
        )
        # Register cleanup at exit to ensure connections are closed
        atexit.register(self.close_all)

    @contextmanager
    def get_connection(self, *, deterministic: Optional[bool] = None, thread_id: Optional[str] = None) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Get a connection from the pool.

        Args:
            deterministic: Ignored (set at pool initialization)
            thread_id: Optional thread identifier for connection affinity

        Yields:
            DuckDB connection from pool
        """
        # Note: deterministic parameter ignored after pool initialization
        # To change deterministic mode, create new ConnectionManager
        with self._pool.get_connection(thread_id=thread_id) as conn:
            yield conn

    @contextmanager
    def transaction(self, *, deterministic: bool = False, thread_id: Optional[str] = None) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Create a database transaction context using pooled connection.

        Args:
            deterministic: Ignored (set at pool initialization)
            thread_id: Optional thread identifier for connection affinity

        Yields:
            DuckDB connection with active transaction
        """
        with self._pool.get_connection(thread_id=thread_id) as conn:
            try:
                conn.begin()  # Start explicit transaction
                yield conn
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    # Rollback might fail if no transaction is active
                    pass
                raise

    def execute_with_retry(
        self,
        fn: Callable[[duckdb.DuckDBPyConnection], T],
        *,
        retries: int = 3,
        backoff_seconds: float = 0.5,
        deterministic: bool = False,
        thread_id: Optional[str] = None,
    ) -> T:
        """Execute a function against a connection with simple retry logic.

        Args:
            fn: Function to execute with database connection
            retries: Maximum number of retry attempts
            backoff_seconds: Base backoff time between retries
            deterministic: If True, use deterministic connection configuration
            thread_id: Optional thread identifier for connection isolation

        Returns:
            Result from the executed function
        """
        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt <= retries:
            try:
                with self.transaction(deterministic=deterministic, thread_id=thread_id) as conn:
                    return fn(conn)
            except Exception as e:  # pragma: no cover - external IO
                last_exc = e
                if attempt == retries:
                    break
                # DETERMINISM FIX: Use deterministic backoff in deterministic mode
                if deterministic:
                    # Use fixed backoff for deterministic behavior
                    sleep_time = backoff_seconds * (2**attempt)
                else:
                    # Add jitter for normal operation
                    import random
                    sleep_time = backoff_seconds * (2**attempt) * (0.5 + random.random() * 0.5)
                time.sleep(sleep_time)
                attempt += 1
        assert last_exc is not None
        raise last_exc

    def close_all(self) -> None:
        """Close all connections in the pool.

        Should be called during cleanup to release database connections.
        """
        self._pool.close_all()


@contextmanager
def time_block(label: str) -> Generator[None, None, None]:
    """Measure execution time of a block.

    Example:
        with time_block("load_year"):
            run_load()
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        dur = (time.perf_counter() - start) * 1000
        print(f"⏱️  {label}: {dur:.1f} ms")
