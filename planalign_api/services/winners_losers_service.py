"""Winners & Losers comparison service."""

import logging
from typing import Optional

import duckdb
import pandas as pd

from ..models.winners_losers import (
    BandGroupResult,
    HeatmapCell,
    WinnersLosersResponse,
)
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import DatabasePathResolver

logger = logging.getLogger(__name__)


class WinnersLosersService:
    """Compare two scenarios and classify employees as winners/losers/neutral."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ):
        self.storage = storage
        self.db_resolver = db_resolver or DatabasePathResolver(storage)

    def analyze(
        self,
        workspace_id: str,
        plan_a: str,
        plan_b: str,
    ) -> Optional[WinnersLosersResponse]:
        """Compare two scenarios by employer contributions.

        Queries fct_workforce_snapshot for the final simulation year in each
        scenario, joins on employee_id, and classifies each employee as
        winner, loser, or neutral based on total employer contributions.
        """
        try:
            df_a, year_a = self._query_scenario_contributions(
                workspace_id, plan_a
            )
            df_b, year_b = self._query_scenario_contributions(
                workspace_id, plan_b
            )

            if df_a is None or df_b is None:
                return None

            final_year = max(year_a, year_b)

            merged, total_excluded = self._classify_employees(df_a, df_b)
            age_results, tenure_results, heatmap = self._aggregate_results(
                merged
            )

            total = len(merged)
            total_winners = int((merged["status"] == "winner").sum())
            total_losers = int((merged["status"] == "loser").sum())
            total_neutral = int((merged["status"] == "neutral").sum())

            return WinnersLosersResponse(
                plan_a_scenario_id=plan_a,
                plan_b_scenario_id=plan_b,
                final_year=final_year,
                total_compared=total,
                total_excluded=total_excluded,
                total_winners=total_winners,
                total_losers=total_losers,
                total_neutral=total_neutral,
                age_band_results=age_results,
                tenure_band_results=tenure_results,
                heatmap=heatmap,
            )
        except Exception as e:
            logger.error(f"Failed to analyze winners/losers: {e}")
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _query_scenario_contributions(
        self, workspace_id: str, scenario_id: str
    ) -> tuple:
        """Query employer contributions for active employees at final year.

        Returns (DataFrame, final_year) or (None, 0) on failure.
        """
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists:
            logger.error(
                f"Database not found for scenario {scenario_id}"
            )
            return None, 0

        conn = duckdb.connect(str(resolved.path), read_only=True)
        try:
            df = conn.execute(
                """
                SELECT
                    employee_id,
                    age_band,
                    tenure_band,
                    COALESCE(employer_match_amount, 0)
                        + COALESCE(employer_core_amount, 0) AS employer_total,
                    simulation_year
                FROM fct_workforce_snapshot
                WHERE simulation_year = (
                    SELECT MAX(simulation_year) FROM fct_workforce_snapshot
                )
                AND LOWER(employment_status) = 'active'
                """
            ).fetchdf()

            if df.empty:
                logger.warning(
                    f"No active employees found for scenario {scenario_id}"
                )
                return None, 0

            final_year = int(df["simulation_year"].iloc[0])
            return df.drop(columns=["simulation_year"]), final_year
        finally:
            conn.close()

    @staticmethod
    def _classify_employees(
        df_a: pd.DataFrame, df_b: pd.DataFrame
    ) -> tuple:
        """INNER JOIN on employee_id, compute delta, classify.

        Returns (merged_df, total_excluded).
        """
        if df_a.empty or df_b.empty or "employee_id" not in df_a.columns or "employee_id" not in df_b.columns:
            return pd.DataFrame(columns=["employee_id", "age_band", "tenure_band", "delta", "status"]), 0

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

        def _band_group(group_df: pd.DataFrame, label_col: str):
            results = []
            if group_df.empty:
                return results
            grouped = group_df.groupby(label_col)["status"].value_counts().unstack(fill_value=0)
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
            return results

        age_results = _band_group(merged, "age_band")
        tenure_results = _band_group(merged, "tenure_band")

        # Heatmap: age × tenure
        heatmap = []
        if not merged.empty:
            grouped = (
                merged.groupby(["age_band", "tenure_band"])["status"]
                .value_counts()
                .unstack(fill_value=0)
            )
            for (age, tenure) in grouped.index:
                row = grouped.loc[(age, tenure)]
                w = int(row.get("winner", 0))
                l = int(row.get("loser", 0))
                n = int(row.get("neutral", 0))
                total = w + l + n
                heatmap.append(
                    HeatmapCell(
                        age_band=str(age),
                        tenure_band=str(tenure),
                        winners=w,
                        losers=l,
                        neutral=n,
                        total=total,
                        net_pct=round((w - l) / total * 100, 2)
                        if total > 0
                        else 0.0,
                    )
                )

        return age_results, tenure_results, heatmap
