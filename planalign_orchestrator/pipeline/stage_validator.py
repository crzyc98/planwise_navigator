#!/usr/bin/env python3
"""
Stage Validator

Validates pipeline stage completion with diagnostic output. Extracted from
PipelineOrchestrator to reduce complexity per Principle II (Modular Architecture).

This class encapsulates stage-specific validation logic for FOUNDATION,
EVENT_GENERATION, and STATE_ACCUMULATION stages with detailed row count reporting.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .workflow import WorkflowStage, StageDefinition

logger = logging.getLogger(__name__)
from .year_executor import PipelineStageError  # noqa: E402

if TYPE_CHECKING:
    from ..config import SimulationConfig
    from ..utils import DatabaseConnectionManager
    from .state_manager import StateManager


class StageValidator:
    """
    Validates pipeline stage completion with diagnostic output.

    Provides stage-specific validation for FOUNDATION, EVENT_GENERATION,
    and STATE_ACCUMULATION stages with detailed row count reporting.
    """

    def __init__(
        self,
        db_manager: "DatabaseConnectionManager",
        config: "SimulationConfig",
        state_manager: "StateManager",
        verbose: bool = False,
    ):
        """
        Initialize stage validator.

        Args:
            db_manager: Database connection manager for queries
            config: Simulation configuration (for start_year reference)
            state_manager: State manager (for verify_year_population)
            verbose: Enable verbose output
        """
        self.db_manager = db_manager
        self.config = config
        self.state_manager = state_manager
        self.verbose = verbose

    def validate_stage(
        self, stage: StageDefinition, year: int, fail_on_error: bool = False
    ) -> None:
        """
        Run validation checks for a completed workflow stage.

        Args:
            stage: Stage definition with stage.name indicating which validation
            year: Simulation year being validated
            fail_on_error: If True, raise PipelineStageError on validation failure

        Raises:
            PipelineStageError: On critical validation failures

        Behavior:
            - FOUNDATION: Validates row counts in foundation models
            - EVENT_GENERATION: Validates hire events vs demand
            - STATE_ACCUMULATION: Delegates to state_manager.verify_year_population
            - Always prints diagnostic output
        """
        if stage.name == WorkflowStage.FOUNDATION:
            self._validate_foundation(year)
        elif stage.name == WorkflowStage.EVENT_GENERATION:
            self._validate_event_generation(year)
        elif stage.name == WorkflowStage.STATE_ACCUMULATION:
            self._validate_state_accumulation(year)

    def _validate_foundation(self, year: int) -> None:
        """Validate FOUNDATION stage outputs with comprehensive row count checks."""
        start_year = self.config.simulation.start_year

        def _chk(conn):
            baseline = self._safe_count(conn, "int_baseline_workforce", year)
            # For years > start_year, baseline lives in start_year; fetch preserved baseline rows
            preserved_baseline = self._safe_count(
                conn, "int_baseline_workforce", start_year
            )
            compensation = self._safe_count(
                conn, "int_employee_compensation_by_year", year
            )
            wn = self._safe_count(conn, "int_workforce_needs", year)
            wnbl = self._safe_count(conn, "int_workforce_needs_by_level", year)
            # Epic E039: Employer contribution model validation (eligibility may not be built in FOUNDATION)
            employer_elig = self._safe_count(conn, "int_employer_eligibility", year)
            # int_employer_core_contributions is built in STATE_ACCUMULATION, not FOUNDATION
            employer_core = self._safe_count(
                conn, "int_employer_core_contributions", year
            )
            # Diagnostics: hiring demand (safe query with COALESCE for missing tables)
            try:
                total_hires_needed = conn.execute(
                    "SELECT COALESCE(MAX(total_hires_needed), 0) FROM int_workforce_needs WHERE simulation_year = ?",
                    [year],
                ).fetchone()[0]
            except Exception:
                total_hires_needed = 0
            try:
                level_hires_needed = conn.execute(
                    "SELECT COALESCE(SUM(hires_needed), 0) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                    [year],
                ).fetchone()[0]
            except Exception:
                level_hires_needed = 0
            return (
                int(baseline),
                int(preserved_baseline),
                int(compensation),
                int(wn),
                int(wnbl),
                int(employer_elig or 0),
                int(employer_core or 0),
                int(total_hires_needed or 0),
                int(level_hires_needed or 0),
            )

        (
            baseline_cnt,
            preserved_baseline_cnt,
            comp_cnt,
            wn_cnt,
            wnbl_cnt,
            employer_elig_cnt,
            employer_core_cnt,
            total_hires_needed,
            level_hires_needed,
        ) = self.db_manager.execute_with_retry(_chk)

        logger.info("Foundation model validation for year %d:", year)
        if year == start_year:
            logger.info("  int_baseline_workforce: %d rows", baseline_cnt)
        else:
            # Baseline is only populated in start_year; show preserved baseline for clarity
            logger.info(
                "  int_baseline_workforce: %d rows (current year); preserved baseline %d rows (start_year=%d)",
                baseline_cnt,
                preserved_baseline_cnt,
                start_year,
            )
        logger.info("  int_employee_compensation_by_year: %d rows", comp_cnt)
        logger.info("  int_workforce_needs: %d rows", wn_cnt)
        logger.info("  int_workforce_needs_by_level: %d rows", wnbl_cnt)
        logger.info(
            "  int_employer_eligibility: %d rows (not built in FOUNDATION)",
            employer_elig_cnt,
        )
        logger.info(
            "  int_employer_core_contributions: %d rows (built later in STATE_ACCUMULATION)",
            employer_core_cnt,
        )
        logger.info("  hiring_demand.total_hires_needed: %d", total_hires_needed)
        logger.info("  hiring_demand.sum_by_level: %d", level_hires_needed)

        # Epic E042 Fix: Only validate baseline workforce for first year
        if baseline_cnt == 0 and year == self.config.simulation.start_year:
            raise PipelineStageError(
                f"CRITICAL: int_baseline_workforce has 0 rows for year {year}. Check census data processing."
            )
        elif baseline_cnt == 0 and year > self.config.simulation.start_year:
            logger.info(
                "int_baseline_workforce has 0 rows for year %d (expected). Baseline is preserved in start_year=%d with %d rows.",
                year,
                start_year,
                preserved_baseline_cnt,
            )
        if comp_cnt == 0:
            raise PipelineStageError(
                f"CRITICAL: int_employee_compensation_by_year has 0 rows for year {year}. Foundation models are broken."
            )
        if wn_cnt == 0 or wnbl_cnt == 0:
            raise PipelineStageError(
                f"CRITICAL: workforce_needs rows={wn_cnt}, by_level rows={wnbl_cnt} for {year}. Hiring will fail."
            )
        if employer_elig_cnt == 0:
            logger.info(
                "int_employer_eligibility has 0 rows for year %d (expected before EVENT_GENERATION).",
                year,
            )
        if employer_core_cnt == 0:
            logger.info(
                "int_employer_core_contributions has 0 rows for year %d (expected; built during STATE_ACCUMULATION).",
                year,
            )
        if total_hires_needed == 0 or level_hires_needed == 0:
            logger.warning(
                "Hiring demand calculated as 0; new hire events will not be generated. Verify target_growth_rate and termination rates."
            )

    def _validate_event_generation(self, year: int) -> None:
        """Validate EVENT_GENERATION stage outputs - ensure hires materialized."""

        def _ev_chk(conn):
            hires = conn.execute(
                "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ?",
                [year],
            ).fetchone()[0]
            demand = conn.execute(
                "SELECT COALESCE(SUM(hires_needed),0) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                [year],
            ).fetchone()[0]
            try:
                projection = conn.execute(
                    "SELECT COUNT(*) FROM enrollment_decision_projection WHERE decision_year = ?",
                    [year],
                ).fetchone()[0]
            except Exception:
                projection = 0
            return int(hires), int(demand), int(projection)

        hires_cnt, demand_cnt, projection_cnt = self.db_manager.execute_with_retry(
            _ev_chk
        )
        logger.info("Event generation validation for year %d:", year)
        logger.info("  int_hiring_events: %d rows", hires_cnt)
        logger.info("  enrollment_decision_projection: %d rows", projection_cnt)
        logger.info("  hiring_demand (sum_by_level): %d", demand_cnt)
        if hires_cnt == 0 and demand_cnt > 0:
            raise PipelineStageError(
                f"CRITICAL: Hiring demand={demand_cnt} but 0 int_hiring_events rows for {year}. Check hiring logic."
            )

    def _validate_state_accumulation(self, year: int) -> None:
        """Validate STATE_ACCUMULATION stage - verify population exists."""
        self.state_manager.verify_year_population(year)

    def _safe_count(self, conn, table: str, year_val: int) -> int:
        """
        Safely query table row counts (handles missing tables).

        Args:
            conn: Database connection
            table: Table name to query
            year_val: Simulation year to filter by

        Returns:
            Row count, or 0 if table doesn't exist
        """
        try:
            return conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE simulation_year = ?",
                [year_val],
            ).fetchone()[0]
        except Exception:
            # Table doesn't exist yet (expected on first run in new workspace)
            return 0
