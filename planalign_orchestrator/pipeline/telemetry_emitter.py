"""Structured telemetry emitter for PlanAlign Studio (feature 094).

Emits single-line JSON records to stdout with a sentinel prefix at run, stage,
and year boundaries. The Studio API subprocess-streams stdout and parses these
records deterministically instead of regex-guessing progress from log text.

Contract: specs/094-live-run-dashboard/contracts/telemetry-stdout-protocol.md
Emission is gated by the ``PLANALIGN_STRUCTURED_TELEMETRY=1`` environment
variable so plain CLI usage is unaffected.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TextIO

from planalign_orchestrator.pipeline.hooks import Hook, HookManager, HookType

logger = logging.getLogger(__name__)

SENTINEL = "PLANALIGN_TELEMETRY|"
PROTOCOL_VERSION = 1
ENV_FLAG = "PLANALIGN_STRUCTURED_TELEMETRY"
_MAX_RECORD_BYTES = 8192


class TelemetryEmitter:
    """Hook callbacks that print structured telemetry records to stdout."""

    def __init__(
        self,
        db_manager: Any = None,
        enabled: Optional[bool] = None,
        stream: Optional[TextIO] = None,
    ):
        if enabled is None:
            enabled = os.environ.get(ENV_FLAG) == "1"
        self.enabled = enabled
        self.db_manager = db_manager
        self.stream = stream if stream is not None else sys.stdout
        self._cumulative_counts: Dict[str, int] = {}
        self._start_year: Optional[int] = None

    # ------------------------------------------------------------------
    # Hook registration
    # ------------------------------------------------------------------

    def register(self, hook_manager: HookManager) -> None:
        """Register all emitter callbacks with the pipeline hook manager."""
        callbacks = [
            (HookType.PRE_SIMULATION, self.on_run_started, "telemetry_run_started"),
            (HookType.PRE_STAGE, self.on_stage_started, "telemetry_stage_started"),
            (HookType.POST_STAGE, self.on_stage_completed, "telemetry_stage_completed"),
            (HookType.POST_YEAR, self.on_year_completed, "telemetry_year_completed"),
            (
                HookType.POST_SIMULATION,
                self.on_run_completed,
                "telemetry_run_completed",
            ),
        ]
        for hook_type, callback, name in callbacks:
            hook_manager.register_hook(
                Hook(hook_type=hook_type, callback=callback, name=name)
            )

    # ------------------------------------------------------------------
    # Hook callbacks (context dicts come from HookManager.execute_hooks)
    # ------------------------------------------------------------------

    def on_run_started(self, context: Dict[str, Any]) -> None:
        start_year = context.get("start_year")
        self._start_year = start_year if isinstance(start_year, int) else None
        end_year = context.get("end_year")
        total_years = None
        if start_year is not None and end_year is not None:
            total_years = end_year - start_year + 1
        self._emit(
            {
                "record": "run_started",
                "start_year": start_year,
                "end_year": end_year,
                "total_years": total_years,
            }
        )

    def on_stage_started(self, context: Dict[str, Any]) -> None:
        self._emit(
            {
                "record": "stage_started",
                "year": context.get("year"),
                "stage": self._stage_name(context.get("stage")),
            }
        )

    def on_stage_completed(self, context: Dict[str, Any]) -> None:
        self._emit(
            {
                "record": "stage_completed",
                "year": context.get("year"),
                "stage": self._stage_name(context.get("stage")),
                "duration_seconds": context.get("duration_seconds"),
            }
        )
        validation = context.get("validation_evidence")
        if isinstance(validation, dict):
            self._emit(
                {
                    "record": "validation_results",
                    "year": context.get("year"),
                    "disposition": validation.get("disposition", "unavailable"),
                    "results": validation.get("results", []),
                }
            )

    def on_year_completed(self, context: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        year = context.get("year")
        year_counts = self._query_year_counts(year)
        for event_type, count in year_counts.items():
            self._cumulative_counts[event_type] = (
                self._cumulative_counts.get(event_type, 0) + count
            )
        self._emit(
            {
                "record": "year_completed",
                "year": year,
                "duration_seconds": context.get("duration_seconds"),
                "event_counts": year_counts,
                "cumulative_counts": dict(self._cumulative_counts),
                "workforce_reconciliation": self._query_reconciliation(
                    year, year_counts
                ),
            }
        )

    def on_run_completed(self, context: Dict[str, Any]) -> None:
        self._emit(
            {
                "record": "run_completed",
                "years_completed": context.get("completed_years", []),
                "duration_seconds": context.get("duration_seconds"),
            }
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _stage_name(stage: Any) -> Optional[str]:
        """Uppercase stage identifier (e.g. EVENT_GENERATION) from enum or str."""
        if stage is None:
            return None
        name = getattr(stage, "name", None)
        if isinstance(name, str):
            return name
        return str(stage).upper()

    def _query_year_counts(self, year: Optional[int]) -> Dict[str, int]:
        """Exact per-event-type counts for a year from fct_yearly_events.

        Uses the orchestrator's own connection manager — no cross-process
        lock contention with the running simulation.
        """
        if self.db_manager is None or year is None:
            return {}
        try:
            with self.db_manager.get_connection() as conn:
                rows = conn.execute(
                    "SELECT UPPER(event_type) AS event_type, COUNT(*) AS n "
                    "FROM fct_yearly_events WHERE simulation_year = ? "
                    "GROUP BY 1 ORDER BY 1",
                    [year],
                ).fetchall()
            return {row[0]: int(row[1]) for row in rows}
        except Exception as e:
            logger.warning("Telemetry year-count query failed for %s: %s", year, e)
            return {}

    def _query_reconciliation(
        self, year: Optional[int], event_counts: Dict[str, int]
    ) -> Dict[str, Any]:
        """Return aggregate workforce equation components for a completed year."""
        unavailable = {
            "opening_workforce": None,
            "hires": event_counts.get("HIRE", 0),
            "terminations": event_counts.get("TERMINATION", 0),
            "expected_closing_workforce": None,
            "actual_closing_workforce": None,
            "variance": None,
            "opening_source": "unavailable",
        }
        if self.db_manager is None or year is None:
            return unavailable
        try:
            with self.db_manager.get_connection() as conn:
                actual = conn.execute(
                    "SELECT COUNT(*) FROM fct_workforce_snapshot "
                    "WHERE simulation_year = ? AND lower(employment_status) = 'active'",
                    [year],
                ).fetchone()[0]
                if year == self._start_year:
                    opening = conn.execute(
                        "SELECT COUNT(*) FROM int_baseline_workforce "
                        "WHERE simulation_year = ? AND lower(employment_status) = 'active'",
                        [year],
                    ).fetchone()[0]
                    opening_source = "baseline"
                else:
                    opening = conn.execute(
                        "SELECT COUNT(*) FROM fct_workforce_snapshot "
                        "WHERE simulation_year = ? AND lower(employment_status) = 'active'",
                        [year - 1],
                    ).fetchone()[0]
                    opening_source = "prior_year_snapshot"
            hires = event_counts.get("HIRE", 0)
            terms = event_counts.get("TERMINATION", 0)
            opening = int(opening)
            expected = opening + hires - terms
            return {
                "opening_workforce": opening,
                "hires": hires,
                "terminations": terms,
                "expected_closing_workforce": expected,
                "actual_closing_workforce": int(actual),
                "variance": int(actual) - expected,
                "opening_source": opening_source,
            }
        except Exception as e:
            logger.warning("Telemetry reconciliation query failed for %s: %s", year, e)
            return unavailable

    def _emit(self, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        record = {
            "v": PROTOCOL_VERSION,
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": os.environ.get("PLANALIGN_RUN_ID"),
            **payload,
        }
        try:
            line = SENTINEL + json.dumps(record, separators=(",", ":"), default=str)
            if len(line.encode("utf-8")) > _MAX_RECORD_BYTES:
                logger.warning(
                    "Telemetry record exceeds %d bytes; dropped", _MAX_RECORD_BYTES
                )
                return
            self.stream.write(line + "\n")
            self.stream.flush()
        except Exception as e:
            # Telemetry must never break the pipeline.
            logger.warning("Telemetry emission failed: %s", e)
