#!/usr/bin/env python3
"""
Shared utilities for preventing concurrent execution across different orchestrator systems.
"""

import atexit
import os
import time
from pathlib import Path
from typing import Optional


class ExecutionMutex:
    """File-based mutex to prevent concurrent simulation runs."""

    def __init__(self, lock_name: str = "simulation_execution"):
        """
        Initialize execution mutex.

        Args:
            lock_name: Name of the lock file (without extension)
        """
        self.lock_file = Path(f".{lock_name}.lock")
        self.acquired = False

    def acquire(self, timeout: int = 30) -> bool:
        """
        Acquire the execution lock.

        Args:
            timeout: Maximum time to wait for lock acquisition in seconds

        Returns:
            True if lock acquired successfully, False otherwise
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                if not self.lock_file.exists():
                    # Create lock file with process info
                    with open(self.lock_file, "w") as f:
                        f.write(f"pid:{os.getpid()}\n")
                        f.write(f"timestamp:{time.time()}\n")

                    self.acquired = True
                    # Register cleanup on exit
                    atexit.register(self.release)
                    return True
                else:
                    # Check if existing lock is stale (older than 1 hour)
                    if time.time() - self.lock_file.stat().st_mtime > 3600:
                        print("⚠️  Removing stale lock file")
                        self.lock_file.unlink()
                        continue

                    print(
                        f"⏳ Simulation already running, waiting... ({int(time.time() - start_time)}s)"
                    )
                    time.sleep(2)

            except Exception as e:
                print(f"❌ Error acquiring lock: {e}")
                return False

        print(f"❌ Failed to acquire execution lock after {timeout} seconds")
        return False

    def release(self):
        """Release the execution lock."""
        if self.acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink()
                self.acquired = False
            except Exception as e:
                print(f"⚠️  Warning: Could not remove lock file: {e}")

    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise RuntimeError("Could not acquire execution lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


def check_conflicting_systems() -> Optional[str]:
    """
    Check for conflicting simulation systems and provide guidance.

    Returns:
        Warning message if conflicts detected, None otherwise
    """
    simple_runner = Path("run_multi_year.py")
    advanced_runner = Path("orchestrator_dbt/run_multi_year.py")

    if simple_runner.exists() and advanced_runner.exists():
        return (
            "⚠️  DUAL ARCHITECTURE DETECTED:\n"
            f"   Simple runner: {simple_runner}\n"
            f"   Advanced runner: {advanced_runner}\n"
            "\n"
            "📋 RECOMMENDATION:\n"
            "   Use 'orchestrator_dbt/run_multi_year.py' for production workloads\n"
            "   Use 'run_multi_year.py' only for simple testing\n"
            "   Both systems are prevented from running concurrently by execution mutex.\n"
        )

    return None


def print_execution_warning():
    """Print warning about dual architecture if detected."""
    warning = check_conflicting_systems()
    if warning:
        print(warning)
