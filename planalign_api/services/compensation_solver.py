"""Compensation growth solver service.

Provides a "magic button" that takes a target average compensation growth rate
and solves for the COLA, merit, promotion increase, and promotion budget that
achieve that target.

IMPORTANT: This solver accounts for workforce dynamics (turnover and new hires)
which significantly impact average compensation growth. The naive formula
(Growth = COLA + Merit + Promo) ignores the dilution effect from:
- Lower-paid new hires entering the workforce
- Higher-paid experienced employees leaving (or vice versa)

The correct formula models year-over-year average compensation change as:
    Avg_Next = (Stayers × Avg_Current × (1 + raise_rate) + NewHires × NewHire_Avg) / Total_Next
    Growth = (Avg_Next / Avg_Current) - 1
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class LevelDistribution:
    """Distribution of employees across job levels."""
    level: int
    name: str
    headcount: int
    percentage: float
    avg_compensation: float
    promotion_rate: float  # Expected annual promotion rate for this level


@dataclass
class WorkforceDynamics:
    """Workforce dynamics parameters that affect average compensation growth."""
    turnover_rate: float = 0.15  # Annual turnover rate (e.g., 0.15 = 15%)
    workforce_growth_rate: float = 0.03  # Annual workforce growth (e.g., 0.03 = 3%)
    new_hire_comp_ratio: float = 0.85  # New hire avg comp as ratio of workforce avg (e.g., 0.85 = 85%)
    terminating_comp_ratio: float = 1.0  # Terminating avg comp as ratio of workforce avg


@dataclass
class CompensationSolverResult:
    """Result from the compensation solver."""
    # Target input
    target_growth_rate: float  # As decimal (0.02 = 2%)

    # Solved parameters (as percentages for UI display)
    cola_rate: float          # e.g., 2.0 for 2%
    merit_budget: float       # e.g., 3.5 for 3.5%
    promotion_increase: float # e.g., 12.5 for 12.5%
    promotion_budget: float   # e.g., 1.5 for 1.5%

    # Validation
    achieved_growth_rate: float  # Actual growth with these settings
    growth_gap: float            # Difference from target

    # Breakdown for transparency
    cola_contribution: float     # Contribution to growth from COLA
    merit_contribution: float    # Contribution to growth from merit
    promo_contribution: float    # Contribution to growth from promotions

    # Workforce context
    total_headcount: int
    avg_compensation: float
    weighted_promotion_rate: float

    # Fields with defaults must come after fields without defaults
    turnover_contribution: float = 0.0  # Contribution (usually negative) from turnover/new hires

    # Workforce dynamics used
    turnover_rate: float = 0.0
    workforce_growth_rate: float = 0.0
    new_hire_comp_ratio: float = 0.0

    # Recommendation: what new hire comp ratio would achieve target with standard raises
    recommended_new_hire_ratio: float = 0.0  # e.g., 85 means hire at 85% of avg
    recommended_scale_factor: float = 0.0  # Multiplier vs current census-derived ranges

    # Warnings/notes
    warnings: List[str] = field(default_factory=list)


class CompensationSolver:
    """Solves for compensation parameters given a target growth rate."""

    # Default promotion rates by level (if not derived from census)
    # These are typical annual promotion probabilities
    DEFAULT_PROMOTION_RATES = {
        1: 0.20,  # Entry level - high promotion rate
        2: 0.15,  # Mid-level
        3: 0.10,  # Senior
        4: 0.08,  # Manager/Director
        5: 0.05,  # VP/Executive - low promotion rate
    }

    # Merit effectiveness - not everyone gets full merit (performance distribution)
    # Typically 85-90% of budget is actually distributed
    MERIT_EFFECTIVENESS = 0.90

    # Default ratio constraints
    DEFAULT_COLA_TO_MERIT_RATIO = 0.6  # COLA is typically 60% of merit

    def __init__(self, workspaces_root: Path):
        """Initialize solver with workspace root directory."""
        self.workspaces_root = workspaces_root

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """Safely quote SQL identifiers (defense-in-depth)."""
        return f"\"{identifier.replace('\"', '\"\"')}\""

    def analyze_workforce_for_solver(
        self,
        workspace_id: str,
        file_path: str,
    ) -> Tuple[List[LevelDistribution], float, int]:
        """
        Analyze workforce to get level distribution and promotion rates.

        Returns:
            Tuple of (level_distributions, avg_compensation, total_headcount)
        """
        # Resolve the file path
        if file_path.startswith("data/"):
            full_path = self.workspaces_root / workspace_id / file_path
        else:
            full_path = Path(file_path)

        if not full_path.exists():
            raise ValueError(f"Census file not found: {full_path}")

        # Use DuckDB to read census data
        conn = duckdb.connect(":memory:")

        # Read census data based on file type
        if full_path.suffix == ".parquet":
            conn.execute(
                "CREATE TABLE census AS SELECT * FROM read_parquet(?)",
                [str(full_path)],
            )
        else:
            conn.execute(
                "CREATE TABLE census AS SELECT * FROM read_csv_auto(?, header=true)",
                [str(full_path)],
            )

        # Get column names (normalized to lowercase)
        columns_result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'census'").fetchall()
        original_columns = [row[0] for row in columns_result]

        # Rename columns to lowercase
        for col in original_columns:
            if col != col.lower():
                conn.execute(
                    f"ALTER TABLE census RENAME COLUMN {self._quote_identifier(col)} "
                    f"TO {self._quote_identifier(col.lower())}"
                )

        # Get updated column list
        columns_result = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'census'").fetchall()
        columns = [row[0] for row in columns_result]

        # Filter to active employees with robust boolean handling
        if "active" in columns:
            conn.execute(
                """
                DELETE FROM census
                WHERE
                    active IS NULL
                    OR LOWER(TRIM(CAST(active AS VARCHAR))) NOT IN ('true', 't', '1', '1.0', 'yes', 'y')
                """
            )
        elif "employee_termination_date" in columns:
            conn.execute("DELETE FROM census WHERE employee_termination_date IS NOT NULL")

        # Get total headcount
        total_headcount = conn.execute("SELECT COUNT(*) FROM census").fetchone()[0]

        # Get compensation column
        comp_col = None
        for col in ["employee_gross_compensation", "annual_salary", "compensation", "salary"]:
            if col in columns:
                comp_col = col
                break

        if comp_col is None:
            conn.close()
            raise ValueError("No compensation column found in census")

        comp_col_sql = self._quote_identifier(comp_col)
        avg_compensation = conn.execute(
            f"SELECT AVG({comp_col_sql}) FROM census"
        ).fetchone()[0]

        # Get level column
        level_col = None
        for col in ["level_id", "job_level", "level", "employee_level"]:
            if col in columns:
                level_col = col
                break

        # Calculate level distribution
        distributions = []

        if level_col:
            level_col_sql = self._quote_identifier(level_col)
            level_stats = conn.execute(
                f"""
                SELECT
                    {level_col_sql} as level,
                    COUNT(*) as headcount,
                    AVG({comp_col_sql}) as avg_compensation
                FROM census
                GROUP BY {level_col_sql}
                ORDER BY {level_col_sql}
                """
            ).fetchall()

            for row in level_stats:
                level = int(row[0])
                headcount = row[1]
                avg_comp = row[2]

                distributions.append(LevelDistribution(
                    level=level,
                    name=self._level_name(level),
                    headcount=headcount,
                    percentage=headcount / total_headcount,
                    avg_compensation=avg_comp,
                    promotion_rate=self.DEFAULT_PROMOTION_RATES.get(level, 0.10),
                ))
        else:
            # No level data - use single level assumption
            distributions.append(LevelDistribution(
                level=1,
                name="All Employees",
                headcount=total_headcount,
                percentage=1.0,
                avg_compensation=avg_compensation,
                promotion_rate=0.10,  # Default 10% promotion rate
            ))

        conn.close()
        return distributions, avg_compensation, total_headcount

    def _level_name(self, level: int) -> str:
        """Get level name from level ID."""
        names = {
            1: "Staff",
            2: "Manager",
            3: "Sr Manager",
            4: "Director",
            5: "VP",
        }
        return names.get(level, f"Level {level}")

    def calculate_weighted_promotion_rate(
        self,
        distributions: List[LevelDistribution],
    ) -> float:
        """Calculate weighted average promotion rate across levels."""
        if not distributions:
            return 0.10  # Default

        total_weight = 0.0
        weighted_rate = 0.0

        for dist in distributions:
            # Weight by compensation (higher levels have bigger impact on average)
            weight = dist.percentage * dist.avg_compensation
            weighted_rate += weight * dist.promotion_rate
            total_weight += weight

        if total_weight == 0:
            return 0.10

        return weighted_rate / total_weight

    def solve_for_target_growth(
        self,
        target_growth_rate: float,  # As decimal, e.g., 0.02 for 2%
        distributions: Optional[List[LevelDistribution]] = None,
        avg_compensation: Optional[float] = None,
        total_headcount: Optional[int] = None,
        promotion_increase: Optional[float] = None,  # If user wants to lock this
        cola_to_merit_ratio: Optional[float] = None,  # Customize ratio
        workforce_dynamics: Optional[WorkforceDynamics] = None,  # Turnover/new hire effects
    ) -> CompensationSolverResult:
        """
        Solve for compensation parameters given a target growth rate.

        The CORRECT growth model accounts for workforce dynamics:

            Next_Year_Avg = (Stayers × Current_Avg × (1 + raise_rate) + New_Hires × NH_Avg) / Next_Year_Total

        Where:
            - Stayers = Current × (1 - turnover_rate)
            - New_Hires = Current × (turnover_rate + growth_rate)
            - raise_rate = COLA + Merit_Effective + (Promo_Rate × Promo_Increase)
            - NH_Avg = Current_Avg × new_hire_comp_ratio

        Rearranging to solve for raise_rate:
            Let S = stayer_fraction = (1 - turnover) / (1 + growth)
            Let N = new_hire_fraction = (turnover + growth) / (1 + growth)
            Let R = new_hire_comp_ratio

            Growth = S × (1 + raise_rate) + N × R - 1
            raise_rate = (Growth + 1 - N × R) / S - 1

        Then we split raise_rate among COLA, Merit, and Promotions.
        """
        warnings = []

        # Use defaults if not provided
        if distributions is None:
            distributions = [
                LevelDistribution(
                    level=1, name="Staff", headcount=500, percentage=0.50,
                    avg_compensation=50000, promotion_rate=0.20,
                ),
                LevelDistribution(
                    level=2, name="Manager", headcount=250, percentage=0.25,
                    avg_compensation=80000, promotion_rate=0.15,
                ),
                LevelDistribution(
                    level=3, name="Sr Manager", headcount=150, percentage=0.15,
                    avg_compensation=110000, promotion_rate=0.10,
                ),
                LevelDistribution(
                    level=4, name="Director", headcount=80, percentage=0.08,
                    avg_compensation=150000, promotion_rate=0.08,
                ),
                LevelDistribution(
                    level=5, name="VP", headcount=20, percentage=0.02,
                    avg_compensation=250000, promotion_rate=0.05,
                ),
            ]
            warnings.append("Using default level distribution (no census data)")

        if avg_compensation is None:
            avg_compensation = sum(d.avg_compensation * d.percentage for d in distributions)

        if total_headcount is None:
            total_headcount = sum(d.headcount for d in distributions)

        # Use provided workforce dynamics or defaults
        dynamics = workforce_dynamics or WorkforceDynamics()

        # Calculate workforce flow fractions
        # S = fraction of next year's workforce that are stayers (got raises)
        # N = fraction of next year's workforce that are new hires
        next_year_multiplier = 1 + dynamics.workforce_growth_rate
        stayer_fraction = (1 - dynamics.turnover_rate) / next_year_multiplier
        new_hire_fraction = (dynamics.turnover_rate + dynamics.workforce_growth_rate) / next_year_multiplier

        # Calculate weighted promotion rate
        weighted_promo_rate = self.calculate_weighted_promotion_rate(distributions)

        # Default promotion increase if not specified
        if promotion_increase is None:
            promotion_increase = 0.125  # 12.5% is typical

        # Calculate the required raise rate for stayers to achieve target growth
        # Growth = S × (1 + raise_rate) + N × R - 1
        # raise_rate = ((Growth + 1) - N × R) / S - 1
        # raise_rate = (Growth + 1 - N × R - S) / S
        # raise_rate = (Growth + 1 - N × R) / S - 1

        target_multiplier = 1 + target_growth_rate
        new_hire_contribution = new_hire_fraction * dynamics.new_hire_comp_ratio

        # Required raise rate for stayers
        required_stayer_multiplier = (target_multiplier - new_hire_contribution) / stayer_fraction
        required_raise_rate = required_stayer_multiplier - 1

        # Calculate turnover contribution (the drag/boost from workforce dynamics)
        # This is: (N × R + S × 1) - 1 = what growth would be with 0% raises
        baseline_multiplier = stayer_fraction * 1.0 + new_hire_fraction * dynamics.new_hire_comp_ratio
        turnover_contribution = baseline_multiplier - 1  # Usually negative if new hires paid less

        # Log workforce dynamics impact
        if abs(turnover_contribution) > 0.005:
            direction = "drag" if turnover_contribution < 0 else "boost"
            warnings.append(
                f"Workforce dynamics create {abs(turnover_contribution)*100:.1f}% {direction} on avg comp "
                f"(turnover: {dynamics.turnover_rate*100:.0f}%, growth: {dynamics.workforce_growth_rate*100:.0f}%, "
                f"new hire ratio: {dynamics.new_hire_comp_ratio*100:.0f}%)"
            )

        # Calculate promotion contribution to raise rate
        promo_contribution = weighted_promo_rate * promotion_increase

        # Remaining raise must come from COLA + Merit
        remaining_raise = required_raise_rate - promo_contribution

        if remaining_raise < 0:
            warnings.append(
                f"Promotion contribution ({promo_contribution*100:.1f}%) exceeds required raise rate. "
                f"Target may be achieved without COLA/merit."
            )
            remaining_raise = 0.001  # Minimum

        # Use ratio to split between COLA and Merit
        ratio = cola_to_merit_ratio or self.DEFAULT_COLA_TO_MERIT_RATIO

        # Solve: remaining = COLA + Merit × MERIT_EFFECTIVENESS
        # With: COLA = ratio × Merit
        merit_budget = remaining_raise / (ratio + self.MERIT_EFFECTIVENESS)
        cola_rate = ratio * merit_budget

        # Calculate effective merit (what actually gets distributed)
        merit_effective = merit_budget * self.MERIT_EFFECTIVENESS

        # Calculate promotion budget as % of total compensation
        promo_budget = weighted_promo_rate * promotion_increase

        # Verify achieved growth using the full formula
        actual_raise_rate = cola_rate + merit_effective + promo_contribution
        achieved_multiplier = stayer_fraction * (1 + actual_raise_rate) + new_hire_contribution
        achieved_growth = achieved_multiplier - 1
        growth_gap = achieved_growth - target_growth_rate

        # Bounds checking and warnings
        if cola_rate < 0.01:
            warnings.append(f"COLA rate ({cola_rate*100:.1f}%) is very low. May not keep pace with inflation.")
        if cola_rate > 0.08:
            warnings.append(f"COLA rate ({cola_rate*100:.1f}%) is unusually high.")

        if merit_budget < 0.02:
            warnings.append(f"Merit budget ({merit_budget*100:.1f}%) is low. May impact retention.")
        if merit_budget > 0.08:
            warnings.append(f"Merit budget ({merit_budget*100:.1f}%) is unusually high.")

        if required_raise_rate > 0.15:
            warnings.append(
                f"Required stayer raise rate ({required_raise_rate*100:.1f}%) is very high. "
                f"Consider adjusting new hire compensation or turnover assumptions."
            )

        # Calculate recommended new hire ratio to achieve target with the CALCULATED raises
        # Use the actual_raise_rate we just computed, not a hypothetical standard rate
        # Formula: Growth = S × (1 + raise_rate) + N × R - 1
        # Solving for R: R = (Growth + 1 - S × (1 + raise_rate)) / N
        recommended_nh_ratio = 0.0
        recommended_scale = 0.0

        if new_hire_fraction > 0.01:  # Avoid division by zero
            # What new hire ratio would exactly hit target with our calculated raises?
            required_nh_contribution = target_multiplier - stayer_fraction * (1 + actual_raise_rate)
            recommended_nh_ratio = required_nh_contribution / new_hire_fraction

            # Clamp to reasonable range (50% to 120% of avg)
            recommended_nh_ratio = max(0.50, min(1.20, recommended_nh_ratio))

            # Calculate scale factor relative to current new_hire_comp_ratio
            if dynamics.new_hire_comp_ratio > 0.01:
                recommended_scale = recommended_nh_ratio / dynamics.new_hire_comp_ratio
            else:
                recommended_scale = recommended_nh_ratio / 0.85  # Assume 85% baseline

            # Add recommendation to warnings if scale adjustment needed
            if abs(recommended_scale - 1.0) > 0.05:
                direction = "up" if recommended_scale > 1.0 else "down"
                warnings.append(
                    f"To hit {target_growth_rate*100:.1f}% target with these raises, "
                    f"adjust new hire comp {direction} to {recommended_nh_ratio*100:.0f}% of avg "
                    f"(scale: {recommended_scale:.2f}x)"
                )

        return CompensationSolverResult(
            target_growth_rate=target_growth_rate,
            cola_rate=round(cola_rate * 100, 2),          # Convert to percentage
            merit_budget=round(merit_budget * 100, 2),
            promotion_increase=round(promotion_increase * 100, 2),
            promotion_budget=round(promo_budget * 100, 2),
            achieved_growth_rate=round(achieved_growth * 100, 2),
            growth_gap=round(growth_gap * 100, 3),
            cola_contribution=round(cola_rate * 100, 2),
            merit_contribution=round(merit_effective * 100, 2),
            promo_contribution=round(promo_contribution * 100, 2),
            turnover_contribution=round(turnover_contribution * 100, 2),
            total_headcount=total_headcount,
            avg_compensation=round(avg_compensation, 2),
            weighted_promotion_rate=round(weighted_promo_rate * 100, 2),
            turnover_rate=round(dynamics.turnover_rate * 100, 2),
            workforce_growth_rate=round(dynamics.workforce_growth_rate * 100, 2),
            new_hire_comp_ratio=round(dynamics.new_hire_comp_ratio * 100, 2),
            recommended_new_hire_ratio=round(recommended_nh_ratio * 100, 2),
            recommended_scale_factor=round(recommended_scale, 2),
            warnings=warnings,
        )

    def solve_with_census(
        self,
        workspace_id: str,
        file_path: str,
        target_growth_rate: float,
        promotion_increase: Optional[float] = None,
        cola_to_merit_ratio: Optional[float] = None,
        workforce_dynamics: Optional[WorkforceDynamics] = None,
    ) -> CompensationSolverResult:
        """
        Analyze census and solve for target growth rate.

        Args:
            workspace_id: Workspace ID
            file_path: Path to census file
            target_growth_rate: Target as decimal (0.02 = 2%)
            promotion_increase: Optional locked promotion increase (as decimal)
            cola_to_merit_ratio: Optional custom COLA:Merit ratio
            workforce_dynamics: Optional turnover/new hire dynamics

        Returns:
            CompensationSolverResult with solved parameters
        """
        try:
            distributions, avg_comp, headcount = self.analyze_workforce_for_solver(
                workspace_id, file_path
            )
        except Exception as e:
            logger.warning(f"Could not analyze census: {e}. Using defaults.")
            distributions = None
            avg_comp = None
            headcount = None

        return self.solve_for_target_growth(
            target_growth_rate=target_growth_rate,
            distributions=distributions,
            avg_compensation=avg_comp,
            total_headcount=headcount,
            promotion_increase=promotion_increase,
            cola_to_merit_ratio=cola_to_merit_ratio,
            workforce_dynamics=workforce_dynamics,
        )
