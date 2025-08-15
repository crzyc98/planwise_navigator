#!/usr/bin/env python3
"""
Registry Management System for Navigator Orchestrator.

Provides type-safe, transactional registry operations for enrollment and
deferral escalation, with integrity validation and SQL templating.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

from .utils import DatabaseConnectionManager


@dataclass
class RegistryValidationResult:
    is_valid: bool
    errors: List[str]
    warnings: List[str]


class Registry(ABC):
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager

    @abstractmethod
    def create_table(self) -> bool:
        ...

    @abstractmethod
    def validate_integrity(self) -> RegistryValidationResult:
        ...


class SQLTemplateManager:
    """Manages SQL templates for registry operations."""

    ENROLLMENT_REGISTRY_CREATE = """
    CREATE TABLE IF NOT EXISTS enrollment_registry (
        employee_id VARCHAR PRIMARY KEY,
        first_enrollment_date DATE,
        first_enrollment_year INTEGER,
        enrollment_source VARCHAR,
        is_enrolled BOOLEAN,
        last_updated TIMESTAMP
    )
    """

    ENROLLMENT_REGISTRY_BASELINE = """
    INSERT INTO enrollment_registry
    SELECT DISTINCT
        employee_id,
        employee_enrollment_date AS first_enrollment_date,
        {year} AS first_enrollment_year,
        'baseline' AS enrollment_source,
        true AS is_enrolled,
        CURRENT_TIMESTAMP AS last_updated
    FROM int_baseline_workforce
    WHERE employment_status = 'active'
      AND employee_enrollment_date IS NOT NULL
      AND employee_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM enrollment_registry er WHERE er.employee_id = int_baseline_workforce.employee_id
      )
    """

    ENROLLMENT_REGISTRY_FROM_EVENTS = """
    INSERT INTO enrollment_registry
    SELECT
        fye.employee_id,
        COALESCE(MIN(fye.event_date), DATE '{year}-01-01') as first_enrollment_date,
        {year} AS first_enrollment_year,
        'event' AS enrollment_source,
        true AS is_enrolled,
        CURRENT_TIMESTAMP AS last_updated
    FROM fct_yearly_events fye
    WHERE fye.event_type IN ('enrollment', 'ENROLLMENT')
      AND fye.simulation_year = {year}
      AND fye.employee_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM enrollment_registry er WHERE er.employee_id = fye.employee_id
      )
    GROUP BY fye.employee_id
    """

    DEFERRAL_ESCALATION_CREATE = """
    CREATE TABLE IF NOT EXISTS deferral_escalation_registry (
        employee_id VARCHAR PRIMARY KEY,
        escalation_count INTEGER,
        last_escalation_date DATE,
        is_participating BOOLEAN,
        last_updated TIMESTAMP
    )
    """

    DEFERRAL_ESCALATION_UPDATE_FROM_EVENTS = """
    UPDATE deferral_escalation_registry AS t
    SET
      escalation_count = t.escalation_count + s.escalation_count,
      last_escalation_date = GREATEST(t.last_escalation_date, s.last_escalation_date),
      is_participating = TRUE,
      last_updated = CURRENT_TIMESTAMP
    FROM (
      SELECT
        fye.employee_id,
        COUNT(*) AS escalation_count,
        MAX(fye.effective_date) AS last_escalation_date
      FROM fct_yearly_events fye
      WHERE fye.event_type IN ('DEFERRAL_ESCALATION')
        AND fye.simulation_year = {year}
        AND fye.employee_id IS NOT NULL
      GROUP BY fye.employee_id
    ) s
    WHERE t.employee_id = s.employee_id
    """

    DEFERRAL_ESCALATION_INSERT_FROM_EVENTS = """
    INSERT INTO deferral_escalation_registry (
      employee_id, escalation_count, last_escalation_date, is_participating, last_updated
    )
    SELECT
      fye.employee_id,
      COUNT(*) AS escalation_count,
      MAX(fye.effective_date) AS last_escalation_date,
      TRUE AS is_participating,
      CURRENT_TIMESTAMP AS last_updated
    FROM fct_yearly_events fye
    WHERE fye.event_type IN ('DEFERRAL_ESCALATION')
      AND fye.simulation_year = {year}
      AND fye.employee_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM deferral_escalation_registry t WHERE t.employee_id = fye.employee_id
      )
    GROUP BY fye.employee_id
    """

    def render_template(self, template: str, **kwargs: Any) -> str:
        return template.format(**kwargs)


class TransactionalRegistry:
    """Mixin that provides atomic batch execution."""

    db_manager: DatabaseConnectionManager

    def execute_transaction(self, operations: List[str]) -> bool:
        with self.db_manager.transaction() as conn:
            try:
                for sql in operations:
                    conn.execute(sql)
                return True
            except Exception:
                return False


class EnrollmentRegistry(Registry, TransactionalRegistry):
    def __init__(self, db_manager: DatabaseConnectionManager):
        super().__init__(db_manager)
        self.sql = SQLTemplateManager()

    def create_table(self) -> bool:
        return self.execute_transaction([self.sql.ENROLLMENT_REGISTRY_CREATE])

    def create_for_year(self, year: int) -> bool:
        ops = [
            self.sql.ENROLLMENT_REGISTRY_CREATE,
            self.sql.render_template(self.sql.ENROLLMENT_REGISTRY_BASELINE, year=year),
        ]
        return self.execute_transaction(ops)

    def reset(self) -> bool:
        """Clear all rows to start a fresh simulation run.

        Registries are orchestrator-managed and not partitioned by simulation_year,
        so we need an explicit reset between runs to avoid stale state.
        """
        return self.execute_transaction([
            "DELETE FROM enrollment_registry"
        ])

    def update_post_year(self, year: int) -> bool:
        ops = [self.sql.render_template(self.sql.ENROLLMENT_REGISTRY_FROM_EVENTS, year=year)]
        return self.execute_transaction(ops)

    def get_enrolled_employees(self, year: int) -> List[str]:
        def _run(conn):
            rows = conn.execute(
                """
                SELECT employee_id
                FROM enrollment_registry
                WHERE is_enrolled = TRUE AND first_enrollment_year <= ?
                ORDER BY employee_id
                """,
                [year],
            ).fetchall()
            return [r[0] for r in rows]

        return self.db_manager.execute_with_retry(_run)

    def is_employee_enrolled(self, employee_id: str, year: int) -> bool:
        def _run(conn):
            row = conn.execute(
                """
                SELECT 1 FROM enrollment_registry
                WHERE employee_id = ? AND is_enrolled = TRUE AND first_enrollment_year <= ?
                LIMIT 1
                """,
                [employee_id, year],
            ).fetchone()
            return row is not None

        return self.db_manager.execute_with_retry(_run)

    def validate_integrity(self) -> RegistryValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        def _run(conn):
            orphaned = conn.execute(
                """
                SELECT COUNT(*) FROM enrollment_registry er
                WHERE NOT EXISTS (
                    SELECT 1 FROM fct_yearly_events fye
                    WHERE fye.employee_id = er.employee_id
                    AND fye.event_type IN ('enrollment','ENROLLMENT')
                )
                """
            ).fetchone()[0]

            duplicates = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT employee_id, COUNT(*) c
                    FROM enrollment_registry
                    GROUP BY employee_id HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]

            return orphaned, duplicates

        orphaned, duplicates = self.db_manager.execute_with_retry(_run)

        if orphaned > 0:
            errors.append(f"{orphaned} orphaned enrollments found")
        if duplicates > 0:
            errors.append(f"{duplicates} duplicate employee registrations")

        return RegistryValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


class DeferralEscalationRegistry(Registry, TransactionalRegistry):
    def __init__(self, db_manager: DatabaseConnectionManager):
        super().__init__(db_manager)
        self.sql = SQLTemplateManager()

    def create_table(self) -> bool:
        return self.execute_transaction([self.sql.DEFERRAL_ESCALATION_CREATE])

    def reset(self) -> bool:
        return self.execute_transaction([
            "DELETE FROM deferral_escalation_registry"
        ])

    def update_post_year(self, year: int) -> bool:
        ops = [
            self.sql.render_template(self.sql.DEFERRAL_ESCALATION_UPDATE_FROM_EVENTS, year=year),
            self.sql.render_template(self.sql.DEFERRAL_ESCALATION_INSERT_FROM_EVENTS, year=year),
        ]
        return self.execute_transaction(ops)

    def get_escalation_participants(self, year: int) -> List[str]:
        def _run(conn):
            rows = conn.execute(
                """
                SELECT employee_id
                FROM deferral_escalation_registry
                WHERE is_participating = TRUE
                ORDER BY employee_id
                """
            ).fetchall()
            return [r[0] for r in rows]

        return self.db_manager.execute_with_retry(_run)

    def get_escalation_count(self, employee_id: str) -> int:
        def _run(conn):
            row = conn.execute(
                """
                SELECT COALESCE(escalation_count, 0)
                FROM deferral_escalation_registry
                WHERE employee_id = ?
                """,
                [employee_id],
            ).fetchone()
            return int(row[0]) if row else 0

        return self.db_manager.execute_with_retry(_run)

    def validate_integrity(self) -> RegistryValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        def _run(conn):
            negatives = conn.execute(
                """
                SELECT COUNT(*) FROM deferral_escalation_registry
                WHERE escalation_count < 0
                """
            ).fetchone()[0]
            return negatives

        negatives = self.db_manager.execute_with_retry(_run)
        if negatives > 0:
            errors.append("Negative escalation counts detected")
        return RegistryValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


class RegistryManager:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager
        self._enrollment_registry: Optional[EnrollmentRegistry] = None
        self._deferral_registry: Optional[DeferralEscalationRegistry] = None

    def get_enrollment_registry(self) -> EnrollmentRegistry:
        if self._enrollment_registry is None:
            self._enrollment_registry = EnrollmentRegistry(self.db_manager)
        return self._enrollment_registry

    def get_deferral_registry(self) -> DeferralEscalationRegistry:
        if self._deferral_registry is None:
            self._deferral_registry = DeferralEscalationRegistry(self.db_manager)
        return self._deferral_registry

    def validate_all_registries(self, year: int) -> Dict[str, RegistryValidationResult]:
        return {
            "enrollment": self.get_enrollment_registry().validate_integrity(),
            "deferral": self.get_deferral_registry().validate_integrity(),
        }
