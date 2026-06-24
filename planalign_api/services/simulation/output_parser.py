"""Parse simulation subprocess stdout for progress tracking."""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List

from ...constants import MAX_RECENT_EVENTS

logger = logging.getLogger(__name__)

# Feature 094: sentinel prefix for structured telemetry records emitted by
# planalign_orchestrator.pipeline.telemetry_emitter (kept as a local constant
# so the API has no import-time coupling to the orchestrator package).
STRUCTURED_SENTINEL = "PLANALIGN_TELEMETRY|"

# Maximum line length to process — truncate before regex to prevent
# polynomial-time backtracking on adversarial input (ReDoS / SonarQube S5852).
_MAX_LINE_LENGTH = 1000

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
        # Feature 094: once a structured record is seen, regex-derived
        # stage/year/count guesses are suppressed for the rest of the run.
        self.structured_mode: bool = False

    def parse_line(self, line_text: str) -> Dict[str, Any]:
        """Parse a single output line and return a change summary.

        Returns a dict with keys that changed (``year_changed``,
        ``stage_changed``, ``new_event``, ``structured_record``) so the
        caller can decide whether to broadcast telemetry.
        """
        changes: Dict[str, Any] = {
            "year_changed": False,
            "stage_changed": False,
            "new_event": None,
            "structured_record": None,
        }

        # Feature 094: structured telemetry fast path
        if line_text.startswith(STRUCTURED_SENTINEL):
            self._parse_structured_line(line_text, changes)
            return changes

        if self.structured_mode:
            # Structured records own stage/year/counts; plain lines are only
            # relevant for severity classification (handled by the caller).
            return changes

        # Truncate to prevent ReDoS on adversarial input
        line_text = line_text[:_MAX_LINE_LENGTH]

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

    def _parse_structured_line(self, line_text: str, changes: Dict[str, Any]) -> None:
        """Apply a sentinel-prefixed JSON record to parser state."""
        try:
            record = json.loads(line_text[len(STRUCTURED_SENTINEL) :])
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Malformed structured telemetry line ignored: %s", e)
            return

        self.structured_mode = True
        changes["structured_record"] = record

        year = record.get("year")
        if isinstance(year, int) and year != self.current_year:
            self.current_year = year
            changes["year_changed"] = True

        stage = record.get("stage")
        if isinstance(stage, str) and stage and stage != self.current_stage:
            self.current_stage = stage
            changes["stage_changed"] = True

        cumulative = record.get("cumulative_counts")
        if isinstance(cumulative, dict) and cumulative:
            self.events_generated = sum(
                int(v) for v in cumulative.values() if isinstance(v, (int, float))
            )

    _STAGE_ORDER = (
        "INITIALIZATION",
        "FOUNDATION",
        "EVENT_GENERATION",
        "STATE_ACCUMULATION",
        "VALIDATION",
        "REPORTING",
    )

    def calculate_progress(self) -> int:
        """Return integer progress percentage (1-99) from year + stage position."""
        year_idx = max(0, self.current_year - self.start_year)
        try:
            stage_idx = self._STAGE_ORDER.index(self.current_stage)
        except ValueError:
            stage_idx = 0
        stage_fraction = stage_idx / len(self._STAGE_ORDER)
        progress = ((year_idx + stage_fraction) / max(self.total_years, 1)) * 100
        return int(min(max(progress, 1), 99))

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
        lower = line_text[:_MAX_LINE_LENGTH].lower()
        if any(kw in lower for kw in ERROR_KEYWORDS):
            return "error"
        if "warning" in lower:
            return "warning"
        return "debug"
