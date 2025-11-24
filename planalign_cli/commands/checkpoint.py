"""
Checkpoint command for Fidelity PlanAlign Engine CLI

Checkpoint management and recovery operations with Rich formatting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..integration.orchestrator_wrapper import OrchestratorWrapper
from ..ui.progress import show_error_message, show_success_message, show_warning_message
from ..utils.config_helpers import find_default_config

console = Console()
checkpoint_command = typer.Typer()

@checkpoint_command.callback()
def checkpoint_main():
    """💾 Checkpoint management and recovery operations."""
    pass

@checkpoint_command.command("list")
def list_checkpoints(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    database: Optional[str] = typer.Option(
        None, "--database", help="Path to DuckDB database file"
    ),
):
    """List available checkpoints."""
    try:
        config_path = Path(config) if config else find_default_config()
        db_path = Path(database) if database else Path("dbt/simulation.duckdb")

        wrapper = OrchestratorWrapper(config_path, db_path)
        checkpoints = wrapper.checkpoint_manager.list_checkpoints()

        if not checkpoints:
            console.print("❌ [yellow]No checkpoints found[/yellow]")
            console.print("💡 [dim]Run a simulation to create checkpoints[/dim]")
            return 0

        console.print(f"💾 [bold blue]Found {len(checkpoints)} checkpoint(s)[/bold blue]")

        # Create table
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Year", justify="center")
        table.add_column("Timestamp", style="dim")
        table.add_column("Format")
        table.add_column("Size", justify="right")
        table.add_column("Status", justify="center")

        for cp in sorted(checkpoints, key=lambda x: x["year"]):
            status = "✅ Valid" if cp["integrity_valid"] else "⚠️ Invalid"
            size_mb = cp.get("file_size", 0) / (1024 * 1024) if cp.get("file_size") else 0

            table.add_row(
                str(cp["year"]),
                cp["timestamp"],
                cp["format"],
                f"{size_mb:.1f} MB",
                status,
            )

        console.print(table)
        return 0

    except Exception as e:
        show_error_message(f"Failed to list checkpoints: {e}")
        raise typer.Exit(1)

@checkpoint_command.command("status")
def checkpoint_status(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    database: Optional[str] = typer.Option(
        None, "--database", help="Path to DuckDB database file"
    ),
):
    """Show recovery status and recommendations."""
    try:
        config_path = Path(config) if config else find_default_config()
        db_path = Path(database) if database else Path("dbt/simulation.duckdb")

        wrapper = OrchestratorWrapper(config_path, db_path)
        config_hash = wrapper.recovery_orchestrator.calculate_config_hash(str(config_path))
        status = wrapper.recovery_orchestrator.get_recovery_status(config_hash)

        console.print("🔍 [bold blue]Recovery Status[/bold blue]")

        # Basic status
        console.print(f"  📊 Checkpoints available: {status['checkpoints_available']}")
        console.print(f"  📈 Total checkpoints: {status['total_checkpoints']}")

        if status["latest_checkpoint_year"]:
            console.print(f"  📅 Latest checkpoint: Year {status['latest_checkpoint_year']} ({status['latest_checkpoint_timestamp']})")

        if status["resumable_year"]:
            console.print(f"  🔄 Resumable from: Year {status['resumable_year']}")

        # Configuration compatibility
        if status["config_compatible"]:
            console.print("  ✅ [green]Configuration compatible[/green]")
        else:
            show_warning_message("Configuration has changed since last checkpoint")

        # Recommendations
        if status["recommendations"]:
            console.print("\n💡 [bold]Recommendations:[/bold]")
            for rec in status["recommendations"]:
                console.print(f"  • [dim]{rec}[/dim]")

        return 0

    except Exception as e:
        show_error_message(f"Failed to get recovery status: {e}")
        raise typer.Exit(1)

@checkpoint_command.command("cleanup")
def cleanup_checkpoints(
    keep: int = typer.Option(
        5, "--keep", help="Number of checkpoints to keep"
    ),
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    database: Optional[str] = typer.Option(
        None, "--database", help="Path to DuckDB database file"
    ),
):
    """Clean up old checkpoints, keeping the most recent ones."""
    try:
        config_path = Path(config) if config else find_default_config()
        db_path = Path(database) if database else Path("dbt/simulation.duckdb")

        wrapper = OrchestratorWrapper(config_path, db_path)
        removed = wrapper.checkpoint_manager.cleanup_old_checkpoints(keep)

        if removed > 0:
            show_success_message(f"Cleaned up {removed} old checkpoint file(s), keeping latest {keep}")
        else:
            console.print("🧹 [dim]No checkpoints to clean up[/dim]")

        return 0

    except Exception as e:
        show_error_message(f"Cleanup failed: {e}")
        raise typer.Exit(1)

@checkpoint_command.command("validate")
def validate_recovery(
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    database: Optional[str] = typer.Option(
        None, "--database", help="Path to DuckDB database file"
    ),
):
    """Validate recovery environment and checkpoint integrity."""
    try:
        config_path = Path(config) if config else find_default_config()
        db_path = Path(database) if database else Path("dbt/simulation.duckdb")

        wrapper = OrchestratorWrapper(config_path, db_path)
        validation = wrapper.recovery_orchestrator.validate_recovery_environment()

        console.print("🔍 [bold blue]Recovery Environment Validation[/bold blue]")

        if validation["valid"]:
            show_success_message("Recovery environment is valid")
        else:
            show_error_message("Recovery environment has issues:")
            for issue in validation["issues"]:
                console.print(f"  • [red]{issue}[/red]")

        if validation["warnings"]:
            console.print("\n⚠️ [bold yellow]Warnings:[/bold yellow]")
            for warning in validation["warnings"]:
                console.print(f"  • [yellow]{warning}[/yellow]")

        return 0 if validation["valid"] else 1

    except Exception as e:
        show_error_message(f"Validation failed: {e}")
        raise typer.Exit(1)

# Default command shows status
@checkpoint_command.command(name="", hidden=True)
def default(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    database: Optional[str] = typer.Option(None, "--database"),
):
    """Default checkpoint command shows status."""
    checkpoint_status(config=config, database=database)
