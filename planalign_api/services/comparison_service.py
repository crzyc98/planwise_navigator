"""Comparison service for scenario analysis."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.comparison import (
    ComparisonResponse,
    DCPlanComparisonYear,
    DCPlanMetrics,
    DeltaValue,
    EventComparisonMetric,
    WorkforceComparisonYear,
    WorkforceMetrics,
)
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import DatabasePathResolver

logger = logging.getLogger(__name__)


class ComparisonService:
    """Service for comparing scenarios."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(storage)

    def compare_scenarios(
        self,
        workspace_id: str,
        scenario_ids: List[str],
        baseline_id: str,
    ) -> Optional[ComparisonResponse]:
        """
        Compare multiple scenarios against a baseline.

        Returns pre-calculated deltas for workforce metrics and events.
        """
        if len(scenario_ids) < 2:
            logger.error("Need at least 2 scenarios to compare")
            return None

        if baseline_id not in scenario_ids:
            logger.error(f"Baseline {baseline_id} not in scenario list")
            return None

        # Load data from each scenario
        scenario_data: Dict[str, Dict[str, Any]] = {}

        for scenario_id in scenario_ids:
            data = self._load_scenario_data(workspace_id, scenario_id)
            if data:
                scenario_data[scenario_id] = data
            else:
                logger.warning(f"Could not load data for scenario {scenario_id}")

        if baseline_id not in scenario_data:
            logger.error(f"Could not load baseline scenario {baseline_id}")
            return None

        baseline_data = scenario_data[baseline_id]

        # Build workforce comparison by year
        workforce_comparison = self._build_workforce_comparison(
            scenario_data, baseline_data, baseline_id
        )

        # Build event comparison
        event_comparison = self._build_event_comparison(
            scenario_data, baseline_data, baseline_id
        )

        # Build DC plan comparison
        dc_plan_comparison = self._build_dc_plan_comparison(
            scenario_data, baseline_data, baseline_id
        )

        # Build summary deltas
        summary_deltas = self._build_summary_deltas(
            scenario_data, baseline_data, baseline_id
        )

        return ComparisonResponse(
            scenarios=scenario_ids,
            scenario_names={},  # Will be filled by router
            baseline_scenario=baseline_id,
            workforce_comparison=workforce_comparison,
            event_comparison=event_comparison,
            dc_plan_comparison=dc_plan_comparison,
            summary_deltas=summary_deltas,
        )

    def _load_scenario_data(
        self, workspace_id: str, scenario_id: str
    ) -> Optional[Dict[str, Any]]:
        """Load simulation data for a scenario from its DuckDB database."""
        try:
            import duckdb

            resolved = self.db_resolver.resolve(workspace_id, scenario_id)
            if not resolved.exists:
                return None

            conn = duckdb.connect(str(resolved.path), read_only=True)

            # Load workforce snapshots
            try:
                workforce_df = conn.execute("""
                    SELECT
                        simulation_year,
                        COUNT(DISTINCT employee_id) as headcount,
                        COUNT(DISTINCT CASE WHEN UPPER(employment_status) = 'ACTIVE' THEN employee_id END) as active,
                        COUNT(DISTINCT CASE WHEN UPPER(employment_status) = 'TERMINATED' THEN employee_id END) as terminated
                    FROM fct_workforce_snapshot
                    GROUP BY simulation_year
                    ORDER BY simulation_year
                """).fetchdf()
                workforce = workforce_df.to_dict("records")
            except Exception:
                workforce = []

            # Load event counts
            try:
                events_df = conn.execute("""
                    SELECT
                        simulation_year,
                        event_type,
                        COUNT(*) as count
                    FROM fct_yearly_events
                    GROUP BY simulation_year, event_type
                    ORDER BY simulation_year, event_type
                """).fetchdf()
                events = events_df.to_dict("records")
            except Exception:
                events = []

            # Load hires by year
            try:
                hires_df = conn.execute("""
                    SELECT
                        simulation_year,
                        COUNT(*) as hires
                    FROM fct_yearly_events
                    WHERE event_type = 'HIRE'
                    GROUP BY simulation_year
                    ORDER BY simulation_year
                """).fetchdf()
                hires_by_year = {
                    row["simulation_year"]: row["hires"]
                    for row in hires_df.to_dict("records")
                }
            except Exception:
                hires_by_year = {}

            # Load DC plan metrics by year
            try:
                dc_plan_df = conn.execute("""
                    SELECT
                        simulation_year,
                        COALESCE(
                            COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE'
                                       AND is_enrolled_flag THEN 1 END) * 100.0
                            / NULLIF(COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE'
                                               THEN 1 END), 0),
                            0
                        ) AS participation_rate,
                        AVG(CASE WHEN is_enrolled_flag
                            THEN current_deferral_rate ELSE NULL END
                        ) AS avg_deferral_rate,
                        COALESCE(SUM(prorated_annual_contributions), 0)
                            AS total_employee_contributions,
                        COALESCE(SUM(employer_match_amount), 0)
                            AS total_employer_match,
                        COALESCE(SUM(employer_core_amount), 0)
                            AS total_employer_core,
                        COALESCE(
                            SUM(employer_match_amount) + SUM(employer_core_amount), 0
                        ) AS total_employer_cost,
                        COALESCE(SUM(prorated_annual_compensation), 0)
                            AS total_compensation,
                        COUNT(CASE WHEN is_enrolled_flag THEN 1 END)
                            AS participant_count
                    FROM fct_workforce_snapshot
                    GROUP BY simulation_year
                    ORDER BY simulation_year
                """).fetchdf()
                dc_plan = dc_plan_df.to_dict("records")
                # Compute employer_cost_rate and handle NULL avg_deferral_rate
                for row in dc_plan:
                    total_comp = row.get("total_compensation", 0) or 0
                    total_cost = row.get("total_employer_cost", 0) or 0
                    row["employer_cost_rate"] = (
                        (total_cost / total_comp * 100) if total_comp > 0 else 0.0
                    )
                    avg_def = row.get("avg_deferral_rate")
                    if avg_def is None or (isinstance(avg_def, float) and avg_def != avg_def):
                        row["avg_deferral_rate"] = 0.0
            except Exception:
                dc_plan = []

            conn.close()

            return {
                "workforce": workforce,
                "events": events,
                "hires_by_year": hires_by_year,
                "dc_plan": dc_plan,
            }

        except Exception as e:
            logger.error(f"Failed to load scenario data: {e}")
            return None

    def _build_workforce_comparison(
        self,
        scenario_data: Dict[str, Dict[str, Any]],
        baseline_data: Dict[str, Any],
        baseline_id: str,
    ) -> List[WorkforceComparisonYear]:
        """Build year-by-year workforce comparison."""
        # Get all years across all scenarios
        all_years = set()
        for data in scenario_data.values():
            for row in data.get("workforce", []):
                all_years.add(row["simulation_year"])

        comparison = []
        prev_headcounts: Dict[str, int] = {}

        for year in sorted(all_years):
            values = {}
            deltas = {}

            # Get baseline values for this year
            baseline_workforce = next(
                (w for w in baseline_data.get("workforce", []) if w["simulation_year"] == year),
                None,
            )
            baseline_hires = baseline_data.get("hires_by_year", {}).get(year, 0)

            if not baseline_workforce:
                continue

            baseline_headcount = baseline_workforce.get("headcount", 0)
            baseline_active = baseline_workforce.get("active", 0)
            baseline_terminated = baseline_workforce.get("terminated", 0)
            baseline_prev = prev_headcounts.get(baseline_id, baseline_headcount)
            baseline_growth = (
                ((baseline_headcount - baseline_prev) / baseline_prev * 100)
                if baseline_prev > 0
                else 0
            )

            baseline_metrics = WorkforceMetrics(
                headcount=baseline_headcount,
                active=baseline_active,
                terminated=baseline_terminated,
                new_hires=baseline_hires,
                growth_pct=baseline_growth,
            )
            values[baseline_id] = baseline_metrics
            deltas[baseline_id] = WorkforceMetrics(
                headcount=0,
                active=0,
                terminated=0,
                new_hires=0,
                growth_pct=0.0,
            )

            # Calculate for each non-baseline scenario
            for scenario_id, data in scenario_data.items():
                if scenario_id == baseline_id:
                    continue

                workforce = next(
                    (w for w in data.get("workforce", []) if w["simulation_year"] == year),
                    None,
                )
                hires = data.get("hires_by_year", {}).get(year, 0)

                if not workforce:
                    continue

                headcount = workforce.get("headcount", 0)
                active = workforce.get("active", 0)
                terminated = workforce.get("terminated", 0)
                prev = prev_headcounts.get(scenario_id, headcount)
                growth = (
                    ((headcount - prev) / prev * 100)
                    if prev > 0
                    else 0
                )

                values[scenario_id] = WorkforceMetrics(
                    headcount=headcount,
                    active=active,
                    terminated=terminated,
                    new_hires=hires,
                    growth_pct=growth,
                )

                deltas[scenario_id] = WorkforceMetrics(
                    headcount=headcount - baseline_headcount,
                    active=active - baseline_active,
                    terminated=terminated - baseline_terminated,
                    new_hires=hires - baseline_hires,
                    growth_pct=growth - baseline_growth,
                )

                prev_headcounts[scenario_id] = headcount

            prev_headcounts[baseline_id] = baseline_headcount

            comparison.append(
                WorkforceComparisonYear(
                    year=year,
                    values=values,
                    deltas=deltas,
                )
            )

        return comparison

    def _build_event_comparison(
        self,
        scenario_data: Dict[str, Dict[str, Any]],
        baseline_data: Dict[str, Any],
        baseline_id: str,
    ) -> List[EventComparisonMetric]:
        """Build event comparison across scenarios."""
        event_types = ["HIRE", "TERMINATION", "PROMOTION", "RAISE"]
        comparison = []

        # Get all years
        all_years = set()
        for data in scenario_data.values():
            for event in data.get("events", []):
                all_years.add(event["simulation_year"])

        for year in sorted(all_years):
            for event_type in event_types:
                # Get baseline value
                baseline_events = baseline_data.get("events", [])
                baseline_value = next(
                    (e["count"] for e in baseline_events
                     if e["simulation_year"] == year and e["event_type"] == event_type),
                    0,
                )

                scenarios = {}
                deltas = {}
                delta_pcts = {}

                for scenario_id, data in scenario_data.items():
                    if scenario_id == baseline_id:
                        scenarios[scenario_id] = baseline_value
                        deltas[scenario_id] = 0
                        delta_pcts[scenario_id] = 0.0
                        continue

                    events = data.get("events", [])
                    value = next(
                        (e["count"] for e in events
                         if e["simulation_year"] == year and e["event_type"] == event_type),
                        0,
                    )

                    scenarios[scenario_id] = value
                    deltas[scenario_id] = value - baseline_value
                    delta_pcts[scenario_id] = (
                        ((value - baseline_value) / baseline_value * 100)
                        if baseline_value > 0
                        else 0.0
                    )

                comparison.append(
                    EventComparisonMetric(
                        metric=event_type.lower() + "s",
                        year=year,
                        baseline=baseline_value,
                        scenarios=scenarios,
                        deltas=deltas,
                        delta_pcts=delta_pcts,
                    )
                )

        return comparison

    def _build_dc_plan_comparison(
        self,
        scenario_data: Dict[str, Dict[str, Any]],
        baseline_data: Dict[str, Any],
        baseline_id: str,
    ) -> List[DCPlanComparisonYear]:
        """Build year-by-year DC plan comparison with deltas."""
        # Collect all years across all scenarios
        all_years: set = set()
        for data in scenario_data.values():
            for row in data.get("dc_plan", []):
                all_years.add(row["simulation_year"])

        comparison = []

        for year in sorted(all_years):
            values: Dict[str, DCPlanMetrics] = {}
            deltas: Dict[str, DCPlanMetrics] = {}

            # Get baseline DC plan row for this year
            baseline_row = next(
                (r for r in baseline_data.get("dc_plan", [])
                 if r["simulation_year"] == year),
                None,
            )

            if not baseline_row:
                continue

            baseline_metrics = DCPlanMetrics(
                participation_rate=baseline_row.get("participation_rate", 0.0),
                avg_deferral_rate=baseline_row.get("avg_deferral_rate", 0.0),
                total_employee_contributions=baseline_row.get("total_employee_contributions", 0.0),
                total_employer_match=baseline_row.get("total_employer_match", 0.0),
                total_employer_core=baseline_row.get("total_employer_core", 0.0),
                total_employer_cost=baseline_row.get("total_employer_cost", 0.0),
                employer_cost_rate=baseline_row.get("employer_cost_rate", 0.0),
                participant_count=int(baseline_row.get("participant_count", 0)),
            )
            values[baseline_id] = baseline_metrics
            deltas[baseline_id] = DCPlanMetrics()  # All zeros

            # Calculate for each non-baseline scenario
            for scenario_id, data in scenario_data.items():
                if scenario_id == baseline_id:
                    continue

                scenario_row = next(
                    (r for r in data.get("dc_plan", [])
                     if r["simulation_year"] == year),
                    None,
                )

                if not scenario_row:
                    continue

                scenario_metrics = DCPlanMetrics(
                    participation_rate=scenario_row.get("participation_rate", 0.0),
                    avg_deferral_rate=scenario_row.get("avg_deferral_rate", 0.0),
                    total_employee_contributions=scenario_row.get("total_employee_contributions", 0.0),
                    total_employer_match=scenario_row.get("total_employer_match", 0.0),
                    total_employer_core=scenario_row.get("total_employer_core", 0.0),
                    total_employer_cost=scenario_row.get("total_employer_cost", 0.0),
                    employer_cost_rate=scenario_row.get("employer_cost_rate", 0.0),
                    participant_count=int(scenario_row.get("participant_count", 0)),
                )
                values[scenario_id] = scenario_metrics

                deltas[scenario_id] = DCPlanMetrics(
                    participation_rate=scenario_metrics.participation_rate - baseline_metrics.participation_rate,
                    avg_deferral_rate=scenario_metrics.avg_deferral_rate - baseline_metrics.avg_deferral_rate,
                    total_employee_contributions=scenario_metrics.total_employee_contributions - baseline_metrics.total_employee_contributions,
                    total_employer_match=scenario_metrics.total_employer_match - baseline_metrics.total_employer_match,
                    total_employer_core=scenario_metrics.total_employer_core - baseline_metrics.total_employer_core,
                    total_employer_cost=scenario_metrics.total_employer_cost - baseline_metrics.total_employer_cost,
                    employer_cost_rate=scenario_metrics.employer_cost_rate - baseline_metrics.employer_cost_rate,
                    participant_count=scenario_metrics.participant_count - baseline_metrics.participant_count,
                )

            comparison.append(
                DCPlanComparisonYear(year=year, values=values, deltas=deltas)
            )

        return comparison

    def _build_summary_deltas(
        self,
        scenario_data: Dict[str, Dict[str, Any]],
        baseline_data: Dict[str, Any],
        baseline_id: str,
    ) -> Dict[str, DeltaValue]:
        """Build summary delta calculations."""
        summary = {}

        # Final headcount
        baseline_workforce = baseline_data.get("workforce", [])
        baseline_final = (
            baseline_workforce[-1].get("headcount", 0)
            if baseline_workforce
            else 0
        )
        baseline_initial = (
            baseline_workforce[0].get("headcount", 0)
            if baseline_workforce
            else 0
        )

        headcount_scenarios = {}
        headcount_deltas = {}
        headcount_delta_pcts = {}

        for scenario_id, data in scenario_data.items():
            workforce = data.get("workforce", [])
            final = workforce[-1].get("headcount", 0) if workforce else 0
            headcount_scenarios[scenario_id] = float(final)
            delta = final - baseline_final
            headcount_deltas[scenario_id] = float(delta)
            headcount_delta_pcts[scenario_id] = (
                (delta / baseline_final * 100) if baseline_final > 0 else 0.0
            )

        summary["final_headcount"] = DeltaValue(
            baseline=float(baseline_final),
            scenarios=headcount_scenarios,
            deltas=headcount_deltas,
            delta_pcts=headcount_delta_pcts,
        )

        # Total growth percentage
        baseline_growth = (
            ((baseline_final - baseline_initial) / baseline_initial * 100)
            if baseline_initial > 0
            else 0.0
        )

        growth_scenarios = {}
        growth_deltas = {}
        growth_delta_pcts = {}

        for scenario_id, data in scenario_data.items():
            workforce = data.get("workforce", [])
            initial = workforce[0].get("headcount", 0) if workforce else 0
            final = workforce[-1].get("headcount", 0) if workforce else 0
            growth = (
                ((final - initial) / initial * 100)
                if initial > 0
                else 0.0
            )
            growth_scenarios[scenario_id] = growth
            delta = growth - baseline_growth
            growth_deltas[scenario_id] = delta
            growth_delta_pcts[scenario_id] = (
                (delta / abs(baseline_growth) * 100) if baseline_growth != 0 else 0.0
            )

        summary["total_growth_pct"] = DeltaValue(
            baseline=baseline_growth,
            scenarios=growth_scenarios,
            deltas=growth_deltas,
            delta_pcts=growth_delta_pcts,
        )

        # Final participation rate (from DC plan data)
        baseline_dc = baseline_data.get("dc_plan", [])
        baseline_pr = (
            baseline_dc[-1].get("participation_rate", 0.0)
            if baseline_dc
            else 0.0
        )

        pr_scenarios: Dict[str, float] = {}
        pr_deltas: Dict[str, float] = {}
        pr_delta_pcts: Dict[str, float] = {}

        for scenario_id, data in scenario_data.items():
            dc_plan = data.get("dc_plan", [])
            pr = dc_plan[-1].get("participation_rate", 0.0) if dc_plan else 0.0
            pr_scenarios[scenario_id] = pr
            delta = pr - baseline_pr
            pr_deltas[scenario_id] = delta
            pr_delta_pcts[scenario_id] = (
                (delta / abs(baseline_pr) * 100) if baseline_pr != 0 else 0.0
            )

        summary["final_participation_rate"] = DeltaValue(
            baseline=baseline_pr,
            scenarios=pr_scenarios,
            deltas=pr_deltas,
            delta_pcts=pr_delta_pcts,
        )

        # Final employer cost (from DC plan data)
        baseline_ec = (
            baseline_dc[-1].get("total_employer_cost", 0.0)
            if baseline_dc
            else 0.0
        )

        ec_scenarios: Dict[str, float] = {}
        ec_deltas: Dict[str, float] = {}
        ec_delta_pcts: Dict[str, float] = {}

        for scenario_id, data in scenario_data.items():
            dc_plan = data.get("dc_plan", [])
            ec = dc_plan[-1].get("total_employer_cost", 0.0) if dc_plan else 0.0
            ec_scenarios[scenario_id] = ec
            delta = ec - baseline_ec
            ec_deltas[scenario_id] = delta
            ec_delta_pcts[scenario_id] = (
                (delta / abs(baseline_ec) * 100) if baseline_ec != 0 else 0.0
            )

        summary["final_employer_cost"] = DeltaValue(
            baseline=baseline_ec,
            scenarios=ec_scenarios,
            deltas=ec_deltas,
            delta_pcts=ec_delta_pcts,
        )

        return summary
