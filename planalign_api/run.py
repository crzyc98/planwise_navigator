"""
Uvicorn entry point with Windows event loop fix.

This module sets the Windows ProactorEventLoop policy BEFORE uvicorn
creates its event loop, which is required for asyncio.create_subprocess_exec().

Usage:
    python -m planalign_api.run
"""

import asyncio
import platform
import sys

# Windows requires ProactorEventLoop for asyncio subprocess support
# MUST be set before uvicorn imports/creates its event loop
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn


def main():
    """Run the API server."""
    uvicorn.run(
        "planalign_api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
