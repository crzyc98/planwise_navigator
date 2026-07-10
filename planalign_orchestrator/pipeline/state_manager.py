#!/usr/bin/env python3
"""
State Management Module for Pipeline Orchestration

Handles database state management and data cleanup operations.
Extracted from PipelineOrchestrator to improve modularity and maintainability.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

from planalign_core.constants import (  # noqa: E402
    MODEL_FCT_WORKFORCE_SNAPSHOT,
    TABLE_FCT_WORKFORCE_SNAPSHOT,
    TABLE_FCT_YEARLY_EVENTS,
)
from planalign_orchestrator.config import SimulationConfig  # noqa: E402
from planalign_orchestrator.dbt_runner import DbtRunner  # noqa: E402
from planalign_orchestrator.utils import DatabaseConnectionManager  # noqa: E402


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

    def _year_scope(
        self, conn, table: str, year: int, *, critical: bool = False
    ) -> tuple[str, list[object]]:
        """Build a year filter scoped to the active scenario when supported.

        Falls back to ``"default"`` for unset scenario_id/plan_design_id, matching
        the same fallback dbt uses (``{{ var('scenario_id', 'default') }}``, see
        ``dbt/models/marts/fct_yearly_events.sql``) and the CLI export path
        (``planalign_orchestrator/config/export.py``). This keeps ordinary
        single-scenario runs (config.scenario_id is None) scoped consistently
        with what was actually written to the table, instead of treating the
        common case as "identifiers unavailable".
        """
        columns = {
            row[0]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'main' AND table_name = ?
                """,
                [table],
            ).fetchall()
        }
        scenario_id = self.config.scenario_id or "default"
        plan_design_id = self.config.plan_design_id or "default"

        predicates = ["simulation_year = ?"]
        parameters: list[object] = [year]
        has_scenario_column = "scenario_id" in columns
        has_plan_design_column = "plan_design_id" in columns
        if has_scenario_column:
            predicates.append("scenario_id = ?")
            parameters.append(scenario_id)
        if has_plan_design_column:
            predicates.append("plan_design_id = ?")
            parameters.append(plan_design_id)

        if critical and not (has_scenario_column and has_plan_design_column):
            logger.warning(
                "%s has no scenario_id/plan_design_id columns; year-only cleanup "
                "for simulation_year=%s may remove rows belonging to other "
                "scenarios/plan designs sharing this database. Schema migration "
                "is required to fully scope this table.",
                table,
                year,
            )

        return " AND ".join(predicates), parameters

    def _delete_year_rows(
        self, conn, table: str, year: int, *, critical: bool = False
    ) -> bool:
        """Delete year rows when the target table exists."""
        table_exists = conn.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = ?
            LIMIT 1
            """,
            [table],
        ).fetchone()
        if not table_exists:
            return False

        where_clause, parameters = self._year_scope(
            conn, table, year, critical=critical
        )
        conn.execute(f"DELETE FROM {table} WHERE {where_clause}", parameters)
        return True

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
        clear_mode = setup.get("clear_mode", "year").lower()
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
                if has_col and self._delete_year_rows(
                    conn,
                    t,
                    year,
                    critical=t
                    in (TABLE_FCT_YEARLY_EVENTS, TABLE_FCT_WORKFORCE_SNAPSHOT),
                ):
                    cleared += 1
            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared:
            logger.info(
                "Cleared year %d rows in %d table(s) per setup.clear_table_patterns",
                year,
                cleared,
            )

    def maybe_full_reset(self) -> None:
        """If configured, clear all rows from matching tables before yearly processing.

        Controlled by:
          setup.clear_tables: true/false - Master switch for clearing
          setup.clear_mode: 'all' (explicit run reset) or 'year' (default)
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
        clear_mode = setup.get("clear_mode", "year").lower()
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
            logger.info(
                "Full reset: cleared all rows in %d table(s) per setup.clear_table_patterns",
                cleared,
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
                    self._delete_year_rows(
                        conn,
                        table,
                        year,
                        critical=table
                        in (TABLE_FCT_YEARLY_EVENTS, TABLE_FCT_WORKFORCE_SNAPSHOT),
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
            snapshot_where, snapshot_parameters = self._year_scope(
                conn,
                TABLE_FCT_WORKFORCE_SNAPSHOT,
                year,
                critical=True,
            )
            events_where, events_parameters = self._year_scope(
                conn,
                TABLE_FCT_YEARLY_EVENTS,
                year,
                critical=True,
            )
            snap = conn.execute(
                f"SELECT COUNT(*) FROM {TABLE_FCT_WORKFORCE_SNAPSHOT} WHERE {snapshot_where}",
                snapshot_parameters,
            ).fetchone()[0]
            events = conn.execute(
                f"SELECT COUNT(*) FROM {TABLE_FCT_YEARLY_EVENTS} WHERE {events_where}",
                events_parameters,
            ).fetchone()[0]
            return int(snap), int(events)

        snap_count, event_count = self.db_manager.execute_with_retry(_counts)
        if snap_count == 0 and event_count > 0:
            # Attempt targeted rebuild of snapshot once
            try:

                def _clear(conn):
                    self._delete_year_rows(
                        conn,
                        TABLE_FCT_WORKFORCE_SNAPSHOT,
                        year,
                        critical=True,
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
                logger.warning(
                    "Retry build of %s failed for %d",
                    TABLE_FCT_WORKFORCE_SNAPSHOT,
                    year,
                )
            else:
                snap_count, _ = self.db_manager.execute_with_retry(_counts)
        if snap_count == 0:
            logger.warning(
                "%s has 0 rows for %d; verify upstream models and vars",
                TABLE_FCT_WORKFORCE_SNAPSHOT,
                year,
            )
