#!/usr/bin/env python3
"""
Audit & Reporting utilities for Navigator Orchestrator.

Generates single-year and multi-year reports, supports basic export formats,
and integrates data quality validation results.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import DatabaseConnectionManager
from .validation import DataValidator, ValidationResult


@dataclass
class WorkforceBreakdown:
    year: int
    total_employees: int
    active_employees: int
    breakdown_by_status: Dict[str, int]
    participation_rate: float


@dataclass
class EventSummary:
    year: int
    total_events: int
    events_by_type: Dict[str, int]
    hire_termination_ratio: float


@dataclass
class YearAuditReport:
    year: int
    workforce_breakdown: WorkforceBreakdown
    event_summary: EventSummary
    growth_analysis: Dict[str, Any]
    contribution_summary: Optional[Dict[str, Any]]
    data_quality_results: List[ValidationResult]
    generated_at: datetime

    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "year": self.year,
            "workforce_breakdown": asdict(self.workforce_breakdown),
            "event_summary": asdict(self.event_summary),
            "growth_analysis": self.growth_analysis,
            "contribution_summary": self.contribution_summary,
            "data_quality_results": [asdict(r) for r in self.data_quality_results],
            "generated_at": self.generated_at.isoformat(),
        }

    def export_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as fh:
            json.dump(self.to_json_dict(), fh, indent=2)


class YearAuditor:
    def __init__(self, db_manager: DatabaseConnectionManager, validator: DataValidator):
        self.db_manager = db_manager
        self.validator = validator

    def generate_report(self, year: int) -> YearAuditReport:
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
        """Display event summary for the year with hire/term derived from snapshot to avoid duplicate events inflation."""
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

        # Derive hires/terminations from the year-end snapshot to ensure consistency with headcount
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
        # Start with derived metrics for hires/terminations
        print(f"   {'hire':15}: {(hires or 0):4,}")
        print(f"   {'termination':15}: {(terminations or 0):4,}")
        for event_type, count in results:
            print(f"   {event_type:15}: {count:4,}")
        print(f"   {'TOTAL':15}: {total_events:4,}")

    def _display_growth_analysis(self, conn, year: int) -> None:
        """Display growth analysis - baseline comparison for year 1, YoY for others."""
        if year == 2025:  # Assuming 2025 is start year - could be made configurable
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
            # Restrict to employees active at year end for enrolled counts and aggregates
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
                # Clarified: contributions reflect employees active at EOY
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
        # Derive hires/terminations from snapshot for consistency with headcount
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
        try:
            # Align contribution summary with display: restrict to employees active at EOY
            # Consistency note: All participation/contribution metrics are based on
            # employees active at year end to avoid inflating counts with terminated employees.
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
                # Explicit keys to reflect Active EOY basis
                "enrolled_employees_active_eoy": int(enrolled or 0),
                "total_contributions_active_eoy": float(total_contrib or 0),
                "avg_contribution_active_eoy": float(avg_contrib or 0),
                "avg_deferral_rate_active_eoy": float(avg_rate or 0),
            }
        except Exception:
            return None


@dataclass
class MultiYearSummary:
    start_year: int
    end_year: int
    workforce_progression: List[WorkforceBreakdown]
    growth_analysis: Dict[str, Any]
    event_trends: Dict[str, List[int]]
    participation_trends: List[float]
    generated_at: datetime

    def export_csv(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["Year", "Total Employees", "Active Employees", "Participation Rate"]
            )
            for wb in self.workforce_progression:
                writer.writerow(
                    [
                        wb.year,
                        wb.total_employees,
                        wb.active_employees,
                        f"{wb.participation_rate:.1%}",
                    ]
                )


class MultiYearReporter:
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db_manager = db_manager

    def generate_summary(self, years: List[int]) -> MultiYearSummary:
        if len(years) < 2:
            raise ValueError("Multi-year analysis requires at least 2 years")
        with self.db_manager.get_connection() as conn:
            progression = [self._workforce_breakdown(conn, y) for y in years]
            growth = self._calculate_overall_growth(conn, years)
            event_trends = self._event_trends(conn, years)
            participation = [wb.participation_rate for wb in progression]
        return MultiYearSummary(
            start_year=min(years),
            end_year=max(years),
            workforce_progression=progression,
            growth_analysis=growth,
            event_trends=event_trends,
            participation_trends=participation,
            generated_at=datetime.utcnow(),
        )

    def display_comprehensive_multi_year_summary(
        self, completed_years: List[int]
    ) -> None:
        """Display comprehensive multi-year simulation summary matching monolithic script."""
        if len(completed_years) < 2:
            return  # Skip summary if less than 2 years completed

        print("\n" + "=" * 60)
        print("📊 MULTI-YEAR SIMULATION SUMMARY")
        print("=" * 60)

        try:
            with self.db_manager.get_connection() as conn:
                # Workforce progression
                self._display_workforce_progression(conn, completed_years)

                # Participation analysis
                self._display_participation_analysis(conn, completed_years)

                # Participation breakdown by method
                self._display_participation_breakdown(conn, completed_years)

                # Overall growth analysis
                self._display_overall_growth_analysis(conn, completed_years)

                # Multi-year event summary
                self._display_multi_year_events(conn, completed_years)

        except Exception as e:
            print(f"❌ Error generating multi-year summary: {e}")

    def _display_workforce_progression(self, conn, completed_years: List[int]) -> None:
        """Display workforce progression across years."""
        progression_query = """
        SELECT
            simulation_year,
            COUNT(*) as total_employees,
            COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
            COUNT(CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 END) as new_hires_active,
            COUNT(CASE WHEN detailed_status_code = 'experienced_termination' THEN 1 END) as experienced_terms,
            COUNT(CASE WHEN detailed_status_code = 'new_hire_termination' THEN 1 END) as new_hire_terms
        FROM fct_workforce_snapshot
        WHERE simulation_year IN ({})
        GROUP BY simulation_year
        ORDER BY simulation_year
        """.format(
            ",".join("?" * len(completed_years))
        )

        results = conn.execute(progression_query, completed_years).fetchall()

        if results:
            print("📈 Workforce Progression:")
            print("   Year  | Total Emp | Active | New Hires | Exp Terms | NH Terms")
            print("   ------|-----------|--------|-----------|-----------|----------")

            for row in results:
                year, total, active, nh_active, exp_terms, nh_terms = row
                print(
                    f"   {year} | {total:9,} | {active:6,} | {nh_active:9,} | {exp_terms:9,} | {nh_terms:8,}"
                )

    def _display_participation_analysis(self, conn, completed_years: List[int]) -> None:
        """Display active employee deferral participation analysis."""
        # Note: All figures are based on employees active at year end (EOY)
        print("\n💰 Deferral Participation (Active EOY):")
        print("   Year  | Active EEs | Participating (Active EOY) | Participation %")
        print("   ------|------------|---------------|----------------")

        participation_query = """
        SELECT
            simulation_year,
            COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
            COUNT(CASE WHEN employment_status = 'active' AND participation_status = 'participating' THEN 1 END) as participating_employees
        FROM fct_workforce_snapshot
        WHERE simulation_year IN ({})
        GROUP BY simulation_year
        ORDER BY simulation_year
        """.format(
            ",".join("?" * len(completed_years))
        )

        results = conn.execute(participation_query, completed_years).fetchall()

        if results:
            for year, active_count, participating in results:
                participation_pct = (
                    (participating / active_count * 100) if active_count > 0 else 0
                )
                print(
                    f"   {year} | {active_count:10,} | {participating:13,} | {participation_pct:14.1f}%"
                )

    def _display_participation_breakdown(
        self, conn, completed_years: List[int]
    ) -> None:
        """Display participation breakdown by enrollment method."""
        # Note: Breakdown metrics are also Active EOY
        print("\n📋 Participation Breakdown by Method (Active EOY):")
        print(
            "   Year  | Auto Enroll | Voluntary  | Census     | Opted Out  | Not Auto   | Unenrolled"
        )
        print(
            "   ------|-------------|------------|------------|------------|------------|------------"
        )

        detail_query = """
        SELECT
            simulation_year,
            COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'participating - auto enrollment' THEN 1 END) as auto_enrolled,
            COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'participating - voluntary enrollment' THEN 1 END) as voluntary,
            COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'participating - census enrollment' THEN 1 END) as census,
            COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'not_participating - opted out of AE' THEN 1 END) as opted_out,
            COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'not_participating - not auto enrolled' THEN 1 END) as not_auto,
            COUNT(CASE WHEN employment_status = 'active' AND participation_status_detail = 'not_participating - proactively unenrolled' THEN 1 END) as unenrolled
        FROM fct_workforce_snapshot
        WHERE simulation_year IN ({})
        GROUP BY simulation_year
        ORDER BY simulation_year
        """.format(
            ",".join("?" * len(completed_years))
        )

        results = conn.execute(detail_query, completed_years).fetchall()

        if results:
            for (
                year,
                auto,
                voluntary,
                census,
                opted_out,
                not_auto,
                unenrolled,
            ) in results:
                print(
                    f"   {year} | {auto:11,} | {voluntary:10,} | {census:10,} | {opted_out:10,} | {not_auto:10,} | {unenrolled:10,}"
                )

    def _display_overall_growth_analysis(
        self, conn, completed_years: List[int]
    ) -> None:
        """Display overall growth analysis with CAGR."""
        progression_query = """
        SELECT
            simulation_year,
            COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees
        FROM fct_workforce_snapshot
        WHERE simulation_year IN ({})
        GROUP BY simulation_year
        ORDER BY simulation_year
        """.format(
            ",".join("?" * len(completed_years))
        )

        results = conn.execute(progression_query, completed_years).fetchall()

        if len(results) >= 2:
            baseline_active = results[0][1]  # Active employees in first year
            final_active = results[-1][1]  # Active employees in last year

            if baseline_active and final_active:
                total_growth = final_active - baseline_active
                growth_pct = (total_growth / baseline_active) * 100
                years_elapsed = len(completed_years)
                cagr = (
                    (final_active / baseline_active) ** (1 / (years_elapsed - 1)) - 1
                ) * 100

                print(f"\n📊 Overall Growth Analysis:")
                print(f"   Starting active workforce    : {baseline_active:6,}")
                print(f"   Ending active workforce      : {final_active:6,}")
                print(
                    f"   Total net growth             : {total_growth:+6,} ({growth_pct:+5.1f}%)"
                )
                print(f"   Compound Annual Growth Rate  : {cagr:5.1f}%")

    def _display_multi_year_events(self, conn, completed_years: List[int]) -> None:
        """Display multi-year event summary."""
        events_summary_query = """
        SELECT
            event_type,
            simulation_year,
            COUNT(*) as event_count
        FROM fct_yearly_events
        WHERE simulation_year IN ({})
        GROUP BY event_type, simulation_year
        ORDER BY event_type, simulation_year
        """.format(
            ",".join("?" * len(completed_years))
        )

        results = conn.execute(events_summary_query, completed_years).fetchall()

        if results:
            print(f"\n📋 Multi-Year Event Summary:")
            # Group by event type
            events_by_type = {}
            for event_type, year, count in results:
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append((year, count))

            for event_type, year_counts in events_by_type.items():
                total_events = sum(count for _, count in year_counts)
                years_list = ", ".join(
                    f"{year}: {count:,}" for year, count in year_counts
                )
                print(f"   {event_type:15}: {total_events:5,} total ({years_list})")

    def _workforce_breakdown(self, conn, year: int) -> WorkforceBreakdown:
        # Reuse YearAuditor breakdown logic minimally
        rows = conn.execute(
            """
            SELECT detailed_status_code, COUNT(*)
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
            GROUP BY detailed_status_code
            """,
            [year],
        ).fetchall()
        breakdown = {r[0]: r[1] for r in rows}
        total = sum(breakdown.values())
        active = conn.execute(
            "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ? AND employment_status = 'active'",
            [year],
        ).fetchone()[0]
        participating = conn.execute(
            """
            SELECT COUNT(*) FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active' AND participation_status = 'participating'
            """,
            [year],
        ).fetchone()[0]
        rate = (participating / active) if active > 0 else 0.0
        return WorkforceBreakdown(year, int(total), int(active), breakdown, float(rate))

    def _calculate_overall_growth(self, conn, years: List[int]) -> Dict[str, Any]:
        first, last = min(years), max(years)
        q = """
        SELECT simulation_year, COUNT(*) as active_count
        FROM fct_workforce_snapshot
        WHERE simulation_year IN (?, ?) AND employment_status = 'active'
        GROUP BY simulation_year
        ORDER BY simulation_year
        """
        results = dict(conn.execute(q, [first, last]).fetchall())
        start = results.get(first, 0)
        end = results.get(last, 0)
        years_elapsed = max(1, last - first)
        cagr = ((end / start) ** (1 / years_elapsed) - 1) * 100 if start > 0 else 0.0
        total_growth = ((end - start) / start) * 100 if start > 0 else 0.0
        return {
            "start_active": start,
            "end_active": end,
            "cagr_pct": cagr,
            "total_growth_pct": total_growth,
        }

    def _event_trends(self, conn, years: List[int]) -> Dict[str, List[int]]:
        q = """
        SELECT simulation_year, lower(event_type) AS et, COUNT(*)
        FROM fct_yearly_events
        WHERE simulation_year IN ({})
        GROUP BY simulation_year, lower(event_type)
        """.format(
            ",".join(["?"] * len(years))
        )
        rows = conn.execute(q, years).fetchall()
        # Collect per-type sequence aligned to years
        types = sorted({r[1] for r in rows})
        idx = {y: i for i, y in enumerate(sorted(years))}
        trends = {t: [0] * len(years) for t in types}
        for y, t, c in rows:
            trends[t][idx[y]] = c
        return trends


class ConsoleReporter:
    @staticmethod
    def format_year_audit(report: YearAuditReport) -> str:
        lines: List[str] = []
        lines.append(f"\n📊 YEAR {report.year} AUDIT RESULTS")
        lines.append("=" * 50)

        lines.append("\n📋 Year-end Employment Makeup by Status:")
        wb = report.workforce_breakdown
        for status, count in wb.breakdown_by_status.items():
            pct = (count / wb.total_employees * 100) if wb.total_employees > 0 else 0
            lines.append(f"   {status:25}: {count:4,} ({pct:4.1f}%)")
        lines.append(f"   {'TOTAL':25}: {wb.total_employees:4,} (100.0%)")

        lines.append(f"\n📈 Year {report.year} Event Summary:")
        es = report.event_summary
        for event_type, count in es.events_by_type.items():
            lines.append(f"   {event_type:15}: {count:4,}")
        lines.append(f"   {'TOTAL':15}: {es.total_events:4,}")

        lines.append("\n🔍 Data Quality Results:")
        for r in report.data_quality_results:
            status = "✅" if r.passed else "❌"
            lines.append(f"   {status} {r.rule_name}: {r.message}")

        return "\n".join(lines)


class ReportTemplate:
    def __init__(self, template_config: Dict[str, Any]):
        self.config = template_config

    def apply_template(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        sections = self.config.get("sections", [])
        filtered: Dict[str, Any] = {}
        for section in sections:
            name = section["name"]
            if section.get("enabled", True) and name in report_data:
                filtered[name] = report_data[name]
        return filtered


EXECUTIVE_SUMMARY_TEMPLATE = {
    "name": "Executive Summary",
    "sections": [
        {"name": "workforce_breakdown", "enabled": True},
        {"name": "growth_analysis", "enabled": True},
        {"name": "event_summary", "enabled": False},
        {"name": "data_quality_results", "enabled": False},
    ],
}


DETAILED_AUDIT_TEMPLATE = {
    "name": "Detailed Audit",
    "sections": [
        {"name": "workforce_breakdown", "enabled": True},
        {"name": "event_summary", "enabled": True},
        {"name": "growth_analysis", "enabled": True},
        {"name": "contribution_summary", "enabled": True},
        {"name": "data_quality_results", "enabled": True},
    ],
}
