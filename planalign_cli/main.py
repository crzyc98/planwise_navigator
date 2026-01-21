#!/usr/bin/env python3
"""
Fidelity PlanAlign Engine CLI

Rich-based CLI wrapper for Fidelity PlanAlign Engine with enhanced user experience.
Wraps existing planalign_orchestrator functionality with beautiful terminal interfaces.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .commands.status import status_command
from .commands.simulate import simulate_command
from .commands.batch import batch_command
from .commands.validate import validate_command
from .commands.checkpoint import checkpoint_command
from .commands.analyze import analyze_command
from .commands.studio import launch_studio
from .commands.sync import (
    sync_init,
    sync_push,
    sync_pull,
    sync_status as sync_status_cmd,
    sync_log,
    sync_disconnect,
)

# Initialize Rich console
console = Console()

# Main app
app = typer.Typer(
    name="planalign",
    help="Fidelity PlanAlign Engine CLI - Enterprise workforce simulation platform",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=True,
)

# Add version callback
def version_callback(value: bool):
    if value:
        from planalign_cli import __version__
        console.print(f"Fidelity PlanAlign Engine v{__version__}")
        raise typer.Exit()

@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version information"
    ),
):
    """
    [bold blue]Fidelity PlanAlign Engine CLI[/bold blue]

    Enterprise-grade workforce simulation and event sourcing platform with
    beautiful terminal interfaces and enhanced user experience.

    [dim]Examples:[/dim]
        planalign status                    # Check system health
        planalign simulate 2025-2027        # Run multi-year simulation
        planalign batch --scenarios baseline # Run batch scenarios
    """
    pass

# Register commands directly instead of as command groups
from .commands.simulate import run_simulation
from .commands.status import show_status, health_check
from .commands.batch import run_batch
from .commands.validate import validate_config
from .commands.checkpoint import list_checkpoints, checkpoint_status, cleanup_checkpoints, validate_recovery

# Main simulate command - direct access
@app.command("simulate")
def simulate(
    years: str = typer.Argument(..., help="Year range (e.g., '2025-2027' or '2025')"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to simulation config YAML"),
    database: Optional[str] = typer.Option(None, "--database", help="Path to DuckDB database file"),
    threads: Optional[int] = typer.Option(None, "--threads", help="Number of dbt threads"),
    resume: bool = typer.Option(False, "--resume", help="Resume from last checkpoint"),
    force_restart: bool = typer.Option(False, "--force-restart", help="Ignore checkpoints and start fresh"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be executed without running"),
    fail_on_validation_error: bool = typer.Option(False, "--fail-on-validation-error", help="Fail simulation on validation errors"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    growth: Optional[str] = typer.Option(None, "--growth", help="Target growth rate (e.g., '3.5%' or '0.035')"),
):
    """🎯 Run multi-year workforce simulation with Rich progress tracking."""
    run_simulation(
        years=years,
        config=config,
        database=database,
        threads=threads,
        resume=resume,
        force_restart=force_restart,
        dry_run=dry_run,
        fail_on_validation_error=fail_on_validation_error,
        verbose=verbose,
        growth=growth,
    )

# Status commands
@app.command("status")
def status(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to simulation config YAML"),
    database: Optional[str] = typer.Option(None, "--database", help="Path to DuckDB database file"),
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show detailed system information"),
):
    """🔍 Show comprehensive system status and health."""
    show_status(config=config, database=database, detailed=detailed)

@app.command("health")
def health(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to simulation config YAML"),
):
    """🏥 Quick health check for system readiness."""
    health_check(config=config)

# Batch command
@app.command("batch")
def batch(
    scenarios: Optional[list[str]] = typer.Option(None, "--scenarios", help="Specific scenario names to run (comma-separated or multiple flags)"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Base configuration file"),
    scenarios_dir: Optional[str] = typer.Option(None, "--scenarios-dir", help="Directory containing scenario YAML files"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Output directory for batch results"),
    export_format: str = typer.Option("excel", "--export-format", help="Export format (excel, csv)"),
    threads: int = typer.Option(1, "--threads", help="Number of dbt threads"),
    optimization: str = typer.Option("medium", "--optimization", help="Optimization level (low, medium, high)"),
    clean: bool = typer.Option(False, "--clean", help="Delete DuckDB databases before running for a clean start"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """📊 Run multiple scenarios with Excel export."""
    # Handle comma-separated scenario names for user convenience
    if scenarios and len(scenarios) == 1 and "," in scenarios[0]:
        scenarios = [s.strip() for s in scenarios[0].split(",")]

    run_batch(
        scenarios=scenarios,
        config=config,
        scenarios_dir=scenarios_dir,
        output_dir=output_dir,
        export_format=export_format,
        threads=threads,
        optimization=optimization,
        clean=clean,
        verbose=verbose,
    )

# Validate command
@app.command("validate")
def validate(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to simulation config YAML"),
    enforce_identifiers: bool = typer.Option(False, "--enforce-identifiers", help="Require scenario_id and plan_design_id"),
):
    """✅ Validate simulation configuration."""
    validate_config(config=config, enforce_identifiers=enforce_identifiers)

# Analyze command
@app.command("analyze")
def analyze(
    target: str = typer.Argument("workforce", help="Analysis target (workforce, events, scenario)"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to simulation config YAML"),
    database: Optional[str] = typer.Option(None, "--database", help="Path to DuckDB database file"),
    start_year: Optional[int] = typer.Option(None, "--start-year", help="Start year for analysis"),
    end_year: Optional[int] = typer.Option(None, "--end-year", help="End year for analysis"),
    trend: bool = typer.Option(False, "--trend", help="Show detailed trend analysis"),
    export: Optional[str] = typer.Option(None, "--export", help="Export format (excel, csv)"),
    scenario: Optional[str] = typer.Option(None, "--scenario", help="Scenario name for scenario analysis"),
    compare: Optional[str] = typer.Option(None, "--compare", help="Compare with another scenario"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """📊 Analyze simulation results with Rich tables and terminal-based visualizations."""
    from .commands.analyze import analyze_workforce, analyze_events, analyze_scenario

    if target == "workforce":
        analyze_workforce(
            config=config,
            database=database,
            start_year=start_year,
            end_year=end_year,
            trend=trend,
            export=export,
            verbose=verbose
        )
    elif target == "events":
        analyze_events(
            config=config,
            database=database,
            year=None,  # Not supported in main analyze command
            event_type=None,  # Not supported in main analyze command
            verbose=verbose
        )
    elif target == "scenario":
        if not scenario:
            console.print("[yellow]Scenario analysis requires a scenario name[/yellow]")
            console.print("Usage: planalign analyze scenario --scenario <scenario_name>")
            raise typer.Exit(1)
        analyze_scenario(
            scenario_name=scenario,
            config=config,
            compare=compare,
            export=export,
            verbose=verbose
        )
    else:
        console.print(f"[yellow]Unknown analysis target: {target}[/yellow]")
        console.print("Available targets: workforce, events, scenario")
        raise typer.Exit(1)

# Checkpoint commands
@app.command("checkpoints")
def checkpoints(
    action: str = typer.Argument("status", help="Action: list, status, cleanup, validate"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to simulation config YAML"),
    database: Optional[str] = typer.Option(None, "--database", help="Path to DuckDB database file"),
    keep: int = typer.Option(5, "--keep", help="Number of checkpoints to keep when cleaning up"),
):
    """💾 Checkpoint management and recovery operations."""
    if action == "list":
        list_checkpoints(config=config, database=database)
    elif action == "status":
        checkpoint_status(config=config, database=database)
    elif action == "cleanup":
        cleanup_checkpoints(keep=keep, config=config, database=database)
    elif action == "validate":
        validate_recovery(config=config, database=database)
    else:
        console.print(f"❌ Unknown action: {action}")
        console.print("Valid actions: list, status, cleanup, validate")
        raise typer.Exit(1)


# Studio command - launch API + Frontend
@app.command("studio")
def studio(
    api_port: int = typer.Option(8000, "--api-port", help="Port for the API backend"),
    frontend_port: int = typer.Option(5173, "--frontend-port", help="Port for the frontend dev server"),
    api_only: bool = typer.Option(False, "--api-only", help="Only start the API backend"),
    frontend_only: bool = typer.Option(False, "--frontend-only", help="Only start the frontend"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser automatically"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output from servers"),
):
    """🚀 Launch PlanAlign Studio (API + Frontend)."""
    launch_studio(
        api_port=api_port,
        frontend_port=frontend_port,
        api_only=api_only,
        frontend_only=frontend_only,
        no_browser=no_browser,
        verbose=verbose,
    )


# Sync commands - workspace cloud synchronization (E083)
sync_app = typer.Typer(
    name="sync",
    help="Workspace cloud synchronization (Git-based)",
    no_args_is_help=True,
)

@sync_app.command("init")
def sync_init_cmd(
    remote_url: str = typer.Argument(
        ...,
        help="Git remote URL (e.g., git@github.com:user/planalign-workspaces.git)"
    ),
    branch: str = typer.Option(
        "main",
        "--branch", "-b",
        help="Branch to use for sync"
    ),
    auto_sync: bool = typer.Option(
        False,
        "--auto-sync",
        help="Enable automatic sync on changes"
    ),
):
    """Initialize workspace sync with a Git remote."""
    sync_init(remote_url=remote_url, branch=branch, auto_sync=auto_sync)

@sync_app.command("push")
def sync_push_cmd(
    message: Optional[str] = typer.Option(
        None,
        "--message", "-m",
        help="Custom commit message"
    ),
):
    """Push local workspace changes to remote."""
    sync_push(message=message)

@sync_app.command("pull")
def sync_pull_cmd():
    """Pull remote changes to local workspaces."""
    sync_pull()

@sync_app.command("status")
def sync_status_command():
    """Show current sync status."""
    sync_status_cmd()

@sync_app.command("log")
def sync_log_cmd(
    limit: int = typer.Option(
        20,
        "--limit", "-n",
        help="Number of log entries to show"
    ),
):
    """Show sync operation history."""
    sync_log(limit=limit)

@sync_app.command("disconnect")
def sync_disconnect_cmd():
    """Disconnect sync from remote."""
    sync_disconnect()

# Add sync subcommand to main app
app.add_typer(sync_app, name="sync")


def cli_main():
    """Entry point for the CLI."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n🛑 [yellow]Operation cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n❌ [bold red]Error:[/bold red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    cli_main()
