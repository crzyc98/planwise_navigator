"""Winners & Losers comparison service."""

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional

import duckdb
import pandas as pd

from ..models.winners_losers import (
    BandGroupResult,
    HeatmapCell,
    WinnersLosersResponse,
)
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import (
    DatabasePathResolver,
    create_api_database_path_resolver,
)

logger = logging.getLogger(__name__)


class IncompatibleSimulationYearsError(ValueError):
    """The selected scenarios have no shared snapshot year."""


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
            selected_years = self._select_comparison_year(workspace_id, plan_a, plan_b)
            if selected_years is None:
                return None
            final_year, year_a, year_b = selected_years
            df_a = self._query_scenario_contributions(workspace_id, plan_a, final_year)
            df_b = self._query_scenario_contributions(workspace_id, plan_b, final_year)

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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _select_comparison_year(
        self, workspace_id: str, plan_a: str, plan_b: str
    ) -> Optional[tuple[int, int, int]]:
        """Return the latest common year and each scenario's actual final year."""
        years_a = self._query_scenario_years(workspace_id, plan_a)
        years_b = self._query_scenario_years(workspace_id, plan_b)
        if not years_a or not years_b:
            return None
        common_years = years_a & years_b
        if not common_years:
            raise IncompatibleSimulationYearsError(
                "Plan A and Plan B have no common simulation year. "
                "Run both scenarios with overlapping simulation years."
            )
        return max(common_years), max(years_a), max(years_b)

    def _query_scenario_years(self, workspace_id: str, scenario_id: str) -> set[int]:
        """Read actual snapshot years, including years with no active employees."""
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
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
        self, workspace_id: str, scenario_id: str, comparison_year: int
    ) -> Optional[pd.DataFrame]:
        """Query active employees at the selected common year; never fall back."""
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
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

            if df.empty:
                logger.warning(f"No active employees found for scenario {scenario_id}")
                return None

            return df
        finally:
            conn.close()

    @staticmethod
    def _classify_employees(df_a: pd.DataFrame, df_b: pd.DataFrame) -> tuple:
        """INNER JOIN on employee_id, compute delta, classify.

        Returns (merged_df, total_excluded).
        """
        if (
            df_a.empty
            or df_b.empty
            or "employee_id" not in df_a.columns
            or "employee_id" not in df_b.columns
        ):
            return (
                pd.DataFrame(
                    columns=[
                        "employee_id",
                        "age_band",
                        "tenure_band",
                        "delta",
                        "status",
                    ]
                ),
                0,
            )

        all_a = set(df_a["employee_id"])
        all_b = set(df_b["employee_id"])
        total_excluded = len(all_a.symmetric_difference(all_b))

        merged = df_a.merge(
            df_b[["employee_id", "employer_total"]],
            on="employee_id",
            how="inner",
            suffixes=("_a", "_b"),
        )

        merged["delta"] = merged["employer_total_b"] - merged["employer_total_a"]
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
