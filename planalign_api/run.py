"""
Uvicorn entry point with Windows event loop fix.

This module sets the Windows ProactorEventLoop policy BEFORE uvicorn
creates its event loop, which is required for asyncio.create_subprocess_exec().

Usage:
    python -m planalign_api.run [--host HOST] [--port PORT] [--reload]
"""

import argparse
import asyncio
import platform

# Windows requires ProactorEventLoop for asyncio subprocess support
# MUST be set before uvicorn imports/creates its event loop
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn


def main():
    """Run the API server."""
    parser = argparse.ArgumentParser(description="Run PlanAlign API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "planalign_api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
