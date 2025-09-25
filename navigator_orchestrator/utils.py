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
from typing import Callable, Generator, Optional, TypeVar

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


class DatabaseConnectionManager:
    """Lightweight DuckDB connection manager with transaction and retry helpers.

    Notes:
    - Creates a new connection for each context to avoid cross-thread issues.
    - Ensures thread-safe and deterministic connections for reproducible results.
    - Keeps surface minimal; can be extended for pooling if needed.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize DatabaseConnectionManager with optional database path.

        Args:
            db_path: Path to the database file. Defaults to dbt/simulation.duckdb
        """
        self.db_path = db_path or Path("dbt/simulation.duckdb")

    def get_connection(self, *, deterministic: bool = False, thread_id: Optional[str] = None) -> duckdb.DuckDBPyConnection:
        """Get a database connection, optionally with deterministic configuration.

        Args:
            deterministic: If True, configure connection for deterministic behavior
            thread_id: Optional thread identifier for connection isolation

        Returns:
            DuckDBPyConnection: A new database connection
        """
        conn = duckdb.connect(str(self.db_path))

        if deterministic:
            # DETERMINISM FIX: Configure connection for reproducible results
            try:
                # Set deterministic threading and memory settings
                conn.execute("PRAGMA threads=1")  # Force single-threaded execution within connection
                conn.execute("PRAGMA enable_external_access=false")  # Disable external access for consistency
                conn.execute("PRAGMA preserve_insertion_order=true")  # Preserve order for deterministic results

                # Set memory limits to ensure consistent resource usage
                conn.execute("PRAGMA memory_limit='1GB'")  # Conservative limit for deterministic behavior

                if thread_id:
                    # Set a deterministic seed based on thread ID for any internal RNG
                    import hashlib
                    thread_seed = int(hashlib.md5(thread_id.encode()).hexdigest()[:8], 16) % (2**31)
                    # Note: DuckDB doesn't have a direct seed setting, but this prepares for future use

            except Exception as e:
                # Pragma settings may not be available in all DuckDB versions
                # Continue with connection but log the issue
                print(f"⚠️ Warning: Could not set deterministic database settings: {e}")

        return conn

    @contextmanager
    def transaction(self, *, deterministic: bool = False, thread_id: Optional[str] = None) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Create a database transaction context with optional deterministic configuration.

        Args:
            deterministic: If True, use deterministic connection configuration
            thread_id: Optional thread identifier for connection isolation
        """
        conn = self.get_connection(deterministic=deterministic, thread_id=thread_id)
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
        finally:
            conn.close()

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
