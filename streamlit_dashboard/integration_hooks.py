"""
Integration Hooks for PlanWise Navigator Optimization System
Provides integration points for existing advanced_optimization.py and compensation_tuning.py

This module provides:
- Drop-in replacement functions for existing code
- Backward compatibility with legacy systems
- Seamless integration with new storage system
- Minimal code changes required
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import pandas as pd
import streamlit as st
from optimization_integration import (cached_function, get_duckdb_integration,
                                      get_optimization_cache)
from optimization_results_manager import (get_optimization_results_manager,
                                          load_latest_optimization_results,
                                          save_scipy_optimization_results,
                                          save_tuning_optimization_results)
from optimization_storage import OptimizationRun, OptimizationType

# Set up logging
logger = logging.getLogger(__name__)


class AdvancedOptimizationIntegration:
    """Integration hooks for advanced_optimization.py interface."""

    @staticmethod
    def save_optimization_results(
        scenario_id: str,
        algorithm: str,
        optimization_config: Dict[str, Any],
        results: Dict[str, Any],
        parameter_history: List[Dict[str, float]] = None,
        objective_history: List[float] = None,
    ) -> str:
        """
        Save optimization results from advanced_optimization.py interface.

        This function is designed to be called from advanced_optimization.py
        with minimal code changes.
        """
        try:
            # Extract required information from results
            optimal_parameters = results.get("optimal_parameters", {})
            objective_value = results.get("objective_value", 0.0)
            converged = results.get("converged", False)
            function_evaluations = results.get("function_evaluations", 0)
            runtime_seconds = results.get("runtime_seconds", 0.0)

            # Extract objective weights from config
            objective_weights = optimization_config.get("objectives", {})

            # Extract initial parameters from config
            initial_parameters = optimization_config.get("initial_parameters", {})

            # Extract additional metadata
            use_synthetic = optimization_config.get("use_synthetic", False)
            random_seed = optimization_config.get("random_seed")
            max_evaluations = optimization_config.get("max_evaluations")

            # Create risk assessment
            risk_assessment = {
                "level": results.get("risk_level", "MEDIUM"),
                "assessment_date": datetime.now().isoformat(),
                "parameters_validated": True,
                "constraints_satisfied": len(results.get("constraint_violations", []))
                == 0,
            }

            # Create business context
            business_context = {
                "justification": f"Advanced {algorithm} optimization for scenario {scenario_id}",
                "cost_impact": results.get("estimated_cost_impact"),
                "employee_impact": results.get("estimated_employee_impact"),
            }

            # Save using the results manager
            run_id = save_scipy_optimization_results(
                scenario_id=scenario_id,
                algorithm=algorithm,
                initial_parameters=initial_parameters,
                optimal_parameters=optimal_parameters,
                objective_weights=objective_weights,
                objective_value=objective_value,
                converged=converged,
                function_evaluations=function_evaluations,
                runtime_seconds=runtime_seconds,
                use_synthetic=use_synthetic,
                parameter_history=parameter_history,
                objective_history=objective_history,
                risk_assessment=risk_assessment,
                business_context=business_context,
            )

            # Store in session state for immediate access
            if "last_optimization_result" not in st.session_state:
                st.session_state["last_optimization_result"] = {}

            st.session_state["last_optimization_result"] = {
                "run_id": run_id,
                "scenario_id": scenario_id,
                "algorithm": algorithm,
                "optimal_parameters": optimal_parameters,
                "objective_value": objective_value,
                "converged": converged,
                "runtime_seconds": runtime_seconds,
                "saved_at": datetime.now().isoformat(),
            }

            logger.info(f"Saved advanced optimization results: {run_id}")
            return run_id

        except Exception as e:
            logger.error(f"Failed to save advanced optimization results: {e}")
            raise

    @staticmethod
    def load_optimization_results() -> Optional[Dict[str, Any]]:
        """
        Load the latest optimization results for advanced_optimization.py interface.

        This is a drop-in replacement for the existing load_optimization_results() function.
        """
        try:
            # Check session state first for immediate results
            if "last_optimization_result" in st.session_state:
                session_result = st.session_state["last_optimization_result"]
                if session_result:
                    return session_result

            # Load from storage
            latest_run = load_latest_optimization_results()
            if (
                latest_run
                and latest_run.metadata.optimization_type
                == OptimizationType.ADVANCED_SCIPY
            ):
                # Convert to legacy format for compatibility
                legacy_format = {
                    "run_id": latest_run.metadata.run_id,
                    "scenario_id": latest_run.metadata.scenario_id,
                    "algorithm_used": latest_run.metadata.optimization_engine.value.replace(
                        "scipy_", ""
                    ).upper(),
                    "optimal_parameters": latest_run.results.optimal_parameters,
                    "objective_value": latest_run.results.objective_value,
                    "converged": latest_run.metadata.converged,
                    "function_evaluations": latest_run.metadata.function_evaluations,
                    "runtime_seconds": latest_run.metadata.runtime_seconds,
                    "risk_assessment": latest_run.results.risk_level,
                    "estimated_cost_impact": latest_run.results.estimated_cost_impact,
                    "estimated_employee_impact": latest_run.results.estimated_employee_impact,
                    "saved_at": latest_run.metadata.created_at.isoformat(),
                }

                return legacy_format

            return None

        except Exception as e:
            logger.error(f"Failed to load optimization results: {e}")
            return None

    @staticmethod
    def get_optimization_status() -> Dict[str, Any]:
        """Get the status of the optimization system for monitoring."""
        try:
            results_manager = get_optimization_results_manager()
            recent_runs = results_manager.get_recent_results(5)

            status = {
                "system_healthy": True,
                "recent_runs_count": len(recent_runs),
                "last_run_time": recent_runs[0].created_at.isoformat()
                if recent_runs
                else None,
                "storage_accessible": True,
                "cache_operational": True,
            }

            # Check for recent failures
            failed_runs = [r for r in recent_runs if not r.converged]
            if len(failed_runs) > len(recent_runs) * 0.5:  # More than 50% failed
                status["system_healthy"] = False
                status["warning"] = "High failure rate in recent optimizations"

            return status

        except Exception as e:
            return {
                "system_healthy": False,
                "error": str(e),
                "storage_accessible": False,
                "cache_operational": False,
            }


class CompensationTuningIntegration:
    """Integration hooks for compensation_tuning.py interface."""

    @staticmethod
    def save_tuning_results(
        scenario_id: str,
        parameters: Dict[str, float],
        simulation_results: Dict[str, Any],
        apply_mode: str = "All Years",
        target_years: List[int] = None,
        random_seed: Optional[int] = None,
        execution_method: str = "dagster",
    ) -> str:
        """
        Save compensation tuning results.

        This function integrates with the compensation_tuning.py interface.
        """
        try:
            if target_years is None:
                target_years = [2025, 2026, 2027, 2028, 2029]

            # Extract workforce metrics from simulation results
            workforce_metrics = {}
            if "workforce_summary" in simulation_results:
                workforce_summary = simulation_results["workforce_summary"]

                # Calculate aggregated metrics
                total_headcount = sum(
                    year_data.get("total_headcount", 0)
                    for year_data in workforce_summary.values()
                )
                total_compensation = sum(
                    year_data.get("total_compensation", 0)
                    for year_data in workforce_summary.values()
                )

                workforce_metrics = {
                    "total_headcount": total_headcount,
                    "total_compensation": total_compensation,
                    "avg_compensation": total_compensation / total_headcount
                    if total_headcount > 0
                    else 0,
                    "years_simulated": len(workforce_summary),
                    "cost_impact": {
                        "total_cost": total_compensation,
                        "confidence": "high"
                        if execution_method == "dagster"
                        else "medium",
                    },
                    "employee_impact": {
                        "employees_affected": total_headcount,
                        "years_affected": len(target_years),
                    },
                }

            # Create risk assessment based on parameter values
            risk_assessment = CompensationTuningIntegration._assess_parameter_risk(
                parameters
            )

            # Save using the results manager
            run_id = save_tuning_optimization_results(
                scenario_id=scenario_id,
                parameters=parameters,
                simulation_results=simulation_results,
                apply_mode=apply_mode,
                target_years=target_years,
                random_seed=random_seed,
                execution_method=execution_method,
                workforce_metrics=workforce_metrics,
                risk_assessment=risk_assessment,
            )

            # Store in session state for immediate access
            st.session_state["last_tuning_result"] = {
                "run_id": run_id,
                "scenario_id": scenario_id,
                "parameters": parameters,
                "apply_mode": apply_mode,
                "target_years": target_years,
                "workforce_metrics": workforce_metrics,
                "saved_at": datetime.now().isoformat(),
            }

            logger.info(f"Saved compensation tuning results: {run_id}")
            return run_id

        except Exception as e:
            logger.error(f"Failed to save compensation tuning results: {e}")
            raise

    @staticmethod
    def _assess_parameter_risk(parameters: Dict[str, float]) -> Dict[str, Any]:
        """Assess risk level based on parameter values."""
        risk_factors = []
        warning_count = 0

        # Check merit rates
        merit_rates = [v for k, v in parameters.items() if "merit_rate" in k]
        if merit_rates:
            max_merit = max(merit_rates)
            min_merit = min(merit_rates)

            if max_merit > 0.08:  # More than 8%
                risk_factors.append("High merit rates detected")
                warning_count += 1

            if max_merit - min_merit > 0.03:  # More than 3% spread
                risk_factors.append("Large merit rate variance across levels")
                warning_count += 1

        # Check COLA rate
        cola_rate = parameters.get("cola_rate", 0)
        if cola_rate > 0.04:  # More than 4%
            risk_factors.append("High COLA rate")
            warning_count += 1

        # Check promotion rates
        promo_rates = [v for k, v in parameters.items() if "promotion_probability" in k]
        if promo_rates and max(promo_rates) > 0.20:  # More than 20%
            risk_factors.append("High promotion probabilities")
            warning_count += 1

        # Determine overall risk level
        if warning_count == 0:
            risk_level = "LOW"
        elif warning_count <= 2:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        return {
            "level": risk_level,
            "factors": risk_factors,
            "warning_count": warning_count,
            "assessment_date": datetime.now().isoformat(),
            "parameters_within_bounds": warning_count == 0,
        }

    @staticmethod
    def load_tuning_results() -> Optional[Dict[str, Any]]:
        """Load the latest compensation tuning results."""
        try:
            # Check session state first
            if "last_tuning_result" in st.session_state:
                return st.session_state["last_tuning_result"]

            # Load from storage
            latest_run = load_latest_optimization_results()
            if (
                latest_run
                and latest_run.metadata.optimization_type
                == OptimizationType.COMPENSATION_TUNING
            ):
                # Convert to format expected by compensation_tuning.py
                legacy_format = {
                    "run_id": latest_run.metadata.run_id,
                    "scenario_id": latest_run.metadata.scenario_id,
                    "parameters": latest_run.results.optimal_parameters,
                    "simulation_results": latest_run.simulation_data,
                    "workforce_metrics": latest_run.simulation_data.get(
                        "workforce_snapshots"
                    )
                    if latest_run.simulation_data
                    else {},
                    "risk_assessment": latest_run.results.risk_assessment,
                    "saved_at": latest_run.metadata.created_at.isoformat(),
                }

                return legacy_format

            return None

        except Exception as e:
            logger.error(f"Failed to load tuning results: {e}")
            return None

    @staticmethod
    def get_parameter_history(scenario_pattern: str = None) -> List[Dict[str, Any]]:
        """Get parameter history for analysis and comparison."""
        try:
            results_manager = get_optimization_results_manager()

            # Search for tuning results
            if scenario_pattern:
                recent_runs = results_manager.search_results(query=scenario_pattern)
            else:
                recent_runs = results_manager.get_recent_results(20)

            # Filter for compensation tuning results
            tuning_runs = [
                r
                for r in recent_runs
                if r.optimization_type == OptimizationType.COMPENSATION_TUNING
            ]

            parameter_history = []
            for run_metadata in tuning_runs:
                full_run = results_manager.load_results(run_metadata.run_id)
                if full_run:
                    parameter_history.append(
                        {
                            "timestamp": run_metadata.created_at,
                            "scenario_id": run_metadata.scenario_id,
                            "parameters": full_run.results.optimal_parameters,
                            "risk_level": full_run.results.risk_level,
                            "run_id": run_metadata.run_id,
                        }
                    )

            return parameter_history

        except Exception as e:
            logger.error(f"Failed to get parameter history: {e}")
            return []


class LegacyFunctionReplacements:
    """Drop-in replacements for legacy functions."""

    @staticmethod
    def load_optimization_results():
        """Legacy function replacement for advanced_optimization.py."""
        return AdvancedOptimizationIntegration.load_optimization_results()

    @staticmethod
    def save_optimization_result(
        scenario_id: str, results: Dict[str, Any], algorithm: str = "MANUAL", **kwargs
    ) -> str:
        """Legacy function for saving optimization results."""
        # Create a configuration dict
        optimization_config = {
            "initial_parameters": kwargs.get("initial_parameters", {}),
            "objectives": kwargs.get("objectives", {}),
            "algorithm": algorithm,
            **kwargs,
        }

        return AdvancedOptimizationIntegration.save_optimization_results(
            scenario_id=scenario_id,
            algorithm=algorithm,
            optimization_config=optimization_config,
            results=results,
        )


# Decorator for automatic result saving
def auto_save_optimization_results(optimization_type: str = "advanced"):
    """
    Decorator to automatically save optimization results.

    Usage:
    @auto_save_optimization_results("advanced")
    def run_optimization(...):
        # optimization logic
        return results
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # Run the original function
            results = func(*args, **kwargs)

            # Extract scenario_id from args/kwargs
            scenario_id = kwargs.get(
                "scenario_id", f"auto_save_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )

            try:
                if optimization_type == "advanced":
                    # Save as advanced optimization
                    algorithm = kwargs.get("algorithm", "AUTO")
                    optimization_config = kwargs.get("optimization_config", {})

                    run_id = AdvancedOptimizationIntegration.save_optimization_results(
                        scenario_id=scenario_id,
                        algorithm=algorithm,
                        optimization_config=optimization_config,
                        results=results,
                    )

                    # Add run_id to results
                    if isinstance(results, dict):
                        results["run_id"] = run_id

                elif optimization_type == "tuning":
                    # Save as compensation tuning
                    parameters = kwargs.get("parameters", {})
                    simulation_results = results if isinstance(results, dict) else {}

                    run_id = CompensationTuningIntegration.save_tuning_results(
                        scenario_id=scenario_id,
                        parameters=parameters,
                        simulation_results=simulation_results,
                        **kwargs,
                    )

                    # Add run_id to results
                    if isinstance(results, dict):
                        results["run_id"] = run_id

            except Exception as e:
                logger.warning(f"Auto-save failed: {e}")
                # Don't fail the original function if auto-save fails

            return results

        return wrapper

    return decorator


# Context managers for optimization sessions
class OptimizationSession:
    """Context manager for optimization sessions with automatic cleanup."""

    def __init__(self, session_name: str, optimization_type: OptimizationType):
        self.session_name = session_name
        self.optimization_type = optimization_type
        self.start_time = None
        self.results = []

    def __enter__(self):
        self.start_time = datetime.now()
        logger.info(f"Starting optimization session: {self.session_name}")

        # Initialize session state
        session_key = f"optimization_session_{self.session_name}"
        st.session_state[session_key] = {
            "start_time": self.start_time,
            "optimization_type": self.optimization_type.value,
            "results": [],
        }

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = datetime.now()
        duration = end_time - self.start_time

        logger.info(
            f"Optimization session '{self.session_name}' completed in {duration}"
        )

        # Update session state with final results
        session_key = f"optimization_session_{self.session_name}"
        if session_key in st.session_state:
            st.session_state[session_key].update(
                {
                    "end_time": end_time,
                    "duration_seconds": duration.total_seconds(),
                    "results_count": len(self.results),
                    "completed": True,
                }
            )

    def add_result(self, run_id: str):
        """Add a result to this session."""
        self.results.append(run_id)

        # Update session state
        session_key = f"optimization_session_{self.session_name}"
        if session_key in st.session_state:
            st.session_state[session_key]["results"].append(run_id)


# Utility functions for common operations
def get_optimization_dashboard_url() -> str:
    """Get the URL for the optimization dashboard."""
    return "/optimization_dashboard"


def create_optimization_report(run_ids: List[str]) -> str:
    """Create a comprehensive optimization report for multiple runs."""
    try:
        results_manager = get_optimization_results_manager()

        report_lines = [
            "# PlanWise Navigator Optimization Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Runs Analyzed: {len(run_ids)}",
            "",
            "## Summary",
            "",
        ]

        # Load all runs
        runs = []
        for run_id in run_ids:
            run = results_manager.load_results(run_id)
            if run:
                runs.append(run)

        if not runs:
            return "No valid optimization runs found for report generation."

        # Add summary statistics
        total_runtime = sum(r.metadata.runtime_seconds or 0 for r in runs)
        converged_count = sum(1 for r in runs if r.metadata.converged)

        report_lines.extend(
            [
                f"- Total Runs: {len(runs)}",
                f"- Converged Runs: {converged_count} ({converged_count/len(runs)*100:.1f}%)",
                f"- Total Runtime: {total_runtime:.1f} seconds",
                f"- Average Runtime: {total_runtime/len(runs):.1f} seconds",
                "",
                "## Run Details",
                "",
            ]
        )

        # Add details for each run
        for run in runs:
            report_lines.extend(
                [
                    f"### Run: {run.metadata.scenario_id}",
                    f"- ID: {run.metadata.run_id}",
                    f"- Type: {run.metadata.optimization_type.value}",
                    f"- Engine: {run.metadata.optimization_engine.value}",
                    f"- Status: {run.metadata.status.value}",
                    f"- Created: {run.metadata.created_at}",
                    f"- Runtime: {run.metadata.runtime_seconds:.2f}s"
                    if run.metadata.runtime_seconds
                    else "- Runtime: N/A",
                    f"- Converged: {'Yes' if run.metadata.converged else 'No' if run.metadata.converged is False else 'N/A'}",
                    f"- Objective Value: {run.results.objective_value:.6f}"
                    if run.results.objective_value
                    else "- Objective Value: N/A",
                    f"- Risk Level: {run.results.risk_level}",
                    "",
                ]
            )

        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"Failed to create optimization report: {e}")
        return f"Error creating report: {str(e)}"


# Export integration functions for easy importing
__all__ = [
    "AdvancedOptimizationIntegration",
    "CompensationTuningIntegration",
    "LegacyFunctionReplacements",
    "auto_save_optimization_results",
    "OptimizationSession",
    "get_optimization_dashboard_url",
    "create_optimization_report",
]


if __name__ == "__main__":
    # Test the integration
    print("Testing integration hooks...")

    # Test advanced optimization integration
    test_results = {
        "optimal_parameters": {"merit_rate_level_1": 0.042, "cola_rate": 0.023},
        "objective_value": 0.234567,
        "converged": True,
        "function_evaluations": 87,
        "runtime_seconds": 45.2,
    }

    test_config = {
        "initial_parameters": {"merit_rate_level_1": 0.045, "cola_rate": 0.025},
        "objectives": {"cost": 0.4, "equity": 0.3, "targets": 0.3},
        "algorithm": "SLSQP",
    }

    run_id = AdvancedOptimizationIntegration.save_optimization_results(
        scenario_id="test_integration",
        algorithm="SLSQP",
        optimization_config=test_config,
        results=test_results,
    )

    print(f"Saved test optimization: {run_id}")

    # Test loading
    loaded_results = AdvancedOptimizationIntegration.load_optimization_results()
    if loaded_results:
        print(f"Loaded results: {loaded_results['scenario_id']}")

    print("Integration hooks test completed!")
