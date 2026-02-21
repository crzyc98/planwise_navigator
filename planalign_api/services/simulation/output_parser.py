"""Parse simulation subprocess stdout for progress tracking."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...constants import MAX_RECENT_EVENTS

# Stage detection patterns applied in priority order
STAGE_PATTERNS: Dict[str, str] = {
    "INITIALIZATION": r"[Ii]nitializ|[Ss]etup|[Ll]oading",
    "FOUNDATION": r"[Ff]oundation|[Bb]aseline",
    "EVENT_GENERATION": r"[Ee]vent|[Gg]enerat",
    "STATE_ACCUMULATION": r"[Ss]tate|[Aa]ccumul",
    "VALIDATION": r"[Vv]alidat",
    "REPORTING": r"[Rr]eport|[Cc]omplet",
}

ERROR_KEYWORDS = ("error", "exception", "failed", "traceback")


class SimulationOutputParser:
    """Stateful parser that tracks simulation progress from stdout lines.

    Accumulates year, stage, event count, and recent event entries
    as lines are fed in via ``parse_line()``.
    """

    def __init__(self, start_year: int, total_years: int):
        self.start_year = start_year
        self.total_years = total_years
        self.current_year: int = start_year
        self.current_stage: str = "INITIALIZATION"
        self.events_generated: int = 0
        self.recent_events: List[Dict[str, Any]] = []

    def parse_line(self, line_text: str) -> Dict[str, Any]:
        """Parse a single output line and return a change summary.

        Returns a dict with keys that changed (``year_changed``,
        ``stage_changed``, ``new_event``) so the caller can decide
        whether to broadcast telemetry.
        """
        changes: Dict[str, Any] = {
            "year_changed": False,
            "stage_changed": False,
            "new_event": None,
        }

        # Detect year transitions
        year_match = re.search(r"[Yy]ear[:\s]+(\d{4})", line_text)
        if year_match:
            new_year = int(year_match.group(1))
            if new_year != self.current_year:
                self.current_year = new_year
                changes["year_changed"] = True
                self._add_event(
                    "INFO",
                    f"Year {new_year}",
                    f"Processing simulation year {new_year}",
                )

        # Detect stage transitions
        prev_stage = self.current_stage
        for stage, pattern in STAGE_PATTERNS.items():
            if re.search(pattern, line_text):
                self.current_stage = stage
                break

        if self.current_stage != prev_stage:
            changes["stage_changed"] = True
            self._add_event(
                "STAGE",
                f"Year {self.current_year}",
                f"Entering {self.current_stage.replace('_', ' ').title()}",
            )

        # Parse aggregate event counts
        events_match = re.search(r"(\d+)\s*events?", line_text, re.IGNORECASE)
        if events_match:
            self.events_generated = int(events_match.group(1))

        # Parse individual event entries
        event_type_match = re.search(
            r"(HIRE|TERMINATION|PROMOTION|RAISE|ENROLLMENT)[\s:]+(\w+)",
            line_text,
            re.IGNORECASE,
        )
        if event_type_match:
            entry = self._add_event(
                event_type_match.group(1).upper(),
                event_type_match.group(2),
                line_text[:100],
            )
            changes["new_event"] = entry

        return changes

    def calculate_progress(self) -> int:
        """Return integer progress percentage (0-99) based on current year."""
        year_idx = self.current_year - self.start_year
        year_progress = (year_idx / self.total_years) * 100
        return int(min(year_progress + 10, 99))

    def _add_event(
        self, event_type: str, employee_id: str, details: str
    ) -> Dict[str, Any]:
        entry = {
            "event_type": event_type,
            "employee_id": employee_id,
            "timestamp": datetime.now().isoformat(),
            "details": details,
        }
        self.recent_events.insert(0, entry)
        self.recent_events = self.recent_events[:MAX_RECENT_EVENTS]
        return entry

    @staticmethod
    def classify_line(line_text: str) -> str:
        """Return ``'error'``, ``'warning'``, or ``'debug'`` for log routing."""
        lower = line_text.lower()
        if any(kw in lower for kw in ERROR_KEYWORDS):
            return "error"
        if "warning" in lower:
            return "warning"
        return "debug"
