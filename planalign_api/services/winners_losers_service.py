"""Winners & Losers comparison service."""

import csv
import logging
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional

import duckdb
import pandas as pd

from ..models.winners_losers import (
    BandGroupResult,
    HeatmapCell,
    EmployeeImpact,
    EmployeeImpactPage,
    WinnersLosersResponse,
)
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import (
    DatabasePathResolver,
    ResolvedDatabasePath,
    create_api_database_path_resolver,
)

logger = logging.getLogger(__name__)


class IncompatibleSimulationYearsError(ValueError):
    """The selected scenarios have no shared snapshot year."""


class ComparisonEvidenceChangedError(ValueError):
    """The selected results changed after the summary was loaded."""


def _cents(value: float | Decimal) -> int:
    return int(
        (Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def _dollar_impact(employees: pd.DataFrame) -> dict[str, float]:
    cents = [_cents(delta) for delta in employees["delta"]]
    increases = sum(delta for delta in cents if delta > 0)
    decreases = sum(delta for delta in cents if delta < 0)
    net = increases + decreases
    average = (
        (Decimal(net) / len(cents)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if cents
        else Decimal(0)
    )
    return {
        "total_increases": increases / 100,
        "total_decreases": decreases / 100,
        "net_contribution_change": net / 100,
        "average_change": float(average) / 100,
    }


# Path to dbt seeds directory (relative to project root)
DBT_SEEDS_DIR = Path(__file__).parent.parent.parent / "dbt" / "seeds"


def _load_band_display_order(band_type: str) -> Dict[str, int]:
    """Map band_label -> display_order from the dbt seed CSV.

    band_label strings like "< 25" sort after "25-34" alphabetically, so
    chart/heatmap ordering must come from the seed's display_order instead
    of the default groupby sort.
    """
    csv_path = DBT_SEEDS_DIR / f"config_{band_type}_bands.csv"
    order: Dict[str, int] = {}
    try:
        with open(csv_path, "r", newline="") as f:
            for row in csv.DictReader(f):
                order[row["band_label"]] = int(row["display_order"])
    except (FileNotFoundError, KeyError, ValueError) as e:
        logger.warning(f"Could not load {band_type} band display order: {e}")
    return order


class WinnersLosersService:
    """Compare two scenarios and classify employees as winners/losers/neutral."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    def analyze(
        self,
        workspace_id: str,
        plan_a: str,
        plan_b: str,
    ) -> Optional[WinnersLosersResponse]:
        """Compare two scenarios by employer contributions.

        Queries both snapshots at their latest shared simulation year,
        joins on employee_id, and classifies each employee as
        winner, loser, or neutral based on total employer contributions.
        Disjoint horizons raise IncompatibleSimulationYearsError.
        """
        try:
            resolved_a = self.db_resolver.resolve(workspace_id, plan_a)
            resolved_b = self.db_resolver.resolve(workspace_id, plan_b)
            selected_years = self._select_comparison_year(
                workspace_id, plan_a, plan_b, resolved_a, resolved_b
            )
            if selected_years is None:
                return None
            final_year, year_a, year_b = selected_years
            df_a = self._query_scenario_contributions(
                workspace_id, plan_a, final_year, resolved_a
            )
            df_b = self._query_scenario_contributions(
                workspace_id, plan_b, final_year, resolved_b
            )

            if df_a is None or df_b is None:
                return None

            merged, total_excluded = self._classify_employees(df_a, df_b)
            age_results, tenure_results, heatmap = self._aggregate_results(merged)

            total = len(merged)
            total_winners = int((merged["status"] == "winner").sum())
            total_losers = int((merged["status"] == "loser").sum())
            total_neutral = int((merged["status"] == "neutral").sum())

            return WinnersLosersResponse(
                plan_a_scenario_id=plan_a,
                plan_b_scenario_id=plan_b,
                plan_a_run_id=resolved_a.run_id,
                plan_b_run_id=resolved_b.run_id,
                **_dollar_impact(merged),
                final_year=final_year,
                plan_a_final_year=year_a,
                plan_b_final_year=year_b,
                total_compared=total,
                total_excluded=total_excluded,
                total_winners=total_winners,
                total_losers=total_losers,
                total_neutral=total_neutral,
                age_band_results=age_results,
                tenure_band_results=tenure_results,
                heatmap=heatmap,
            )
        except IncompatibleSimulationYearsError:
            raise
        except Exception as e:
            logger.error(f"Failed to analyze winners/losers: {e}")
            return None

    def employee_impacts(
        self,
        workspace_id: str,
        plan_a: str,
        plan_b: str,
        comparison_year: int,
        plan_a_run_id: str | None = None,
        plan_b_run_id: str | None = None,
        age_band: str | None = None,
        tenure_band: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> EmployeeImpactPage:
        """Read a filtered page only while the summary's selected evidence is current."""
        merged = self._pinned_population(
            workspace_id, plan_a, plan_b, comparison_year, plan_a_run_id, plan_b_run_id
        )
        if age_band is not None:
            merged = merged[merged["age_band"] == age_band]
        if tenure_band is not None:
            merged = merged[merged["tenure_band"] == tenure_band]
        page = merged.sort_values("employee_id").iloc[offset : offset + limit]
        return EmployeeImpactPage(
            plan_a_scenario_id=plan_a,
            plan_b_scenario_id=plan_b,
            plan_a_run_id=plan_a_run_id,
            plan_b_run_id=plan_b_run_id,
            final_year=comparison_year,
            age_band=age_band,
            tenure_band=tenure_band,
            total=len(merged),
            offset=offset,
            limit=limit,
            employees=self._employee_rows(page),
            **_dollar_impact(merged),
        )

    def _pinned_population(
        self,
        workspace_id: str,
        plan_a: str,
        plan_b: str,
        comparison_year: int,
        plan_a_run_id: str | None,
        plan_b_run_id: str | None,
    ) -> pd.DataFrame:
        """Resolve once, verify the summary evidence, and read that same population."""
        resolved_a = self.db_resolver.resolve(workspace_id, plan_a)
        resolved_b = self.db_resolver.resolve(workspace_id, plan_b)
        if (resolved_a.run_id, resolved_b.run_id) != (plan_a_run_id, plan_b_run_id):
            raise ComparisonEvidenceChangedError(
                "Selected runs changed. Refresh the comparison before opening employee detail."
            )
        years = self._select_comparison_year(
            workspace_id, plan_a, plan_b, resolved_a, resolved_b
        )
        if years is None or years[0] != comparison_year:
            raise ComparisonEvidenceChangedError(
                "Comparison year changed or results are unavailable. Refresh the comparison."
            )
        df_a = self._query_scenario_contributions(
            workspace_id, plan_a, comparison_year, resolved_a
        )
        df_b = self._query_scenario_contributions(
            workspace_id, plan_b, comparison_year, resolved_b
        )
        merged, _ = self._classify_employees(df_a, df_b)
        return merged

    @staticmethod
    def _employee_rows(page: pd.DataFrame) -> List[EmployeeImpact]:
        return [
            EmployeeImpact(
                employee_id=row.employee_id,
                age_band=row.age_band,
                tenure_band=row.tenure_band,
                plan_a_amount=row.employer_total_a,
                plan_b_amount=row.employer_total_b,
                delta=row.delta,
                status=row.status,
            )
            for row in page.itertuples()
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _select_comparison_year(
        self,
        workspace_id: str,
        plan_a: str,
        plan_b: str,
        resolved_a: ResolvedDatabasePath | None = None,
        resolved_b: ResolvedDatabasePath | None = None,
    ) -> Optional[tuple[int, int, int]]:
        """Return the latest common year and each scenario's actual final year."""
        years_a = self._query_scenario_years(workspace_id, plan_a, resolved_a)
        years_b = self._query_scenario_years(workspace_id, plan_b, resolved_b)
        if not years_a or not years_b:
            return None
        common_years = years_a & years_b
        if not common_years:
            raise IncompatibleSimulationYearsError(
                "Plan A and Plan B have no common simulation year. "
                "Run both scenarios with overlapping simulation years."
            )
        return max(common_years), max(years_a), max(years_b)

    def _query_scenario_years(
        self,
        workspace_id: str,
        scenario_id: str,
        resolved: ResolvedDatabasePath | None = None,
    ) -> set[int]:
        """Read actual snapshot years, including years with no active employees."""
        resolved = resolved or self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            logger.error(f"Database not found for scenario {scenario_id}")
            return set()
        with duckdb.connect(str(resolved.path), read_only=True) as conn:
            rows = conn.execute(
                "SELECT DISTINCT simulation_year FROM fct_workforce_snapshot "
                "WHERE simulation_year IS NOT NULL"
            ).fetchall()
        return {int(row[0]) for row in rows}

    def _query_scenario_contributions(
        self,
        workspace_id: str,
        scenario_id: str,
        comparison_year: int,
        resolved: ResolvedDatabasePath | None = None,
    ) -> pd.DataFrame:
        """Query active employees at the selected common year; never fall back."""
        resolved = resolved or self.db_resolver.resolve(workspace_id, scenario_id)
        conn = duckdb.connect(str(resolved.path), read_only=True)
        try:
            df = conn.execute(
                """
                SELECT
                    employee_id,
                    age_band,
                    tenure_band,
                    COALESCE(employer_match_amount, 0)
                        + COALESCE(employer_core_amount, 0) AS employer_total
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
                AND LOWER(employment_status) = 'active'
                """,
                [comparison_year],
            ).fetchdf()

            return df
        finally:
            conn.close()

    @staticmethod
    def _classify_employees(
        df_a: pd.DataFrame, df_b: pd.DataFrame
    ) -> tuple[pd.DataFrame, int]:
        """INNER JOIN on employee_id, compute delta, classify.

        Returns (merged_df, total_excluded).
        """
        all_a = set(df_a["employee_id"])
        all_b = set(df_b["employee_id"])
        total_excluded = len(all_a.symmetric_difference(all_b))

        merged = df_a.merge(
            df_b[["employee_id", "employer_total"]],
            on="employee_id",
            how="inner",
            suffixes=("_a", "_b"),
            validate="one_to_one",
        )
        cents_a = merged["employer_total_a"].map(_cents)
        cents_b = merged["employer_total_b"].map(_cents)
        merged["employer_total_a"] = cents_a / 100
        merged["employer_total_b"] = cents_b / 100
        merged["delta"] = (cents_b - cents_a) / 100
        merged[["age_band", "tenure_band"]] = merged[
            ["age_band", "tenure_band"]
        ].fillna("Unknown")
        merged["status"] = merged["delta"].apply(
            lambda d: "winner" if d > 0 else ("loser" if d < 0 else "neutral")
        )

        return merged, total_excluded

    @staticmethod
    def _aggregate_results(merged: pd.DataFrame) -> tuple:
        """Group by age_band, tenure_band, and age×tenure.

        Returns (age_results, tenure_results, heatmap).
        """

        def _band_group(
            group_df: pd.DataFrame, label_col: str, order_map: Dict[str, int]
        ) -> List[BandGroupResult]:
            results: List[BandGroupResult] = []
            if group_df.empty:
                return results
            grouped = (
                group_df.groupby(label_col)["status"]
                .value_counts()
                .unstack(fill_value=0)
            )
            for label in grouped.index:
                row = grouped.loc[label]
                winners = int(row.get("winner", 0))
                losers = int(row.get("loser", 0))
                neutral = int(row.get("neutral", 0))
                results.append(
                    BandGroupResult(
                        band_label=str(label),
                        winners=winners,
                        losers=losers,
                        neutral=neutral,
                        total=winners + losers + neutral,
                        **_dollar_impact(group_df[group_df[label_col] == label]),
                    )
                )
            results.sort(key=lambda r: order_map.get(r.band_label, len(order_map)))
            return results

        age_order = _load_band_display_order("age")
        tenure_order = _load_band_display_order("tenure")

        age_results = _band_group(merged, "age_band", age_order)
        tenure_results = _band_group(merged, "tenure_band", tenure_order)

        # Heatmap: age × tenure
        heatmap = []
        if not merged.empty:
            grouped = (
                merged.groupby(["age_band", "tenure_band"])["status"]
                .value_counts()
                .unstack(fill_value=0)
            )
            for age, tenure in grouped.index:
                row = grouped.loc[(age, tenure)]
                w = int(row.get("winner", 0))
                losers = int(row.get("loser", 0))
                n = int(row.get("neutral", 0))
                total = w + losers + n
                heatmap.append(
                    HeatmapCell(
                        age_band=str(age),
                        tenure_band=str(tenure),
                        winners=w,
                        losers=losers,
                        neutral=n,
                        total=total,
                        **_dollar_impact(
                            merged[
                                (merged["age_band"] == age)
                                & (merged["tenure_band"] == tenure)
                            ]
                        ),
                        net_pct=(
                            round((w - losers) / total * 100, 2) if total > 0 else 0.0
                        ),
                    )
                )

            heatmap.sort(
                key=lambda c: (
                    age_order.get(c.age_band, len(age_order)),
                    tenure_order.get(c.tenure_band, len(tenure_order)),
                )
            )

        return age_results, tenure_results, heatmap
