"""
Sync command for Fidelity PlanAlign Engine CLI (E083).

Workspace cloud synchronization using Git.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def _get_sync_service():
    """Get sync service instance with error handling."""
    try:
        from planalign_api.services.sync_service import SyncService
        return SyncService()
    except ImportError as e:
        console.print("[red]GitPython is required for sync functionality.[/red]")
        console.print("Install it with: [cyan]pip install GitPython[/cyan]")
        raise typer.Exit(1)


def sync_init(
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
    """Initialize workspace sync with a Git remote.

    Sets up Git-based synchronization for all PlanAlign workspaces.
    Your workspace configurations, scenario metadata, and run history
    will be version-controlled and syncable across devices.

    Examples:
        planalign sync init git@github.com:user/planalign-workspaces.git
        planalign sync init https://github.com/user/planalign-workspaces.git --branch dev
    """
    from planalign_api.services.sync_service import SyncError, SyncAuthError

    sync_service = _get_sync_service()

    with console.status("[bold blue]Initializing sync...[/bold blue]"):
        try:
            status = sync_service.init(
                remote_url=remote_url,
                branch=branch,
                auto_sync=auto_sync,
            )

            console.print()
            console.print(Panel(
                f"[green]Sync initialized successfully![/green]\n\n"
                f"Remote: [cyan]{remote_url}[/cyan]\n"
                f"Branch: [cyan]{branch}[/cyan]\n"
                f"Auto-sync: [cyan]{'Enabled' if auto_sync else 'Disabled'}[/cyan]\n\n"
                f"Use [bold]planalign sync push[/bold] to upload workspaces.\n"
                f"Use [bold]planalign sync pull[/bold] to download changes.",
                title="Sync Initialized",
                border_style="green",
            ))

        except SyncAuthError as e:
            console.print(f"\n[red]Authentication failed:[/red] {e}")
            console.print("\n[dim]Tips:[/dim]")
            console.print("  - For SSH: Ensure your SSH key is added to GitHub/GitLab")
            console.print("  - For HTTPS: Use a personal access token as password")
            raise typer.Exit(1)

        except SyncError as e:
            console.print(f"\n[red]Sync initialization failed:[/red] {e}")
            raise typer.Exit(1)


def sync_push(
    message: Optional[str] = typer.Option(
        None,
        "--message", "-m",
        help="Custom commit message"
    ),
):
    """Push local workspace changes to remote.

    Stages and commits all workspace metadata files (JSON, YAML),
    then pushes to the configured remote repository.

    Large files like DuckDB databases and Excel exports are excluded
    automatically - they can be regenerated from the synced configurations.

    Examples:
        planalign sync push
        planalign sync push -m "Added new Q4 projection scenarios"
    """
    from planalign_api.services.sync_service import SyncError, SyncAuthError

    sync_service = _get_sync_service()

    # Check if initialized
    if not sync_service.is_initialized():
        console.print("[yellow]Sync not initialized.[/yellow]")
        console.print("Run [cyan]planalign sync init <remote-url>[/cyan] first.")
        raise typer.Exit(1)

    with console.status("[bold blue]Pushing changes...[/bold blue]"):
        try:
            result = sync_service.push(message=message)

            if result.success:
                if result.files_pushed == 0:
                    console.print("[dim]Nothing to push. Workspaces are up to date.[/dim]")
                else:
                    console.print()
                    console.print(Panel(
                        f"[green]Push successful![/green]\n\n"
                        f"Files pushed: [cyan]{result.files_pushed}[/cyan]\n"
                        f"Commit: [cyan]{result.commit_sha}[/cyan]",
                        title="Push Complete",
                        border_style="green",
                    ))
            else:
                console.print(f"[red]Push failed:[/red] {result.message}")
                raise typer.Exit(1)

        except SyncAuthError as e:
            console.print(f"\n[red]Authentication failed:[/red] {e}")
            raise typer.Exit(1)

        except SyncError as e:
            console.print(f"\n[red]Push failed:[/red] {e}")
            raise typer.Exit(1)


def sync_pull():
    """Pull remote changes to local workspaces.

    Downloads any changes from the remote repository and
    merges them with your local workspaces.

    If conflicts occur, they are handled according to your
    configured conflict strategy (default: last-write-wins).

    Example:
        planalign sync pull
    """
    from planalign_api.services.sync_service import SyncError, SyncAuthError

    sync_service = _get_sync_service()

    # Check if initialized
    if not sync_service.is_initialized():
        console.print("[yellow]Sync not initialized.[/yellow]")
        console.print("Run [cyan]planalign sync init <remote-url>[/cyan] first.")
        raise typer.Exit(1)

    with console.status("[bold blue]Pulling changes...[/bold blue]"):
        try:
            result = sync_service.pull()

            if result.success:
                if result.files_updated == 0 and result.files_added == 0:
                    console.print("[dim]Already up to date.[/dim]")
                else:
                    console.print()
                    console.print(Panel(
                        f"[green]Pull successful![/green]\n\n"
                        f"Files updated: [cyan]{result.files_updated}[/cyan]\n"
                        f"Files added: [cyan]{result.files_added}[/cyan]\n"
                        f"Files removed: [cyan]{result.files_removed}[/cyan]",
                        title="Pull Complete",
                        border_style="green",
                    ))
            else:
                if result.conflicts:
                    console.print(f"\n[yellow]Conflicts detected in {len(result.conflicts)} file(s):[/yellow]")
                    for conflict in result.conflicts[:10]:
                        console.print(f"  - {conflict}")
                    if len(result.conflicts) > 10:
                        console.print(f"  ... and {len(result.conflicts) - 10} more")
                    console.print("\n[dim]Resolve conflicts manually or use --force to overwrite.[/dim]")
                else:
                    console.print(f"[red]Pull failed:[/red] {result.message}")
                raise typer.Exit(1)

        except SyncAuthError as e:
            console.print(f"\n[red]Authentication failed:[/red] {e}")
            raise typer.Exit(1)

        except SyncError as e:
            console.print(f"\n[red]Pull failed:[/red] {e}")
            raise typer.Exit(1)


def sync_status():
    """Show current sync status.

    Displays information about:
    - Whether sync is initialized
    - The configured remote and branch
    - Number of local changes pending
    - Whether you're ahead/behind the remote

    Example:
        planalign sync status
    """
    sync_service = _get_sync_service()

    status = sync_service.get_status()

    if not status.is_initialized:
        console.print()
        console.print(Panel(
            "[yellow]Sync not initialized[/yellow]\n\n"
            "Run [cyan]planalign sync init <remote-url>[/cyan] to enable workspace sync.\n\n"
            "[dim]Syncing allows you to:[/dim]\n"
            "  - Access workspaces from any device\n"
            "  - Version control your scenario configurations\n"
            "  - Share workspaces with teammates",
            title="Sync Status",
            border_style="yellow",
        ))
        return

    # Build status display
    lines = []

    # Remote info
    lines.append(f"Remote: [cyan]{status.remote_url}[/cyan]")
    lines.append(f"Branch: [cyan]{status.branch}[/cyan]")
    lines.append("")

    # Changes status
    if status.local_changes > 0:
        lines.append(f"[yellow]Local changes:[/yellow] {status.local_changes} file(s) to push")
    else:
        lines.append("[green]Local:[/green] No uncommitted changes")

    # Ahead/behind
    if status.ahead > 0:
        lines.append(f"[yellow]Ahead:[/yellow] {status.ahead} commit(s) to push")
    if status.behind > 0:
        lines.append(f"[yellow]Behind:[/yellow] {status.behind} commit(s) to pull")

    if status.ahead == 0 and status.behind == 0 and status.local_changes == 0:
        lines.append("[green]Up to date with remote[/green]")

    # Last sync
    if status.last_sync:
        lines.append("")
        lines.append(f"Last sync: [dim]{status.last_sync.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")

    # Conflicts
    if status.conflicts:
        lines.append("")
        lines.append(f"[red]Conflicts:[/red] {len(status.conflicts)} file(s)")

    # Error
    if status.error:
        lines.append("")
        lines.append(f"[red]Error:[/red] {status.error}")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title="Sync Status",
        border_style="blue",
    ))

    # Show workspace summary
    workspace_infos = sync_service.get_workspace_sync_info()
    if workspace_infos:
        console.print()
        table = Table(title="Workspaces", show_header=True, header_style="bold blue")
        table.add_column("Workspace", style="cyan")
        table.add_column("Scenarios", justify="center")
        table.add_column("Status", justify="center")

        for info in workspace_infos:
            status_icon = "[yellow]Modified[/yellow]" if info.has_local_changes else "[green]Synced[/green]"
            table.add_row(
                info.workspace_name,
                str(info.scenario_count),
                status_icon,
            )

        console.print(table)


def sync_log(
    limit: int = typer.Option(
        20,
        "--limit", "-n",
        help="Number of log entries to show"
    ),
):
    """Show sync operation history.

    Displays recent push, pull, and other sync operations
    with timestamps and details.

    Examples:
        planalign sync log
        planalign sync log -n 50
    """
    sync_service = _get_sync_service()

    if not sync_service.is_initialized():
        console.print("[yellow]Sync not initialized.[/yellow]")
        console.print("Run [cyan]planalign sync init <remote-url>[/cyan] first.")
        raise typer.Exit(1)

    logs = sync_service.get_sync_log(limit=limit)

    if not logs:
        console.print("[dim]No sync history yet.[/dim]")
        return

    console.print()
    table = Table(title="Sync History", show_header=True, header_style="bold blue")
    table.add_column("Time", style="dim")
    table.add_column("Operation")
    table.add_column("Details")
    table.add_column("Status", justify="center")

    operation_icons = {
        "push": "[green]Push[/green]",
        "pull": "[blue]Pull[/blue]",
        "init": "[cyan]Init[/cyan]",
        "conflict": "[yellow]Conflict[/yellow]",
        "disconnect": "[red]Disconnect[/red]",
    }

    for entry in logs:
        status_icon = "[green]OK[/green]" if entry.success else "[red]FAIL[/red]"
        op_display = operation_icons.get(entry.operation, entry.operation)

        details = entry.message
        if entry.commit_sha:
            details += f" [{entry.commit_sha}]"

        table.add_row(
            entry.timestamp.strftime("%Y-%m-%d %H:%M"),
            op_display,
            details[:60] + "..." if len(details) > 60 else details,
            status_icon,
        )

    console.print(table)


def sync_disconnect():
    """Disconnect sync from remote.

    Removes the Git remote configuration but preserves all
    local workspace files. You can re-initialize sync later
    with a new or the same remote.

    Example:
        planalign sync disconnect
    """
    sync_service = _get_sync_service()

    if not sync_service.is_initialized():
        console.print("[dim]Sync is not initialized.[/dim]")
        return

    # Confirm
    confirm = typer.confirm(
        "This will disconnect sync but preserve local files. Continue?"
    )

    if not confirm:
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    if sync_service.disconnect():
        console.print()
        console.print(Panel(
            "[green]Sync disconnected.[/green]\n\n"
            "Local workspaces have been preserved.\n"
            "Run [cyan]planalign sync init <remote-url>[/cyan] to reconnect.",
            title="Disconnected",
            border_style="green",
        ))
    else:
        console.print("[red]Failed to disconnect sync.[/red]")
        raise typer.Exit(1)
