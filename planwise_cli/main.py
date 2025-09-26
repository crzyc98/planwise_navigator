#!/usr/bin/env python3
"""
PlanWise Navigator CLI

Rich-based CLI wrapper for PlanWise Navigator with enhanced user experience.
Wraps existing navigator_orchestrator functionality with beautiful terminal interfaces.
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

# Initialize Rich console
console = Console()

# Main app
app = typer.Typer(
    name="planwise",
    help="🚀 PlanWise Navigator CLI - Enterprise workforce simulation platform",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=True,
)

# Add version callback
def version_callback(value: bool):
    if value:
        from planwise_cli import __version__
        console.print(f"PlanWise Navigator CLI v{__version__}")
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
    🚀 [bold blue]PlanWise Navigator CLI[/bold blue]

    Enterprise-grade workforce simulation and event sourcing platform with
    beautiful terminal interfaces and enhanced user experience.

    [dim]Examples:[/dim]
        planwise status                    # Check system health
        planwise simulate 2025-2027        # Run multi-year simulation
        planwise batch --scenarios baseline # Run batch scenarios
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
            console.print("Usage: planwise analyze scenario --scenario <scenario_name>")
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
