"""
Year auditor for single-year simulation reports.

Generates detailed audit reports for individual simulation years
with workforce breakdown, event summary, and data quality validation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING

from config.constants import (
    EVENT_HIRE,
    EVENT_TERMINATION,
    EVENT_TYPE_TERMINATION,
    MODEL_INT_BASELINE_WORKFORCE,
    TABLE_FCT_WORKFORCE_SNAPSHOT,
    TABLE_FCT_YEARLY_EVENTS,
)
from .data_models import (
    WorkforceBreakdown,
    EventSummary,
    YearAuditReport,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..utils import DatabaseConnectionManager
    from ..validation import DataValidator


class YearAuditor:
    """
    Generates audit reports for single simulation years.

    Provides both programmatic report generation and detailed
    console display of year audit results.
    """

    def __init__(
        self, db_manager: "DatabaseConnectionManager", validator: "DataValidator"
    ):
        self.db_manager = db_manager
        self.validator = validator

    def generate_report(self, year: int) -> YearAuditReport:
        """Generate a complete audit report for the specified year."""
        with self.db_manager.get_connection() as conn:
            wb = self._generate_workforce_breakdown(conn, year)
            es = self._generate_event_summary(conn, year)
            ga = self._calculate_growth_analysis(conn, year)
            cs = self._generate_contribution_summary(conn, year)
        dqr = self.validator.validate_year_results(year)
        return YearAuditReport(
            year=year,
            workforce_breakdown=wb,
            event_summary=es,
            growth_analysis=ga,
            contribution_summary=cs,
            data_quality_results=dqr,
            generated_at=datetime.now(timezone.utc),
        )

    def generate_detailed_year_audit(self, year: int) -> None:
        """Generate and display comprehensive year audit matching monolithic script format."""
        logger.info("YEAR %d AUDIT RESULTS", year)

        try:
            with self.db_manager.get_connection() as conn:
                # Workforce breakdown
                self._display_workforce_breakdown(conn, year)

                # Event summary
                self._display_event_summary(conn, year)

                # Growth analysis
                self._display_growth_analysis(conn, year)

                # Employee contributions
                self._display_contribution_summary(conn, year)

                # Data quality checks
                self._display_data_quality_checks(conn, year)

        except Exception as e:
            logger.error("Error during year audit: %s", e, exc_info=True)

    def _display_workforce_breakdown(self, conn, year: int) -> None:
        """Display detailed workforce breakdown by status."""
        workforce_query = f"""
        SELECT
            detailed_status_code,
            COUNT(*) as employee_count,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as percentage
        FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
        WHERE simulation_year = ?
        GROUP BY detailed_status_code
        ORDER BY employee_count DESC
        """

        results = conn.execute(workforce_query, [year]).fetchall()

        if results:
            total_employees = sum(row[1] for row in results)
            lines = ["Year-end Employment Makeup by Status:"]
            for status, count, pct in results:
                lines.append(
                    "   %s: %4s (%4.1f%%)"
                    % (status.ljust(25), f"{count:,}", pct)
                )
            lines.append(
                "   %s: %4s (100.0%%)"
                % ("TOTAL".ljust(25), f"{total_employees:,}")
            )
            logger.info("\n".join(lines))

    def _display_event_summary(self, conn, year: int) -> None:
        """Display event summary for the year."""
        # Raw events for non-headcount-changing types
        events_query = f"""
        SELECT event_type, COUNT(*) AS event_count
        FROM {TABLE_FCT_YEARLY_EVENTS}
        WHERE simulation_year = ?
          AND event_type NOT IN ('{EVENT_HIRE}', '{EVENT_TERMINATION}')
        GROUP BY event_type
        ORDER BY event_count DESC
        """
        results = conn.execute(events_query, [year]).fetchall()

        # Derive hires/terminations from the year-end snapshot
        derived_query = f"""
        SELECT
          SUM(CASE WHEN detailed_status_code IN ('new_hire_active','new_hire_termination') THEN 1 ELSE 0 END) AS hires,
          SUM(CASE WHEN employment_status = 'terminated' THEN 1 ELSE 0 END) AS terminations
        FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
        WHERE simulation_year = ?
        """
        hires, terminations = conn.execute(derived_query, [year]).fetchone()

        # Log summary
        total_events = (
            (hires or 0) + (terminations or 0) + sum(row[1] for row in results)
        )
        lines = ["Year %d Event Summary:" % year]
        lines.append("   %s: %4s" % ("hire".ljust(15), f"{(hires or 0):,}"))
        lines.append("   %s: %4s" % ("termination".ljust(15), f"{(terminations or 0):,}"))
        for event_type, count in results:
            lines.append("   %s: %4s" % (event_type.ljust(15), f"{count:,}"))
        lines.append("   %s: %4s" % ("TOTAL".ljust(15), f"{total_events:,}"))
        logger.info("\n".join(lines))

    def _display_growth_analysis(self, conn, year: int) -> None:
        """Display growth analysis - baseline comparison for year 1, YoY for others."""
        if year == 2025:  # Assuming 2025 is start year
            # Compare with baseline workforce
            baseline_query = f"""
            SELECT COUNT(*) as baseline_count
            FROM {MODEL_INT_BASELINE_WORKFORCE}
            WHERE employment_status = 'active'
            """
            baseline_result = conn.execute(baseline_query).fetchone()
            baseline_count = baseline_result[0] if baseline_result else 0

            # Get year-end active employees
            active_query = f"""
            SELECT COUNT(*) as active_count
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ? AND employment_status = 'active'
            """
            active_result = conn.execute(active_query, [year]).fetchone()
            active_count = active_result[0] if active_result else 0

            lines = ["Growth from Baseline:"]
            lines.append("   Baseline active employees  : %4s" % f"{baseline_count:,}")
            lines.append("   Year-end active employees  : %4s" % f"{active_count:,}")

            if baseline_count > 0:
                growth = active_count - baseline_count
                growth_pct = (growth / baseline_count) * 100
                lines.append(
                    "   Net growth                 : %+d (%+5.1f%%)"
                    % (growth, growth_pct)
                )
            logger.info("\n".join(lines))
        else:
            # Year-over-year comparison
            prev_year_query = f"""
            SELECT COUNT(*) as prev_active_count
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ? AND employment_status = 'active'
            """
            prev_result = conn.execute(prev_year_query, [year - 1]).fetchone()
            prev_count = prev_result[0] if prev_result else 0

            current_query = f"""
            SELECT COUNT(*) as current_active_count
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ? AND employment_status = 'active'
            """
            current_result = conn.execute(current_query, [year]).fetchone()
            current_count = current_result[0] if current_result else 0

            lines = ["Year-over-Year Growth:"]
            lines.append("   Year %d active employees: %4s" % (year - 1, f"{prev_count:,}"))
            lines.append("   Year %d active employees  : %4s" % (year, f"{current_count:,}"))

            if prev_count > 0:
                growth = current_count - prev_count
                growth_pct = (growth / prev_count) * 100
                lines.append(
                    "   Net growth                   : %+d (%+5.1f%%)"
                    % (growth, growth_pct)
                )
            logger.info("\n".join(lines))

    def _display_contribution_summary(self, conn, year: int) -> None:
        """Display employee contributions summary."""
        try:
            contributions_query = f"""
            SELECT
                COUNT(*) as enrolled_employees_active_eoy,
                ROUND(SUM(c.annual_contribution_amount), 0) as total_contributions_active_eoy,
                ROUND(AVG(c.annual_contribution_amount), 0) as avg_contribution_active_eoy,
                ROUND(AVG(c.effective_annual_deferral_rate) * 100, 1) as avg_deferral_rate_active_eoy
            FROM int_employee_contributions c
            JOIN {TABLE_FCT_WORKFORCE_SNAPSHOT} s
              ON s.employee_id = c.employee_id
             AND s.simulation_year = c.simulation_year
            WHERE c.simulation_year = ?
              AND s.employment_status = 'active'
            """
            result = conn.execute(contributions_query, [year]).fetchone()

            if result and result[0] > 0:
                enrolled, total_contrib, avg_contrib, avg_rate = result
                logger.info(
                    "Employee Contributions Summary:\n"
                    "   Enrolled employees (active EOY)  : %4s\n"
                    "   Total annual contributions   : $%s\n"
                    "   Average contribution         : $%s\n"
                    "   Average deferral rate        : %4.1f%%",
                    f"{enrolled:,}",
                    f"{total_contrib:,.0f}",
                    f"{avg_contrib:,.0f}",
                    avg_rate,
                )

            # Check for contribution data quality issues
            dq_query = """
            SELECT COUNT(*) as validation_failures
            FROM dq_employee_contributions_validation
            WHERE simulation_year = ?
            """
            dq_result = conn.execute(dq_query, [year]).fetchone()
            if dq_result and dq_result[0] > 0:
                failures = dq_result[0]
                logger.warning(
                    "Data quality issues: %d validation failures", failures
                )
            else:
                logger.info("Data quality: All validations passed")

        except Exception as contrib_error:
            logger.warning(
                "Contribution summary unavailable: %s",
                contrib_error,
                exc_info=True,
            )

    def _display_data_quality_checks(self, conn, year: int) -> None:
        """Display data quality checks and validation."""
        logger.info("Data Quality Checks:")

        # Get events for analysis
        events_query = f"""
        SELECT
            event_type,
            COUNT(*) as event_count
        FROM {TABLE_FCT_YEARLY_EVENTS}
        WHERE simulation_year = ?
        GROUP BY event_type
        ORDER BY event_count DESC
        """
        events_results = conn.execute(events_query, [year]).fetchall()

        if events_results:
            # Check for reasonable hire/termination ratios
            hire_count = sum(
                count for event_type, count in events_results if event_type == EVENT_HIRE
            )
            term_count = sum(
                count
                for event_type, count in events_results
                if event_type in [EVENT_TERMINATION, EVENT_TYPE_TERMINATION]
            )

            if hire_count > 0 and term_count > 0:
                turnover_ratio = term_count / hire_count
                logger.info(
                    "   Hire/Termination ratio       : %s hires, %s terms (ratio: %.2f)",
                    f"{hire_count:,}",
                    f"{term_count:,}",
                    turnover_ratio,
                )

                # Flag unusual ratios
                if hire_count > 2000:
                    logger.warning(
                        "HIGH HIRE COUNT: %s hires may be excessive for one year",
                        f"{hire_count:,}",
                    )
                if term_count > 1000:
                    logger.warning(
                        "HIGH TERMINATION COUNT: %s terminations may be excessive",
                        f"{term_count:,}",
                    )

            # Check for employer match events
            match_count = sum(
                count
                for event_type, count in events_results
                if event_type == "EMPLOYER_MATCH"
            )
            if match_count > 0:
                # Get match cost information
                match_query = f"""
                SELECT
                    COUNT(*) as match_count,
                    SUM(compensation_amount) as total_match_cost,
                    AVG(compensation_amount) as avg_match_amount
                FROM {TABLE_FCT_YEARLY_EVENTS}
                WHERE simulation_year = ? AND event_type = 'EMPLOYER_MATCH'
                """
                match_result = conn.execute(match_query, [year]).fetchone()
                if match_result:
                    match_cnt, total_cost, avg_match = match_result
                    logger.info(
                        "Employer Match Summary:\n"
                        "   Employees receiving match    : %s\n"
                        "   Total match cost             : $%s\n"
                        "   Average match per employee   : $%s",
                        f"{match_cnt:,}",
                        f"{total_cost:,.2f}",
                        f"{avg_match:,.2f}",
                    )

    def _generate_workforce_breakdown(self, conn, year: int) -> WorkforceBreakdown:
        """Generate workforce breakdown data structure."""
        rows = conn.execute(
            f"""
            SELECT detailed_status_code, COUNT(*) AS employee_count
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ?
            GROUP BY detailed_status_code
            ORDER BY employee_count DESC
            """,
            [year],
        ).fetchall()
        breakdown = {r[0]: r[1] for r in rows}
        total = sum(breakdown.values())
        active = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ? AND employment_status = 'active'
            """,
            [year],
        ).fetchone()[0]
        participating = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ?
              AND employment_status = 'active'
              AND participation_status = 'participating'
            """,
            [year],
        ).fetchone()[0]
        participation_rate = (participating / active) if active > 0 else 0.0
        return WorkforceBreakdown(
            year=year,
            total_employees=int(total),
            active_employees=int(active),
            breakdown_by_status=breakdown,
            participation_rate=float(participation_rate),
        )

    def _generate_event_summary(self, conn, year: int) -> EventSummary:
        """Generate event summary data structure."""
        # Raw counts excluding hire/termination
        rows = conn.execute(
            f"""
            SELECT lower(event_type) AS et, COUNT(*)
            FROM {TABLE_FCT_YEARLY_EVENTS}
            WHERE simulation_year = ?
              AND lower(event_type) NOT IN ('{EVENT_HIRE}','{EVENT_TERMINATION}')
            GROUP BY lower(event_type)
            ORDER BY 2 DESC
            """,
            [year],
        ).fetchall()
        by_type = {r[0]: r[1] for r in rows}
        # Derive hires/terminations from snapshot for consistency
        hires, terms = conn.execute(
            f"""
            SELECT
              SUM(CASE WHEN detailed_status_code IN ('new_hire_active','new_hire_termination') THEN 1 ELSE 0 END) AS hires,
              SUM(CASE WHEN employment_status = 'terminated' THEN 1 ELSE 0 END) AS terminations
            FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ?
            """,
            [year],
        ).fetchone()
        by_type[EVENT_HIRE] = int(hires or 0)
        by_type[EVENT_TERMINATION] = int(terms or 0)
        total = sum(by_type.values())
        ratio = (
            float("inf")
            if (terms or 0) == 0
            else (by_type[EVENT_HIRE] / by_type[EVENT_TERMINATION])
        )
        return EventSummary(
            year=year,
            total_events=total,
            events_by_type=by_type,
            hire_termination_ratio=ratio,
        )

    def _calculate_growth_analysis(self, conn, year: int) -> Dict[str, Any]:
        """Calculate year-over-year growth analysis."""
        prev = year - 1
        prev_active = conn.execute(
            f"""
            SELECT COUNT(*) FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ? AND employment_status = 'active'
            """,
            [prev],
        ).fetchone()
        curr_active = conn.execute(
            f"""
            SELECT COUNT(*) FROM {TABLE_FCT_WORKFORCE_SNAPSHOT}
            WHERE simulation_year = ? AND employment_status = 'active'
            """,
            [year],
        ).fetchone()
        prev_val = int(prev_active[0]) if prev_active else 0
        curr_val = int(curr_active[0]) if curr_active else 0
        growth = curr_val - prev_val
        pct = (growth / prev_val * 100) if prev_val > 0 else 0.0
        return {
            "previous_active": prev_val,
            "current_active": curr_val,
            "net_growth": growth,
            "growth_pct": pct,
        }

    def _generate_contribution_summary(
        self, conn, year: int
    ) -> Optional[Dict[str, Any]]:
        """Generate contribution summary data structure."""
        try:
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) as enrolled_employees_active_eoy,
                    ROUND(SUM(c.annual_contribution_amount), 0) as total_contributions_active_eoy,
                    ROUND(AVG(c.annual_contribution_amount), 0) as avg_contribution_active_eoy,
                    ROUND(AVG(c.effective_annual_deferral_rate) * 100, 1) as avg_deferral_rate_active_eoy
                FROM int_employee_contributions c
                JOIN {TABLE_FCT_WORKFORCE_SNAPSHOT} s
                  ON s.employee_id = c.employee_id
                 AND s.simulation_year = c.simulation_year
                WHERE c.simulation_year = ?
                  AND s.employment_status = 'active'
                """,
                [year],
            ).fetchone()
            if not row:
                return None
            enrolled, total_contrib, avg_contrib, avg_rate = row
            return {
                "enrolled_employees_active_eoy": int(enrolled or 0),
                "total_contributions_active_eoy": float(total_contrib or 0),
                "avg_contribution_active_eoy": float(avg_contrib or 0),
                "avg_deferral_rate_active_eoy": float(avg_rate or 0),
            }
        except Exception:
            return None
