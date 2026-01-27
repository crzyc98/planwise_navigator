"""
Multi-year reporter for simulation summaries.

Generates comprehensive reports spanning multiple simulation years
with workforce progression, participation trends, and growth analysis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, TYPE_CHECKING

from .data_models import WorkforceBreakdown, MultiYearSummary

if TYPE_CHECKING:
    from ..utils import DatabaseConnectionManager


class MultiYearReporter:
    """
    Generates reports spanning multiple simulation years.

    Provides both programmatic report generation and detailed
    console display of multi-year summary results.
    """

    def __init__(self, db_manager: "DatabaseConnectionManager"):
        self.db_manager = db_manager

    def generate_summary(self, years: List[int]) -> MultiYearSummary:
        """Generate a complete multi-year summary report."""
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

    def _display_workforce_progression(
        self, conn, completed_years: List[int]
    ) -> None:
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

    def _display_participation_analysis(
        self, conn, completed_years: List[int]
    ) -> None:
        """Display active employee deferral participation analysis."""
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
        """Generate workforce breakdown for a single year."""
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
        """Calculate overall growth statistics across years."""
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
        """Calculate event trends across years."""
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
