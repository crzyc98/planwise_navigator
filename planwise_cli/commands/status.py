"""
Status command for PlanWise Navigator CLI

Shows system health, database status, checkpoint information, and recommendations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..integration.orchestrator_wrapper import OrchestratorWrapper
from ..ui.progress import create_status_spinner
from ..utils.config_helpers import find_default_config

console = Console()
status_command = typer.Typer()

@status_command.callback()
def status_main():
    """🔍 Show system status and health diagnostics."""
    pass

@status_command.command("show")
def show_status(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    database: Optional[str] = typer.Option(
        None, "--database", help="Path to DuckDB database file"
    ),
    detailed: bool = typer.Option(
        False, "--detailed", "-d", help="Show detailed system information"
    ),
):
    """Show comprehensive system status and health."""
    console.print("🔍 [bold blue]PlanWise Navigator Status[/bold blue]")

    with create_status_spinner("Checking system health...") as progress:
        try:
            # Initialize wrapper with default paths
            config_path = Path(config) if config else find_default_config()
            db_path = Path(database) if database else Path("dbt/simulation.duckdb")

            wrapper = OrchestratorWrapper(config_path, db_path)
            status_info = wrapper.get_system_status()

            progress.update("System check complete")

        except Exception as e:
            console.print(f"❌ [red]Failed to get system status: {e}[/red]")
            raise typer.Exit(1)

    # Display status information in organized panels
    _display_status_overview(status_info)
    _display_database_status(status_info.get("database", {}))
    _display_checkpoint_status(status_info.get("checkpoints", {}))

    if detailed:
        _display_configuration_status(status_info.get("config", {}))
        _display_performance_metrics(status_info.get("performance", {}))

    # Show recommendations
    recommendations = status_info.get("recommendations", [])
    if recommendations:
        _display_recommendations(recommendations)

@status_command.command("health")
def health_check(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
):
    """Quick health check for system readiness."""
    console.print("🏥 [bold blue]Health Check[/bold blue]")

    try:
        config_path = Path(config) if config else find_default_config()
        wrapper = OrchestratorWrapper(config_path, Path("dbt/simulation.duckdb"))

        health_status = wrapper.check_system_health()

        if health_status["healthy"]:
            console.print("✅ [bold green]System is healthy and ready[/bold green]")
        else:
            console.print("⚠️ [bold yellow]System has issues[/bold yellow]")
            for issue in health_status.get("issues", []):
                console.print(f"  • [red]{issue}[/red]")

        return 0 if health_status["healthy"] else 1

    except Exception as e:
        console.print(f"❌ [red]Health check failed: {e}[/red]")
        raise typer.Exit(1)

def _display_status_overview(status_info: dict):
    """Display high-level status overview."""
    table = Table(title="System Overview", show_header=True, header_style="bold blue")
    table.add_column("Component", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    # System status
    system_status = "✅ Ready" if status_info.get("system_ready") else "⚠️ Issues"
    table.add_row("System", system_status, status_info.get("system_message", ""))

    # Database status
    db_status = "✅ Connected" if status_info.get("database", {}).get("connected") else "❌ Disconnected"
    table.add_row("Database", db_status, status_info.get("database", {}).get("path", ""))

    # Configuration status
    config_status = "✅ Valid" if status_info.get("config", {}).get("valid") else "❌ Invalid"
    table.add_row("Configuration", config_status, status_info.get("config", {}).get("path", ""))

    console.print(table)
    console.print()

def _display_database_status(db_info: dict):
    """Display database status information."""
    if not db_info:
        return

    panel_content = []

    if db_info.get("connected"):
        panel_content.append(f"📊 [green]Connected to: {db_info.get('path')}[/green]")
        panel_content.append(f"📈 Tables: {db_info.get('table_count', 0)}")
        panel_content.append(f"🗄️ Size: {db_info.get('size_mb', 0):.1f} MB")

        if db_info.get("last_modified"):
            panel_content.append(f"🕒 Last modified: {db_info['last_modified']}")
    else:
        panel_content.append(f"❌ [red]Database not accessible: {db_info.get('path')}[/red]")

    console.print(Panel("\n".join(panel_content), title="Database Status", border_style="blue"))
    console.print()

def _display_checkpoint_status(checkpoint_info: dict):
    """Display checkpoint status information."""
    if not checkpoint_info:
        return

    panel_content = []

    checkpoint_count = checkpoint_info.get("count", 0)
    if checkpoint_count > 0:
        panel_content.append(f"💾 [green]{checkpoint_count} checkpoint(s) available[/green]")

        if checkpoint_info.get("latest_year"):
            panel_content.append(f"📅 Latest: Year {checkpoint_info['latest_year']}")

        if checkpoint_info.get("resumable_year"):
            panel_content.append(f"🔄 Resumable from: Year {checkpoint_info['resumable_year']}")

        if checkpoint_info.get("config_compatible"):
            panel_content.append("✅ [green]Configuration compatible[/green]")
        else:
            panel_content.append("⚠️ [yellow]Configuration changed - may need restart[/yellow]")
    else:
        panel_content.append("❌ [yellow]No checkpoints found[/yellow]")
        panel_content.append("💡 Run a simulation to create checkpoints")

    console.print(Panel("\n".join(panel_content), title="Checkpoint Status", border_style="green"))
    console.print()

def _display_configuration_status(config_info: dict):
    """Display detailed configuration status."""
    if not config_info:
        return

    table = Table(title="Configuration Details", show_header=True, header_style="bold blue")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="dim")
    table.add_column("Status", justify="center")

    for setting, details in config_info.items():
        if isinstance(details, dict):
            status = "✅" if details.get("valid") else "❌"
            value = str(details.get("value", ""))
            table.add_row(setting, value, status)

    console.print(table)
    console.print()

def _display_performance_metrics(perf_info: dict):
    """Display performance metrics if available."""
    if not perf_info:
        return

    panel_content = []

    if perf_info.get("last_run_duration"):
        panel_content.append(f"⏱️ Last run: {perf_info['last_run_duration']}")

    if perf_info.get("memory_usage"):
        panel_content.append(f"🧠 Memory usage: {perf_info['memory_usage']}")

    if perf_info.get("thread_count"):
        panel_content.append(f"🔧 Configured threads: {perf_info['thread_count']}")

    if panel_content:
        console.print(Panel("\n".join(panel_content), title="Performance Metrics", border_style="yellow"))
        console.print()

def _display_recommendations(recommendations: list[str]):
    """Display system recommendations."""
    panel_content = []

    for i, rec in enumerate(recommendations, 1):
        panel_content.append(f"{i}. {rec}")

    console.print(Panel(
        "\n".join(panel_content),
        title="💡 Recommendations",
        border_style="yellow"
    ))

# Default command
@status_command.command(name="", hidden=True)
def default():
    """Default status command."""
    show_status()
