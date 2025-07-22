"""
Optimization Algorithms and Parameter Adjustment Logic

This module contains pure business logic functions for compensation optimization,
parameter adjustment algorithms, and convergence logic. These functions are
independent of the Dagster orchestration framework.

Functions:
    adjust_parameters_for_optimization: Intelligent parameter adjustment for compensation optimization
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from dagster import AssetExecutionContext

# Database path configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent


def adjust_parameters_for_optimization(context: AssetExecutionContext, gap: float, optimization_mode: str, iteration: int) -> bool:
    """
    Intelligent parameter adjustment using existing parameter structure.
    Builds on proven parameter validation and application patterns.

    Args:
        context: Dagster asset execution context for logging
        gap: The gap percentage between target and actual growth rates
        optimization_mode: Optimization approach ("Conservative", "Aggressive", or "Balanced")
        iteration: Current optimization iteration number

    Returns:
        bool: True if parameters were successfully adjusted, False otherwise

    Examples:
        Conservative adjustment with small gap:
        >>> adjust_parameters_for_optimization(context, 1.5, "Conservative", 1)

        Aggressive adjustment with large gap:
        >>> adjust_parameters_for_optimization(context, -5.2, "Aggressive", 2)
    """
    try:
        import pandas as pd

        # Load current parameters from comp_levers.csv
        comp_levers_path = Path(PROJECT_ROOT / "dbt" / "seeds" / "comp_levers.csv")
        if not comp_levers_path.exists():
            context.log.error(f"❌ Could not find comp_levers.csv at {comp_levers_path}")
            return False

        df = pd.read_csv(comp_levers_path)

        # Calculate adjustment factors based on optimization mode
        if optimization_mode == "Conservative":
            adjustment_factor = 0.1  # 10% of the gap
        elif optimization_mode == "Aggressive":
            adjustment_factor = 0.5  # 50% of the gap
        else:  # Balanced (default)
            adjustment_factor = 0.3  # 30% of the gap

        # Reduce adjustment factor as iterations progress (convergence acceleration)
        adjustment_factor *= (0.8 ** (iteration - 1))

        # Calculate parameter adjustments
        # Gap > 0 means we need to increase growth (increase compensation parameters)
        # Gap < 0 means we need to decrease growth (decrease compensation parameters)

        gap_adjustment = gap * adjustment_factor / 100  # Convert percentage to decimal

        context.log.info(f"📊 Parameter adjustment calculation:")
        context.log.info(f"   Gap: {gap:+.2f}%")
        context.log.info(f"   Mode: {optimization_mode}")
        context.log.info(f"   Adjustment factor: {adjustment_factor:.3f}")
        context.log.info(f"   Gap adjustment: {gap_adjustment:+.4f}")

        # Update parameters in the DataFrame
        for _, row in df.iterrows():
            param_name = row['parameter_name']
            current_value = row['parameter_value']

            if param_name == 'cola_rate':
                # Adjust COLA rate
                new_value = max(0.01, min(0.08, current_value + gap_adjustment))
                df.loc[df.index == row.name, 'parameter_value'] = new_value

            elif param_name == 'merit_base':
                # Adjust merit rates (distribute adjustment across levels)
                level = row['job_level']
                # Higher levels get smaller adjustments
                level_factor = 1.2 - (level * 0.1)  # Level 1: 1.1x, Level 5: 0.7x
                new_value = max(0.01, min(0.10, current_value + (gap_adjustment * level_factor)))
                df.loc[df.index == row.name, 'parameter_value'] = new_value

            elif param_name == 'new_hire_salary_adjustment':
                # Adjust new hire salary adjustment (more conservative)
                new_value = max(1.0, min(1.4, current_value + (gap_adjustment * 0.5)))
                df.loc[df.index == row.name, 'parameter_value'] = new_value

        # Update metadata
        df['created_at'] = datetime.now().strftime("%Y-%m-%d")
        df['created_by'] = 'optimization_engine'

        # Save updated parameters
        df.to_csv(comp_levers_path, index=False)

        context.log.info(f"✅ Parameters updated for iteration {iteration}")
        context.log.info(f"📊 Updated {len(df)} parameter entries in comp_levers.csv")

        return True

    except Exception as e:
        context.log.error(f"❌ Parameter adjustment failed: {e}")
        import traceback
        context.log.error(f"Detailed error: {traceback.format_exc()}")
        return False
