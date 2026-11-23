"""Start job processes in their own process group and stop the whole group.

A job's leader (the ``planalign`` CLI) can exit, or be stopped, while a
descendant such as a dbt subprocess keeps running and holding the database.
Jobs therefore start in a new session on POSIX, and stopping one signals the
entire group and waits until no member is left. On Windows only the leader is
signalled (``CREATE_NEW_PROCESS_GROUP`` keeps console signals away from the
API).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)
CANCEL_GRACE_SECONDS = 5.0
IS_POSIX = os.name == "posix"
_POLL_SECONDS = 0.05


def new_session_kwargs() -> dict[str, Any]:
    """``Popen``/``create_subprocess_exec`` keywords for a separate process group."""
    if IS_POSIX:
        return {"start_new_session": True}
    return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}


def group_alive(pgid: int) -> bool:
    """Whether any process is left in the group.

    macOS answers EPERM rather than ESRCH while a member is still exiting if
    another process is reading the process table at that moment, so EPERM
    means "not gone yet": poll again.
    """
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def signal_group(pgid: int, sig: int) -> None:
    """Send ``sig`` to the group; a group that is already gone is fine."""
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        logger.debug("Process group %s already exited", pgid)


def wait_for_group_exit(pgid: int, grace: float = CANCEL_GRACE_SECONDS) -> None:
    """Block until every process in the group is gone (POSIX; no-op elsewhere).

    Members still running after ``grace`` seconds are sent SIGKILL.
    """
    if not IS_POSIX:
        return
    deadline = time.monotonic() + grace
    try:
        while group_alive(pgid):
            if time.monotonic() >= deadline:
                os.killpg(pgid, signal.SIGKILL)
            time.sleep(_POLL_SECONDS)
    except ProcessLookupError:
        return


def terminate_group(
    process: subprocess.Popen[Any], grace: float = CANCEL_GRACE_SECONDS
) -> None:
    """SIGTERM the process's group, SIGKILL it after ``grace``, and reap it."""
    try:
        if not IS_POSIX:
            _terminate_leader(process, grace)
            return
        os.killpg(process.pid, signal.SIGTERM)
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            process.poll()  # Reap the leader before checking its process group.
            if not group_alive(process.pid):
                break
            time.sleep(_POLL_SECONDS)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        wait_for_group_exit(process.pid, grace)
    except ProcessLookupError:
        process.wait()
    except PermissionError:
        logger.exception("Could not terminate job process %s", process.pid)
        raise


def _terminate_leader(process: subprocess.Popen[Any], grace: float) -> None:
    process.terminate()
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
    process.wait()


async def stop_group_async(pgid: int, grace: float = CANCEL_GRACE_SECONDS) -> bool:
    """SIGTERM a POSIX group, SIGKILL it after ``grace``; True once it is gone."""
    signal_group(pgid, signal.SIGTERM)
    if await wait_group_async(pgid, grace):
        return True
    signal_group(pgid, signal.SIGKILL)
    return await wait_group_async(pgid, grace)


async def wait_group_async(pgid: int, timeout: float) -> bool:
    """Wait up to ``timeout`` seconds for the group to empty; True if it did."""
    deadline = time.monotonic() + timeout
    while group_alive(pgid):
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(_POLL_SECONDS)
    return True
