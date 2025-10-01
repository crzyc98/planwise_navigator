"""
Progress indicators and spinners for PlanWise Navigator CLI

Rich-based progress bars, spinners, and status indicators for long-running operations.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TaskID,
)
from rich.spinner import Spinner
from rich.status import Status

console = Console()

@contextmanager
def create_progress_bar(description: str = "Processing...") -> Generator[Progress, None, None]:
    """Create a Rich progress bar for multi-step operations."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:
        yield progress

@contextmanager
def create_status_spinner(message: str = "Working...") -> Generator[Status, None, None]:
    """Create a spinner for indeterminate operations."""
    with Status(message, console=console, spinner="dots") as status:
        yield status

@contextmanager
def create_simulation_progress() -> Generator[tuple[Progress, dict], None, None]:
    """Create specialized progress tracker for multi-year simulations."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(complete_style="green", finished_style="bright_green"),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:

        # Task trackers
        tasks = {
            "overall": progress.add_task("🎯 Multi-year simulation", total=100),
            "current_year": None,
            "current_stage": None,
        }

        yield progress, tasks

def update_simulation_progress(
    progress: Progress,
    tasks: dict,
    year: int,
    stage: str,
    stage_progress: float = 0,
    year_progress: float = 0,
    overall_progress: float = 0
):
    """Update simulation progress with current year and stage information."""

    # Update current year task
    if tasks["current_year"] is None or year != getattr(tasks, "_current_year", None):
        if tasks["current_year"] is not None:
            progress.update(tasks["current_year"], completed=100)

        tasks["current_year"] = progress.add_task(f"📅 Year {year}", total=100)
        tasks["_current_year"] = year

    # Update current stage task
    if tasks["current_stage"] is None or stage != getattr(tasks, "_current_stage", None):
        if tasks["current_stage"] is not None:
            progress.update(tasks["current_stage"], completed=100)

        tasks["current_stage"] = progress.add_task(f"  ⚙️ {stage}", total=100)
        tasks["_current_stage"] = stage

    # Update all progress bars
    progress.update(tasks["current_stage"], completed=stage_progress)
    progress.update(tasks["current_year"], completed=year_progress)
    progress.update(tasks["overall"], completed=overall_progress)

@contextmanager
def create_batch_progress(scenario_count: int) -> Generator[tuple[Progress, TaskID], None, None]:
    """Create progress tracker for batch scenario processing."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(complete_style="green"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:

        main_task = progress.add_task("📊 Processing scenarios", total=scenario_count)
        yield progress, main_task

def create_dbt_progress() -> Progress:
    """Create progress indicator specifically for dbt operations."""
    return Progress(
        SpinnerColumn(spinner_style="blue"),
        TextColumn("[bold blue]dbt:[/bold blue] {task.description}"),
        BarColumn(complete_style="green"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )

class ProgressReporter:
    """Progress reporter for wrapping existing operations."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self._progress = None
        self._tasks = {}

    def start_operation(self, name: str, total: Optional[int] = None):
        """Start tracking an operation."""
        if self._progress is None:
            self._progress = create_dbt_progress()
            self._progress.start()

        task_id = self._progress.add_task(name, total=total or 100)
        self._tasks[name] = task_id
        return task_id

    def update_operation(self, name: str, advance: int = 1, completed: Optional[float] = None):
        """Update operation progress."""
        if name in self._tasks and self._progress:
            if completed is not None:
                self._progress.update(self._tasks[name], completed=completed)
            else:
                self._progress.advance(self._tasks[name], advance)

    def finish_operation(self, name: str):
        """Mark operation as complete."""
        if name in self._tasks and self._progress:
            self._progress.update(self._tasks[name], completed=100)

    def stop(self):
        """Stop progress tracking."""
        if self._progress:
            self._progress.stop()
            self._progress = None
        self._tasks.clear()

def show_success_message(message: str, details: Optional[str] = None):
    """Show a formatted success message."""
    console.print(f"✅ [bold green]{message}[/bold green]")
    if details:
        console.print(f"   [dim]{details}[/dim]")

def show_warning_message(message: str, details: Optional[str] = None):
    """Show a formatted warning message."""
    console.print(f"⚠️ [bold yellow]{message}[/bold yellow]")
    if details:
        console.print(f"   [dim]{details}[/dim]")

def show_error_message(message: str, details: Optional[str] = None):
    """Show a formatted error message."""
    console.print(f"❌ [bold red]{message}[/bold red]")
    if details:
        console.print(f"   [dim]{details}[/dim]")

class SimulationProgressTracker:
    """
    Progress tracker that monitors simulation output and updates progress bars.

    This class provides a context manager that tracks simulation progress by
    monitoring console output patterns and updating Rich progress bars accordingly.
    """

    def __init__(self, total_years: int, start_year: int, console: Console):
        self.total_years = total_years
        self.start_year = start_year
        self.console = console
        self.progress = None
        self.main_task = None
        self.current_year_task = None
        self.current_stage_task = None
        self.current_year = None

        # Define stage weights for progress calculation
        self.stage_weights = {
            "initialization": 15,
            "foundation": 20,
            "event_generation": 35,
            "state_accumulation": 20,
            "validation": 5,
            "reporting": 5
        }
        self.total_stage_weight = sum(self.stage_weights.values())

    def __enter__(self):
        # Create progress display
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(complete_style="green", finished_style="bright_green"),
            MofNCompleteColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            transient=False,
        )

        self.progress.start()

        # Main simulation task
        self.main_task = self.progress.add_task(
            "🎯 Multi-year simulation",
            total=100
        )

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.progress:
            self.progress.stop()

    def update_year(self, year: int):
        """Update progress when starting a new year."""
        self.current_year = year

        # Calculate overall progress based on completed years
        completed_years = year - self.start_year
        overall_progress = (completed_years / self.total_years) * 100

        self.progress.update(self.main_task, completed=overall_progress)

        # Add current year task if it doesn't exist
        if self.current_year_task is not None:
            self.progress.update(self.current_year_task, completed=100)

        self.current_year_task = self.progress.add_task(
            f"📅 Year {year}",
            total=100
        )

    def update_stage(self, stage: str):
        """Update progress when starting a new stage."""
        stage_lower = stage.lower().replace("_", " ")

        # Complete previous stage task
        if self.current_stage_task is not None:
            self.progress.update(self.current_stage_task, completed=100)

        # Add new stage task
        stage_emoji = {
            "initialization": "🔄",
            "foundation": "🏗️",
            "event_generation": "⚡",
            "state_accumulation": "📊",
            "validation": "✅",
            "reporting": "📋"
        }.get(stage_lower.replace(" ", "_"), "⚙️")

        self.current_stage_task = self.progress.add_task(
            f"  {stage_emoji} {stage_lower.title()}",
            total=100
        )

    def update_stage_progress(self, stage: str, progress_percent: float):
        """Update progress for the current stage."""
        if self.current_stage_task is not None:
            self.progress.update(self.current_stage_task, completed=progress_percent)

        # Update year progress based on stage completion
        if self.current_year_task is not None:
            stage_lower = stage.lower().replace("_", " ").replace(" ", "_")
            stage_weight = self.stage_weights.get(stage_lower, 10)

            # Calculate year progress (simplified - assumes equal stage distribution)
            year_progress = min(100, progress_percent * (stage_weight / self.total_stage_weight))
            self.progress.update(self.current_year_task, completed=year_progress)

    def complete(self):
        """Mark simulation as complete."""
        if self.current_stage_task is not None:
            self.progress.update(self.current_stage_task, completed=100)
        if self.current_year_task is not None:
            self.progress.update(self.current_year_task, completed=100)
        if self.main_task is not None:
            self.progress.update(self.main_task, completed=100)

    def error(self, message: str):
        """Mark simulation as failed."""
        if self.main_task is not None:
            self.progress.update(self.main_task, description="❌ Simulation failed")
