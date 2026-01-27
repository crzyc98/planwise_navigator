"""
Year auditor for single-year simulation reports.

Generates detailed audit reports for individual simulation years
with workforce breakdown, event summary, and data quality validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING

from .data_models import (
    WorkforceBreakdown,
    EventSummary,
    YearAuditReport,
)

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
            generated_at=datetime.utcnow(),
        )

    def generate_detailed_year_audit(self, year: int) -> None:
        """Generate and display comprehensive year audit matching monolithic script format."""
        print(f"\n📊 YEAR {year} AUDIT RESULTS")
        print("=" * 50)

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

                print()  # Extra spacing

        except Exception as e:
            print(f"❌ Error during year audit: {e}")

    def _display_workforce_breakdown(self, conn, year: int) -> None:
        """Display detailed workforce breakdown by status."""
        workforce_query = """
        SELECT
            detailed_status_code,
            COUNT(*) as employee_count,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as percentage
        FROM fct_workforce_snapshot
        WHERE simulation_year = ?
        GROUP BY detailed_status_code
        ORDER BY employee_count DESC
        """

        results = conn.execute(workforce_query, [year]).fetchall()

        if results:
            print("📋 Year-end Employment Makeup by Status:")
            total_employees = sum(row[1] for row in results)
            for status, count, pct in results:
                print(f"   {status:25}: {count:4,} ({pct:4.1f}%)")
            print(f"   {'TOTAL':25}: {total_employees:4,} (100.0%)")

    def _display_event_summary(self, conn, year: int) -> None:
        """Display event summary for the year."""
        # Raw events for non-headcount-changing types
        events_query = """
        SELECT event_type, COUNT(*) AS event_count
        FROM fct_yearly_events
        WHERE simulation_year = ?
          AND event_type NOT IN ('hire', 'termination')
        GROUP BY event_type
        ORDER BY event_count DESC
        """
        results = conn.execute(events_query, [year]).fetchall()

        # Derive hires/terminations from the year-end snapshot
        derived_query = """
        SELECT
          SUM(CASE WHEN detailed_status_code IN ('new_hire_active','new_hire_termination') THEN 1 ELSE 0 END) AS hires,
          SUM(CASE WHEN employment_status = 'terminated' THEN 1 ELSE 0 END) AS terminations
        FROM fct_workforce_snapshot
        WHERE simulation_year = ?
        """
        hires, terminations = conn.execute(derived_query, [year]).fetchone()

        # Print summary
        print(f"\n📈 Year {year} Event Summary:")
        total_events = (
            (hires or 0) + (terminations or 0) + sum(row[1] for row in results)
        )
        print(f"   {'hire':15}: {(hires or 0):4,}")
        print(f"   {'termination':15}: {(terminations or 0):4,}")
        for event_type, count in results:
            print(f"   {event_type:15}: {count:4,}")
        print(f"   {'TOTAL':15}: {total_events:4,}")

    def _display_growth_analysis(self, conn, year: int) -> None:
        """Display growth analysis - baseline comparison for year 1, YoY for others."""
        if year == 2025:  # Assuming 2025 is start year
            # Compare with baseline workforce
            baseline_query = """
            SELECT COUNT(*) as baseline_count
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
            """
            baseline_result = conn.execute(baseline_query).fetchone()
            baseline_count = baseline_result[0] if baseline_result else 0

            # Get year-end active employees
            active_query = """
            SELECT COUNT(*) as active_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
            """
            active_result = conn.execute(active_query, [year]).fetchone()
            active_count = active_result[0] if active_result else 0

            print(f"\n📊 Growth from Baseline:")
            print(f"   Baseline active employees  : {baseline_count:4,}")
            print(f"   Year-end active employees  : {active_count:4,}")

            if baseline_count > 0:
                growth = active_count - baseline_count
                growth_pct = (growth / baseline_count) * 100
                print(
                    f"   Net growth                 : {growth:+4,} ({growth_pct:+5.1f}%)"
                )
        else:
            # Year-over-year comparison
            prev_year_query = """
            SELECT COUNT(*) as prev_active_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
            """
            prev_result = conn.execute(prev_year_query, [year - 1]).fetchone()
            prev_count = prev_result[0] if prev_result else 0

            current_query = """
            SELECT COUNT(*) as current_active_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
            """
            current_result = conn.execute(current_query, [year]).fetchone()
            current_count = current_result[0] if current_result else 0

            print(f"\n📊 Year-over-Year Growth:")
            print(f"   Year {year-1} active employees: {prev_count:4,}")
            print(f"   Year {year} active employees  : {current_count:4,}")

            if prev_count > 0:
                growth = current_count - prev_count
                growth_pct = (growth / prev_count) * 100
                print(
                    f"   Net growth                   : {growth:+4,} ({growth_pct:+5.1f}%)"
                )

    def _display_contribution_summary(self, conn, year: int) -> None:
        """Display employee contributions summary."""
        try:
            contributions_query = """
            SELECT
                COUNT(*) as enrolled_employees_active_eoy,
                ROUND(SUM(c.annual_contribution_amount), 0) as total_contributions_active_eoy,
                ROUND(AVG(c.annual_contribution_amount), 0) as avg_contribution_active_eoy,
                ROUND(AVG(c.effective_annual_deferral_rate) * 100, 1) as avg_deferral_rate_active_eoy
            FROM int_employee_contributions c
            JOIN fct_workforce_snapshot s
              ON s.employee_id = c.employee_id
             AND s.simulation_year = c.simulation_year
            WHERE c.simulation_year = ?
              AND s.employment_status = 'active'
            """
            result = conn.execute(contributions_query, [year]).fetchone()

            if result and result[0] > 0:
                enrolled, total_contrib, avg_contrib, avg_rate = result
                print(f"\n💰 Employee Contributions Summary:")
                print(f"   Enrolled employees (active EOY)  : {enrolled:4,}")
                print(f"   Total annual contributions   : ${total_contrib:10,.0f}")
                print(f"   Average contribution         : ${avg_contrib:6,.0f}")
                print(f"   Average deferral rate        : {avg_rate:4.1f}%")

            # Check for contribution data quality issues
            dq_query = """
            SELECT COUNT(*) as validation_failures
            FROM dq_employee_contributions_validation
            WHERE simulation_year = ?
            """
            dq_result = conn.execute(dq_query, [year]).fetchone()
            if dq_result and dq_result[0] > 0:
                failures = dq_result[0]
                print(
                    f"   ⚠️  Data quality issues      : {failures:4,} validation failures"
                )
            else:
                print(f"   ✅ Data quality              : All validations passed")

        except Exception as contrib_error:
            print(f"   ⚠️  Contribution summary unavailable: {contrib_error}")

    def _display_data_quality_checks(self, conn, year: int) -> None:
        """Display data quality checks and validation."""
        print(f"\n🔍 Data Quality Checks:")

        # Get events for analysis
        events_query = """
        SELECT
            event_type,
            COUNT(*) as event_count
        FROM fct_yearly_events
        WHERE simulation_year = ?
        GROUP BY event_type
        ORDER BY event_count DESC
        """
        events_results = conn.execute(events_query, [year]).fetchall()

        if events_results:
            # Check for reasonable hire/termination ratios
            hire_count = sum(
                count for event_type, count in events_results if event_type == "hire"
            )
            term_count = sum(
                count
                for event_type, count in events_results
                if event_type in ["termination", "TERMINATION"]
            )

            if hire_count > 0 and term_count > 0:
                turnover_ratio = term_count / hire_count
                print(
                    f"   Hire/Termination ratio       : {hire_count:,} hires, {term_count:,} terms (ratio: {turnover_ratio:.2f})"
                )

                # Flag unusual ratios
                if hire_count > 2000:
                    print(
                        f"   ⚠️  HIGH HIRE COUNT: {hire_count:,} hires may be excessive for one year"
                    )
                if term_count > 1000:
                    print(
                        f"   ⚠️  HIGH TERMINATION COUNT: {term_count:,} terminations may be excessive"
                    )

            # Check for employer match events
            match_count = sum(
                count
                for event_type, count in events_results
                if event_type == "EMPLOYER_MATCH"
            )
            if match_count > 0:
                # Get match cost information
                match_query = """
                SELECT
                    COUNT(*) as match_count,
                    SUM(compensation_amount) as total_match_cost,
                    AVG(compensation_amount) as avg_match_amount
                FROM fct_yearly_events
                WHERE simulation_year = ? AND event_type = 'EMPLOYER_MATCH'
                """
                match_result = conn.execute(match_query, [year]).fetchone()
                if match_result:
                    match_cnt, total_cost, avg_match = match_result
                    print(f"\n💰 Employer Match Summary:")
                    print(f"   Employees receiving match    : {match_cnt:,}")
                    print(f"   Total match cost             : ${total_cost:,.2f}")
                    print(f"   Average match per employee   : ${avg_match:,.2f}")

    def _generate_workforce_breakdown(self, conn, year: int) -> WorkforceBreakdown:
        """Generate workforce breakdown data structure."""
        rows = conn.execute(
            """
            SELECT detailed_status_code, COUNT(*) AS employee_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
            GROUP BY detailed_status_code
            ORDER BY employee_count DESC
            """,
            [year],
        ).fetchall()
        breakdown = {r[0]: r[1] for r in rows}
        total = sum(breakdown.values())
        active = conn.execute(
            """
            SELECT COUNT(*)
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
            """,
            [year],
        ).fetchone()[0]
        participating = conn.execute(
            """
            SELECT COUNT(*)
            FROM fct_workforce_snapshot
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
            """
            SELECT lower(event_type) AS et, COUNT(*)
            FROM fct_yearly_events
            WHERE simulation_year = ?
              AND lower(event_type) NOT IN ('hire','termination')
            GROUP BY lower(event_type)
            ORDER BY 2 DESC
            """,
            [year],
        ).fetchall()
        by_type = {r[0]: r[1] for r in rows}
        # Derive hires/terminations from snapshot for consistency
        hires, terms = conn.execute(
            """
            SELECT
              SUM(CASE WHEN detailed_status_code IN ('new_hire_active','new_hire_termination') THEN 1 ELSE 0 END) AS hires,
              SUM(CASE WHEN employment_status = 'terminated' THEN 1 ELSE 0 END) AS terminations
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
            """,
            [year],
        ).fetchone()
        by_type["hire"] = int(hires or 0)
        by_type["termination"] = int(terms or 0)
        total = sum(by_type.values())
        ratio = (
            float("inf")
            if (terms or 0) == 0
            else (by_type["hire"] / by_type["termination"])
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
            """
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
            """,
            [prev],
        ).fetchone()
        curr_active = conn.execute(
            """
            SELECT COUNT(*) FROM fct_workforce_snapshot
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
                """
                SELECT
                    COUNT(*) as enrolled_employees_active_eoy,
                    ROUND(SUM(c.annual_contribution_amount), 0) as total_contributions_active_eoy,
                    ROUND(AVG(c.annual_contribution_amount), 0) as avg_contribution_active_eoy,
                    ROUND(AVG(c.effective_annual_deferral_rate) * 100, 1) as avg_deferral_rate_active_eoy
                FROM int_employee_contributions c
                JOIN fct_workforce_snapshot s
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
