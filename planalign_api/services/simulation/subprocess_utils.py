"""
Cross-platform subprocess utilities for simulation execution.

Provides reliable async subprocess creation and I/O handling
that works on both Windows and Unix platforms.
"""

import asyncio
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncIterator, Dict, List, Tuple

# Thread pool for Windows subprocess I/O
_subprocess_executor = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="subprocess_io"
)

IS_WINDOWS = platform.system() == "Windows"


async def create_subprocess(
    cmd: List[str],
    cwd: str,
    env: Dict[str, str],
) -> Tuple[Any, AsyncIterator[bytes]]:
    """
    Create a subprocess in a cross-platform way.

    On Windows, uses subprocess.Popen with threaded I/O to avoid
    asyncio event loop issues. On Unix, uses asyncio.create_subprocess_exec.

    Args:
        cmd: Command to execute as a list of strings
        cwd: Working directory for the subprocess
        env: Environment variables for the subprocess

    Returns:
        Tuple of (process, async_line_iterator)
    """
    if IS_WINDOWS:
        # On Windows, use Popen + thread-based async reading
        # This is more reliable than asyncio subprocess on Windows
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            bufsize=1,  # Line buffered
        )

        async def read_lines() -> AsyncIterator[bytes]:
            """Read lines from process stdout using thread pool."""
            loop = asyncio.get_event_loop()
            while True:
                line = await loop.run_in_executor(
                    _subprocess_executor, process.stdout.readline
                )
                if not line:
                    break
                yield line

        return process, read_lines()
    else:
        # On Unix, asyncio subprocess works fine
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=env,
        )

        async def read_lines() -> AsyncIterator[bytes]:
            """Read lines from asyncio subprocess."""
            async for line in process.stdout:
                yield line

        return process, read_lines()


async def wait_subprocess(process: Any) -> int:
    """
    Wait for subprocess to complete in a cross-platform way.

    Args:
        process: The process to wait for (Popen on Windows, asyncio.Process on Unix)

    Returns:
        Exit code of the process
    """
    if IS_WINDOWS:
        # For Popen, use thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_subprocess_executor, process.wait)
    else:
        # For asyncio subprocess, use await
        return await process.wait()
