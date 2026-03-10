"""
Output capture utilities for Rich Live display coexistence.

Provides thread-safe mechanisms for routing subprocess output through
Rich's Console.print() to avoid display corruption during Live rendering,
and a plain-text fallback for non-interactive terminals.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Optional

from rich.console import Console

_SIGNAL_PATTERNS = re.compile(
    r'(error|warn|\d+ of \d+|^Running with dbt|^Finished running|^Done\.|OK created|FAIL|PASS)',
    re.IGNORECASE,
)
_NOISE_PATTERNS = re.compile(
    r'^\s*(select|from|where|with\s+\w|join|group by|order by|--|\[debug\]|={3,}|-{3,}|Concurrency:|registered in)',
    re.IGNORECASE,
)


def _is_signal_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _NOISE_PATTERNS.match(stripped):
        return False
    return bool(_SIGNAL_PATTERNS.search(stripped))


class OutputCapture:
    """Routes output lines through Rich Console.print() for safe Live display coexistence.

    When Rich's Live display is active, raw stdout writes cause visual corruption.
    This class uses Console.print() which Rich's Live context handles correctly,
    rendering text above the live display area.
    """

    def __init__(self, console: Console):
        self.console = console

    def capture_line(self, line: str) -> None:
        """Safely render a line of text during an active Rich Live display."""
        if line.strip():
            self.console.print(line, highlight=False)


class PlainTextProgressFallback:
    """Plain-text progress callback for non-interactive terminals.

    Implements the same interface as LiveProgressTracker but uses plain print()
    statements. Used when stdout is not a TTY (e.g., piped to a file).
    """

    def __init__(self, total_years: int, start_year: int, end_year: int, verbose: bool = False):
        self.total_years = total_years
        self.start_year = start_year
        self.end_year = end_year
        self.verbose = verbose
        self.current_year: Optional[int] = None
        self.current_stage: Optional[str] = None
        self.years_completed = 0

    def update_year(self, year: int) -> None:
        """Print year transition."""
        if self.current_year != year:
            if self.current_year is not None:
                self.years_completed += 1
            self.current_year = year
            print(f"[Progress] Starting year {year} ({self.years_completed}/{self.total_years} completed)")

    def update_stage(self, stage: str) -> None:
        """Print stage transition."""
        self.current_stage = stage
        stage_display = stage.replace('_', ' ').title()
        print(f"[Progress] Stage: {stage_display}")

    def stage_completed(self, stage: str, duration: float) -> None:
        """Print stage completion."""
        stage_display = stage.replace('_', ' ').title()
        print(f"[Progress] Completed {stage_display} in {duration:.1f}s")

    def update_events(self, event_count: int) -> None:
        """Print event count update."""
        print(f"[Progress] Generated {event_count:,} events")

    def year_validation(self, year: int) -> None:
        """Print year validation completion."""
        print(f"[Progress] Year {year} validation complete")

    def on_dbt_line(self, line: str) -> None:
        """Print dbt output line in verbose mode (signal lines only)."""
        if self.verbose and _is_signal_line(line):
            print(f"[dbt] {line}")


def is_tty() -> bool:
    """Detect whether stdout is an interactive terminal.

    Returns False when stdout is redirected to a file or pipe,
    or when running on Windows without ANSI support.
    """
    if not sys.stdout.isatty():
        return False

    if os.name == 'nt':
        # On Windows, check for ANSI support via environment or Rich detection
        term = os.environ.get('TERM', '')
        wt_session = os.environ.get('WT_SESSION', '')
        if term or wt_session:
            return True
        # Fall back to Rich's terminal detection
        try:
            test_console = Console()
            return test_console.is_terminal
        except Exception:
            return False

    return True
