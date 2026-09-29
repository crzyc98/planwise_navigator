"""ExecutionMutex reclaims locks whose holder died (#588).

A cancelled Studio fit/backtest is terminated mid-run; SIGTERM skips atexit,
so its initialization lock would otherwise block every run sharing the
working directory for up to an hour.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from planalign_orchestrator.utils import ExecutionMutex

pytestmark = pytest.mark.fast


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def _write_lock(mutex: ExecutionMutex, pid: int) -> None:
    mutex.lock_file.write_text(f"pid:{pid}\ntimestamp:{time.time()}\n")


def test_lock_left_by_a_dead_process_is_reclaimed(tmp_path):
    mutex = ExecutionMutex("init", lock_dir=tmp_path)
    _write_lock(mutex, _dead_pid())

    assert mutex.acquire(timeout=3)
    assert f"pid:{os.getpid()}" in mutex.lock_file.read_text()
    mutex.release()


def test_lock_held_by_a_live_process_is_respected(tmp_path):
    mutex = ExecutionMutex("init", lock_dir=tmp_path)
    _write_lock(mutex, os.getpid())

    assert not mutex.acquire(timeout=1)
    assert mutex.lock_file.exists()


def test_unreadable_lock_is_not_reclaimed_early(tmp_path):
    mutex = ExecutionMutex("init", lock_dir=tmp_path)
    mutex.lock_file.write_text("garbage\n")

    assert not mutex.acquire(timeout=1)
