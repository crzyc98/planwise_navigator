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


@dataclass(slots=True)
class DatabaseConnectionManager:
    """Lightweight DuckDB connection manager with transaction and retry helpers.

    Notes:
    - Creates a new connection for each context to avoid cross-thread issues.
    - Keeps surface minimal; can be extended for pooling if needed.
    """

    db_path: Path = Path("simulation.duckdb")

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    @contextmanager
    def transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute_with_retry(
        self,
        fn: Callable[[duckdb.DuckDBPyConnection], T],
        *,
        retries: int = 3,
        backoff_seconds: float = 0.5,
    ) -> T:
        """Execute a function against a connection with simple retry logic."""
        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt <= retries:
            try:
                with self.transaction() as conn:
                    return fn(conn)
            except Exception as e:  # pragma: no cover - external IO
                last_exc = e
                if attempt == retries:
                    break
                time.sleep(backoff_seconds * (2 ** attempt))
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
