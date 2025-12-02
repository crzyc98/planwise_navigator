"""
Studio command - Launch PlanAlign Studio (API + Frontend)

Starts both the FastAPI backend and the React/Vite frontend.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def _get_npm_command() -> str:
    """
    Get the correct npm command for the current platform.

    On Windows, npm is typically npm.cmd. On macOS/Linux, it's just npm.
    Uses shutil.which() to find the correct executable.
    """
    # Try to find npm in PATH
    npm_path = shutil.which("npm")
    if npm_path:
        return npm_path

    # Fallback for Windows where shutil.which might not find .cmd
    if sys.platform == "win32":
        # Try common Windows npm locations
        for cmd in ["npm.cmd", "npm.exe"]:
            path = shutil.which(cmd)
            if path:
                return path

    # Default fallback
    return "npm"

# Track child processes for cleanup
_processes: list[subprocess.Popen] = []


def _cleanup_processes(signum=None, frame=None):
    """Terminate all child processes."""
    for proc in _processes:
        if proc.poll() is None:  # Still running
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    if signum is not None:
        sys.exit(0)


def launch_studio(
    api_port: int = 8000,
    frontend_port: int = 5173,
    api_only: bool = False,
    frontend_only: bool = False,
    no_browser: bool = False,
    verbose: bool = False,
):
    """
    Launch PlanAlign Studio (API backend + React frontend).

    Args:
        api_port: Port for the FastAPI backend (default: 8000)
        frontend_port: Port for the Vite dev server (default: 5173)
        api_only: Only start the API backend
        frontend_only: Only start the frontend
        no_browser: Don't open browser automatically
        verbose: Show detailed output from both servers
    """
    # studio.py is at planalign_cli/commands/studio.py
    # Go up 3 levels: commands/ -> planalign_cli/ -> project_root/
    project_root = Path(__file__).parent.parent.parent
    api_dir = project_root / "planalign_api"
    frontend_dir = project_root / "planalign_studio"

    # Validate directories exist
    if not api_only and not frontend_dir.exists():
        console.print(f"[red]Frontend directory not found: {frontend_dir}[/red]")
        raise SystemExit(1)

    if not frontend_only and not api_dir.exists():
        console.print(f"[red]API directory not found: {api_dir}[/red]")
        raise SystemExit(1)

    # Register signal handlers for cleanup
    signal.signal(signal.SIGINT, _cleanup_processes)
    signal.signal(signal.SIGTERM, _cleanup_processes)

    # Display startup info
    console.print()
    console.print(
        Panel.fit(
            "[bold blue]PlanAlign Studio[/bold blue]\n"
            "[dim]Launching development servers...[/dim]",
            border_style="blue",
        )
    )
    console.print()

    started_services = []

    try:
        # Start API backend
        if not frontend_only:
            console.print("[cyan]Starting API backend...[/cyan]")

            # Determine output handling
            stdout = None if verbose else subprocess.DEVNULL
            stderr = None if verbose else subprocess.DEVNULL

            api_env = os.environ.copy()
            api_env["PLANALIGN_API_PORT"] = str(api_port)

            # On Windows, use our wrapper module that sets ProactorEventLoop
            # before uvicorn creates its event loop (required for subprocess support)
            if sys.platform == "win32":
                api_cmd = [
                    sys.executable,
                    "-c",
                    f"import asyncio; asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy()); "
                    f"import uvicorn; uvicorn.run('planalign_api.main:app', host='0.0.0.0', port={api_port}, reload=True)",
                ]
            else:
                api_cmd = [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "planalign_api.main:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(api_port),
                    "--reload",
                ]

            api_process = subprocess.Popen(
                api_cmd,
                cwd=str(project_root),
                env=api_env,
                stdout=stdout,
                stderr=stderr,
            )
            _processes.append(api_process)
            started_services.append(("API Backend", f"http://localhost:{api_port}"))

            # Wait for API to start
            time.sleep(2)
            if api_process.poll() is not None:
                console.print("[red]API backend failed to start[/red]")
                raise SystemExit(1)

            console.print(f"[green]  API running at http://localhost:{api_port}[/green]")
            console.print(f"[dim]    Docs: http://localhost:{api_port}/api/docs[/dim]")

        # Start frontend
        if not api_only:
            console.print("[cyan]Starting frontend...[/cyan]")

            # Check if node_modules exists
            if not (frontend_dir / "node_modules").exists():
                console.print("[yellow]  Installing frontend dependencies...[/yellow]")
                npm_cmd = _get_npm_command()
                install_result = subprocess.run(
                    [npm_cmd, "install"],
                    cwd=str(frontend_dir),
                    capture_output=not verbose,
                    shell=(sys.platform == "win32"),  # Use shell on Windows for .cmd files
                )
                if install_result.returncode != 0:
                    console.print("[red]  Failed to install frontend dependencies[/red]")
                    _cleanup_processes()
                    raise SystemExit(1)

            stdout = None if verbose else subprocess.DEVNULL
            stderr = None if verbose else subprocess.DEVNULL

            frontend_env = os.environ.copy()
            frontend_env["VITE_API_URL"] = f"http://localhost:{api_port}"

            npm_cmd = _get_npm_command()
            frontend_process = subprocess.Popen(
                [npm_cmd, "run", "dev", "--", "--port", str(frontend_port)],
                cwd=str(frontend_dir),
                env=frontend_env,
                stdout=stdout,
                stderr=stderr,
                shell=(sys.platform == "win32"),  # Use shell on Windows for .cmd files
            )
            _processes.append(frontend_process)
            started_services.append(("Frontend", f"http://localhost:{frontend_port}"))

            # Wait for frontend to start
            time.sleep(3)
            if frontend_process.poll() is not None:
                console.print("[red]Frontend failed to start[/red]")
                _cleanup_processes()
                raise SystemExit(1)

            console.print(f"[green]  Frontend running at http://localhost:{frontend_port}[/green]")

        # Display summary
        console.print()
        table = Table(title="Running Services", show_header=True)
        table.add_column("Service", style="cyan")
        table.add_column("URL", style="green")

        for service, url in started_services:
            table.add_row(service, url)

        console.print(table)
        console.print()

        # Open browser
        if not no_browser and not api_only:
            try:
                import webbrowser

                webbrowser.open(f"http://localhost:{frontend_port}")
                console.print("[dim]Opening browser...[/dim]")
            except Exception:
                pass

        console.print("[bold green]Studio is running![/bold green]")
        console.print("[dim]Press Ctrl+C to stop all services[/dim]")
        console.print()

        # Keep running until interrupted
        while True:
            # Check if processes are still running
            for proc in _processes:
                if proc.poll() is not None:
                    console.print("[yellow]A service stopped unexpectedly[/yellow]")
                    _cleanup_processes()
                    raise SystemExit(1)
            time.sleep(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        _cleanup_processes()
        console.print("[green]All services stopped[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        _cleanup_processes()
        raise SystemExit(1)
