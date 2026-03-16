#!/usr/bin/env python3
"""
State Management Module for Pipeline Orchestration

Handles database state management and data cleanup operations.
Extracted from PipelineOrchestrator to improve modularity and maintainability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from config.constants import (
    MODEL_FCT_WORKFORCE_SNAPSHOT,
    TABLE_FCT_WORKFORCE_SNAPSHOT,
    TABLE_FCT_YEARLY_EVENTS,
)
from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.dbt_runner import DbtRunner
from planalign_orchestrator.utils import DatabaseConnectionManager


class StateManager:
    """Manages database state operations for multi-year simulation pipeline.

    Responsibilities:
    - Clearing year-specific data for idempotent re-runs
    - Full database resets based on configuration
    - State verification and validation

    This class encapsulates all state management logic previously embedded in
    PipelineOrchestrator, enabling cleaner separation of concerns and easier testing.
    """

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        dbt_runner: DbtRunner,
        config: SimulationConfig,
        verbose: bool = False,
    ):
        """Initialize StateManager with required dependencies.

        Args:
            db_manager: Database connection manager for executing queries
            dbt_runner: dbt command runner for model execution
            config: Simulation configuration containing setup options
            verbose: Enable verbose logging output
        """
        self.db_manager = db_manager
        self.dbt_runner = dbt_runner
        self.config = config
        self.verbose = verbose

    def maybe_clear_year_data(self, year: int) -> None:
        """Clear year-scoped data for idempotent re-runs when configured.

        Respects config.setup.clear_tables and config.setup.clear_table_patterns.
        Only deletes rows for the given simulation_year when the column exists.

        This method enables idempotent pipeline execution by removing stale data
        from previous runs while preserving data from other simulation years.

        Args:
            year: Simulation year to clear data for

        Configuration:
            setup.clear_tables: bool - Enable/disable clearing
            setup.clear_mode: str - 'year' for per-year, 'all' for full reset
            setup.clear_table_patterns: list - Table prefixes to clear (default: ['int_', 'fct_'])
        """
        setup = getattr(self.config, "setup", None)
        if not isinstance(setup, dict):
            return
        if not setup.get("clear_tables"):
            return
        # Respect clear_mode setting; skip year-level clears if full reset is requested
        clear_mode = setup.get("clear_mode", "all").lower()
        if clear_mode == "all":
            return
        patterns = setup.get("clear_table_patterns", ["int_", "fct_"])

        def _should_clear(name: str) -> bool:
            return any(name.startswith(p) for p in patterns)

        def _run(conn):
            tables = [
                r[0]
                for r in conn.execute(
                    """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
                """
                ).fetchall()
            ]
            cleared = 0
            for t in tables:
                if not _should_clear(t):
                    continue
                # check if table has simulation_year column
                has_col = conn.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='main' AND table_name = ? AND column_name = 'simulation_year'
                    LIMIT 1
                    """,
                    [t],
                ).fetchone()
                if has_col:
                    conn.execute(f"DELETE FROM {t} WHERE simulation_year = ?", [year])
                    cleared += 1
            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared:
            print(
                f"🧹 Cleared year {year} rows in {cleared} table(s) per setup.clear_table_patterns"
            )

    def maybe_full_reset(self) -> None:
        """If configured, clear all rows from matching tables before yearly processing.

        Controlled by:
          setup.clear_tables: true/false - Master switch for clearing
          setup.clear_mode: 'all' (default) or 'year' - Full vs. incremental clearing
          setup.clear_table_patterns: list of prefixes - Tables to clear (default ['int_', 'fct_'])

        This method enables clean-slate simulation runs by removing all data from
        intermediate and fact tables, useful for debugging or when configuration
        changes require complete rebuilds.

        Configuration:
            setup.clear_tables: bool - Enable/disable clearing
            setup.clear_mode: str - Must be 'all' for this method to execute
            setup.clear_table_patterns: list - Table prefixes to clear
        """
        setup = getattr(self.config, "setup", None)
        if not isinstance(setup, dict) or not setup.get("clear_tables"):
            return
        clear_mode = setup.get("clear_mode", "all").lower()
        if clear_mode != "all":
            return
        patterns = setup.get("clear_table_patterns", ["int_", "fct_"])

        def _should_clear(name: str) -> bool:
            return any(name.startswith(p) for p in patterns)

        def _run(conn):
            tables = [
                r[0]
                for r in conn.execute(
                    """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
                ).fetchall()
            ]
            cleared = 0
            for t in tables:
                if not _should_clear(t):
                    continue
                conn.execute(f"DELETE FROM {t}")
                cleared += 1
            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared:
            print(
                f"🧹 Full reset: cleared all rows in {cleared} table(s) per setup.clear_table_patterns"
            )

    def clear_year_fact_rows(self, year: int) -> None:
        """Idempotency guard: remove current-year rows in core fact tables before rebuild.

        This avoids duplicate events/snapshots when event sequencing changes between runs.
        Essential for maintaining data integrity during development and debugging.

        Targets critical fact tables:
        - fct_yearly_events: All workforce events for the year
        - fct_workforce_snapshot: Point-in-time workforce state
        - fct_employer_match_events: Employer contribution events

        Args:
            year: Simulation year to clear fact rows for

        Note:
            Silently handles tables that don't exist yet (graceful degradation).
            Uses database retry logic for resilience.
        """

        def _run(conn):
            for table in (
                TABLE_FCT_YEARLY_EVENTS,
                TABLE_FCT_WORKFORCE_SNAPSHOT,
                "fct_employer_match_events",
            ):
                try:
                    conn.execute(
                        f"DELETE FROM {table} WHERE simulation_year = ?", [year]
                    )
                except Exception:
                    # Table may not exist yet; ignore
                    pass
            return True

        try:
            self.db_manager.execute_with_retry(_run)
        except Exception:
            pass

    def verify_year_population(
        self, year: int, dbt_vars: Optional[dict] = None
    ) -> None:
        """Verify critical tables have rows for the given year; attempt one retry if empty.

        Performs data quality validation on core fact tables to ensure the pipeline
        produced valid output. If snapshot table is empty but events exist, attempts
        a targeted rebuild of the snapshot model.

        Validation checks:
        - fct_workforce_snapshot has rows for the year
        - fct_yearly_events has rows for the year
        - Snapshot count >= 0 (zero is allowed but triggers warning)

        Args:
            year: Simulation year to validate
            dbt_vars: Optional dbt variables to pass to rebuild command

        Behavior:
            - If snapshot is empty but events exist: Attempts one rebuild
            - If rebuild fails: Logs warning but continues
            - If snapshot remains empty: Logs warning for investigation
        """

        def _counts(conn):
            snap = conn.execute(
                f"SELECT COUNT(*) FROM {TABLE_FCT_WORKFORCE_SNAPSHOT} WHERE simulation_year = ?",
                [year],
            ).fetchone()[0]
            events = conn.execute(
                f"SELECT COUNT(*) FROM {TABLE_FCT_YEARLY_EVENTS} WHERE simulation_year = ?",
                [year],
            ).fetchone()[0]
            return int(snap), int(events)

        snap_count, event_count = self.db_manager.execute_with_retry(_counts)
        if snap_count == 0 and event_count > 0:
            # Attempt targeted rebuild of snapshot once
            try:
                def _clear(conn):
                    conn.execute(
                        f"DELETE FROM {TABLE_FCT_WORKFORCE_SNAPSHOT} WHERE simulation_year = ?",
                        [year],
                    )
                    return True
                self.db_manager.execute_with_retry(_clear)
            except Exception:
                pass
            res = self.dbt_runner.execute_command(
                ["run", "--select", MODEL_FCT_WORKFORCE_SNAPSHOT],
                simulation_year=year,
                dbt_vars=dbt_vars or {},
                stream_output=True,
            )
            if not res.success:
                print(f"⚠️ Retry build of {TABLE_FCT_WORKFORCE_SNAPSHOT} failed for {year}")
            else:
                snap_count, _ = self.db_manager.execute_with_retry(_counts)
        if snap_count == 0:
            print(
                f"⚠️ {TABLE_FCT_WORKFORCE_SNAPSHOT} has 0 rows for {year}; verify upstream models and vars"
            )
