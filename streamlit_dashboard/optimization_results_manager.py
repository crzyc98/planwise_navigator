"""
OptimizationResultsManager - Unified Interface for Optimization Results
Bridges advanced_optimization.py and compensation_tuning.py with the storage system.

This module provides a high-level interface for saving, loading, and managing
optimization results across different optimization types in PlanWise Navigator.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import streamlit as st
from optimization_storage import (ExportFormat, OptimizationConfiguration,
                                  OptimizationEngine, OptimizationMetadata,
                                  OptimizationObjective, OptimizationResults,
                                  OptimizationRun, OptimizationStatus,
                                  OptimizationStorageManager, OptimizationType,
                                  get_optimization_storage)

# Set up logging
logger = logging.getLogger(__name__)


class OptimizationResultsManager:
    """
    High-level manager for optimization results that provides a unified interface
    for both advanced_optimization.py and compensation_tuning.py.
    """

    def __init__(self):
        """Initialize the results manager."""
        self.storage = get_optimization_storage()
        self.session_key = "optimization_results_manager"
        self._init_session_state()

    def _init_session_state(self):
        """Initialize session state for the results manager."""
        if self.session_key not in st.session_state:
            st.session_state[self.session_key] = {
                "current_results": None,
                "comparison_mode": False,
                "selected_runs": [],
                "export_queue": [],
                "last_refresh": datetime.now(),
            }

    def save_advanced_optimization_results(
        self,
        scenario_id: str,
        algorithm: str,
        initial_parameters: Dict[str, float],
        optimal_parameters: Dict[str, float],
        objective_weights: Dict[str, float],
        objective_value: float,
        converged: bool,
        function_evaluations: int,
        runtime_seconds: float,
        use_synthetic: bool = False,
        parameter_history: List[Dict[str, float]] = None,
        objective_history: List[float] = None,
        risk_assessment: Dict[str, Any] = None,
        business_context: Dict[str, Any] = None,
    ) -> str:
        """Save results from advanced optimization interface."""

        # Map algorithm to engine type
        engine_mapping = {
            "SLSQP": OptimizationEngine.SCIPY_SLSQP,
            "DE": OptimizationEngine.SCIPY_DE,
            "L-BFGS-B": OptimizationEngine.SCIPY_LBFGSB,
        }

        engine = engine_mapping.get(algorithm, OptimizationEngine.SCIPY_SLSQP)

        # Create metadata
        metadata = OptimizationMetadata(
            scenario_id=scenario_id,
            optimization_type=OptimizationType.ADVANCED_SCIPY,
            optimization_engine=engine,
            status=OptimizationStatus.COMPLETED,
            function_evaluations=function_evaluations,
            runtime_seconds=runtime_seconds,
            converged=converged,
            use_synthetic_mode=use_synthetic,
            description=f"Advanced SciPy optimization using {algorithm}",
            tags=["advanced", "scipy", algorithm.lower()],
            business_justification=business_context.get("justification", "")
            if business_context
            else "",
        )

        # Create configuration
        objectives = [
            OptimizationObjective(
                name="cost",
                weight=objective_weights.get("cost", 0.0),
                direction="minimize",
                description="Total compensation cost optimization",
            ),
            OptimizationObjective(
                name="equity",
                weight=objective_weights.get("equity", 0.0),
                direction="minimize",
                description="Compensation equity across levels",
            ),
            OptimizationObjective(
                name="targets",
                weight=objective_weights.get("targets", 0.0),
                direction="minimize",
                description="Workforce growth target achievement",
            ),
        ]

        configuration = OptimizationConfiguration(
            objectives=objectives,
            initial_parameters=initial_parameters,
            algorithm_config={"algorithm": algorithm, "use_synthetic": use_synthetic},
        )

        # Create results
        results = OptimizationResults(
            objective_value=objective_value,
            objective_breakdown=objective_weights,
            optimal_parameters=optimal_parameters,
            parameter_history=parameter_history or [],
            objective_history=objective_history or [],
            risk_level=risk_assessment.get("level", "MEDIUM")
            if risk_assessment
            else "MEDIUM",
            risk_assessment=risk_assessment or {},
            estimated_cost_impact=business_context.get("cost_impact")
            if business_context
            else None,
            estimated_employee_impact=business_context.get("employee_impact")
            if business_context
            else None,
        )

        # Create optimization run
        run = OptimizationRun(
            metadata=metadata, configuration=configuration, results=results
        )

        # Save and update session
        run_id = self.storage.save_run_with_session_cache(run)

        # Update session state
        manager_state = st.session_state[self.session_key]
        manager_state["current_results"] = run
        manager_state["last_refresh"] = datetime.now()

        logger.info(f"Saved advanced optimization results: {run_id}")
        return run_id

    def save_compensation_tuning_results(
        self,
        scenario_id: str,
        parameters: Dict[str, float],
        simulation_results: Dict[str, Any],
        apply_mode: str,
        target_years: List[int],
        random_seed: Optional[int] = None,
        execution_method: str = "dagster",
        workforce_metrics: Dict[str, Any] = None,
        risk_assessment: Dict[str, Any] = None,
    ) -> str:
        """Save results from compensation tuning interface."""

        # Create metadata
        metadata = OptimizationMetadata(
            scenario_id=scenario_id,
            optimization_type=OptimizationType.COMPENSATION_TUNING,
            optimization_engine=OptimizationEngine.MANUAL,
            status=OptimizationStatus.COMPLETED,
            random_seed=random_seed,
            use_synthetic_mode=False,  # Compensation tuning uses real simulations
            description=f"Compensation parameter tuning ({apply_mode} mode)",
            tags=["compensation_tuning", apply_mode.lower(), execution_method],
            business_justification=f"Parameter adjustment for years {', '.join(map(str, target_years))}",
        )

        # Create configuration
        configuration = OptimizationConfiguration(
            initial_parameters=parameters,
            algorithm_config={
                "apply_mode": apply_mode,
                "target_years": target_years,
                "execution_method": execution_method,
            },
        )

        # Process simulation results for objective value
        objective_value = 0.0
        if workforce_metrics:
            # Calculate a composite objective based on workforce metrics
            total_comp = workforce_metrics.get("total_compensation", 0)
            headcount = workforce_metrics.get("total_headcount", 1)
            avg_comp = total_comp / headcount if headcount > 0 else 0
            objective_value = avg_comp / 1000000  # Normalize to millions

        # Create results
        results = OptimizationResults(
            objective_value=objective_value,
            optimal_parameters=parameters,
            risk_level=risk_assessment.get("level", "MEDIUM")
            if risk_assessment
            else "MEDIUM",
            risk_assessment=risk_assessment or {},
            projected_outcomes=simulation_results,
            estimated_cost_impact=workforce_metrics.get("cost_impact")
            if workforce_metrics
            else None,
            estimated_employee_impact=workforce_metrics.get("employee_impact")
            if workforce_metrics
            else None,
        )

        # Create optimization run
        run = OptimizationRun(
            metadata=metadata,
            configuration=configuration,
            results=results,
            simulation_data={
                "simulation_results": simulation_results,
                "workforce_snapshots": workforce_metrics or {},
                "data_quality_metrics": {},
            },
        )

        # Save and update session
        run_id = self.storage.save_run_with_session_cache(run)

        # Update session state
        manager_state = st.session_state[self.session_key]
        manager_state["current_results"] = run
        manager_state["last_refresh"] = datetime.now()

        logger.info(f"Saved compensation tuning results: {run_id}")
        return run_id

    def load_results(self, run_id: str) -> Optional[OptimizationRun]:
        """Load optimization results by run ID."""
        return self.storage.load_run_with_session_cache(run_id)

    def get_recent_results(self, limit: int = 10) -> List[OptimizationMetadata]:
        """Get recent optimization results."""
        return self.storage.get_recent_runs(limit)

    def search_results(
        self,
        query: str = None,
        optimization_type: OptimizationType = None,
        status: OptimizationStatus = None,
        date_range: Tuple[datetime, datetime] = None,
    ) -> List[OptimizationMetadata]:
        """Search optimization results with various filters."""
        if query:
            return self.storage.storage.search_optimization_runs(query)
        else:
            return self.storage.storage.list_optimization_runs(
                optimization_type=optimization_type, status=status, limit=50
            )

    def compare_results(self, run_ids: List[str]) -> Dict[str, Any]:
        """Compare multiple optimization results."""
        runs = []
        for run_id in run_ids:
            run = self.load_results(run_id)
            if run:
                runs.append(run)

        if not runs:
            return {"error": "No valid runs found for comparison"}

        comparison = {
            "run_count": len(runs),
            "run_metadata": [
                {
                    "run_id": run.metadata.run_id,
                    "scenario_id": run.metadata.scenario_id,
                    "optimization_type": run.metadata.optimization_type.value,
                    "created_at": run.metadata.created_at,
                    "objective_value": run.results.objective_value,
                    "risk_level": run.results.risk_level,
                }
                for run in runs
            ],
            "parameter_comparison": self._compare_parameters(runs),
            "objective_comparison": self._compare_objectives(runs),
            "risk_comparison": self._compare_risk_levels(runs),
        }

        return comparison

    def _compare_parameters(self, runs: List[OptimizationRun]) -> Dict[str, Any]:
        """Compare parameters across runs."""
        all_params = set()
        for run in runs:
            all_params.update(run.results.optimal_parameters.keys())

        comparison = {}
        for param in all_params:
            values = []
            for run in runs:
                value = run.results.optimal_parameters.get(param)
                values.append(
                    {
                        "run_id": run.metadata.run_id,
                        "value": value,
                        "scenario": run.metadata.scenario_id,
                    }
                )

            comparison[param] = {
                "values": values,
                "min": min([v["value"] for v in values if v["value"] is not None]),
                "max": max([v["value"] for v in values if v["value"] is not None]),
                "variance": self._calculate_variance(
                    [v["value"] for v in values if v["value"] is not None]
                ),
            }

        return comparison

    def _compare_objectives(self, runs: List[OptimizationRun]) -> Dict[str, Any]:
        """Compare objective values across runs."""
        objectives = []
        for run in runs:
            objectives.append(
                {
                    "run_id": run.metadata.run_id,
                    "scenario": run.metadata.scenario_id,
                    "objective_value": run.results.objective_value,
                    "breakdown": run.results.objective_breakdown,
                }
            )

        return {
            "objectives": objectives,
            "best_run": min(
                objectives, key=lambda x: x["objective_value"] or float("inf")
            ),
            "worst_run": max(objectives, key=lambda x: x["objective_value"] or 0),
        }

    def _compare_risk_levels(self, runs: List[OptimizationRun]) -> Dict[str, Any]:
        """Compare risk levels across runs."""
        risk_levels = {}
        for run in runs:
            risk_level = run.results.risk_level
            if risk_level not in risk_levels:
                risk_levels[risk_level] = []
            risk_levels[risk_level].append(
                {"run_id": run.metadata.run_id, "scenario": run.metadata.scenario_id}
            )

        return risk_levels

    def _calculate_variance(self, values: List[float]) -> float:
        """Calculate variance of a list of values."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance

    def export_results(
        self,
        run_id: str,
        format: ExportFormat,
        output_path: str = None,
        include_comparison: bool = False,
    ) -> str:
        """Export optimization results to specified format."""
        export_path = self.storage.storage.export_optimization_run(
            run_id=run_id,
            format=format,
            output_path=output_path,
            include_simulation_data=True,
        )

        # Add to export queue in session state
        manager_state = st.session_state[self.session_key]
        manager_state["export_queue"].append(
            {
                "run_id": run_id,
                "format": format.value,
                "path": export_path,
                "exported_at": datetime.now(),
            }
        )

        return export_path

    def get_export_history(self, run_id: str) -> List[Dict[str, Any]]:
        """Get export history for a specific run."""
        return self.storage.storage.get_export_history(run_id)

    def delete_results(self, run_id: str) -> bool:
        """Delete optimization results."""
        success = self.storage.storage.delete_optimization_run(run_id)

        if success:
            # Clear from session cache
            manager_state = st.session_state[self.session_key]
            if (
                manager_state["current_results"]
                and manager_state["current_results"].metadata.run_id == run_id
            ):
                manager_state["current_results"] = None

            # Remove from comparison selection
            manager_state["selected_runs"] = [
                rid for rid in manager_state["selected_runs"] if rid != run_id
            ]

        return success

    def create_results_dashboard(self) -> None:
        """Create a Streamlit dashboard for viewing and managing optimization results."""
        st.header("🎯 Optimization Results Dashboard")

        # Tabs for different views
        tab1, tab2, tab3, tab4 = st.tabs(
            [
                "📊 Recent Results",
                "🔍 Search & Filter",
                "⚖️ Compare Results",
                "📥 Export & Archive",
            ]
        )

        with tab1:
            self._create_recent_results_view()

        with tab2:
            self._create_search_filter_view()

        with tab3:
            self._create_comparison_view()

        with tab4:
            self._create_export_view()

    def _create_recent_results_view(self):
        """Create the recent results view."""
        st.subheader("Recent Optimization Results")

        # Refresh button
        if st.button("🔄 Refresh", key="refresh_recent"):
            self.storage.clear_session_cache()
            st.rerun()

        # Get recent results
        recent_runs = self.get_recent_results(20)

        if not recent_runs:
            st.info("No optimization results found.")
            return

        # Create results table
        results_data = []
        for run in recent_runs:
            results_data.append(
                {
                    "Run ID": run.run_id,
                    "Scenario": run.scenario_id,
                    "Type": run.optimization_type.value.replace("_", " ").title(),
                    "Engine": run.optimization_engine.value.replace("_", " ").title(),
                    "Status": run.status.value.title(),
                    "Created": run.created_at.strftime("%Y-%m-%d %H:%M"),
                    "Runtime": f"{run.runtime_seconds:.1f}s"
                    if run.runtime_seconds
                    else "N/A",
                    "Converged": "✅"
                    if run.converged
                    else "❌"
                    if run.converged is False
                    else "N/A",
                }
            )

        df = pd.DataFrame(results_data)

        # Display table with selection
        selected_indices = st.dataframe(
            df, use_container_width=True, selection_mode="multi-row", on_select="rerun"
        )

        # Action buttons for selected results
        if (
            selected_indices
            and hasattr(selected_indices, "selection")
            and selected_indices.selection["rows"]
        ):
            selected_runs = [recent_runs[i] for i in selected_indices.selection["rows"]]

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("📋 View Details"):
                    st.session_state["selected_run_details"] = selected_runs[0].run_id
            with col2:
                if st.button("⚖️ Compare Selected"):
                    manager_state = st.session_state[self.session_key]
                    manager_state["selected_runs"] = [
                        run.run_id for run in selected_runs
                    ]
                    manager_state["comparison_mode"] = True
            with col3:
                if st.button("📥 Export Selected"):
                    st.session_state["export_selected"] = [
                        run.run_id for run in selected_runs
                    ]

        # Show details if selected
        if "selected_run_details" in st.session_state:
            self._show_run_details(st.session_state["selected_run_details"])

    def _create_search_filter_view(self):
        """Create the search and filter view."""
        st.subheader("Search & Filter Results")

        # Search controls
        col1, col2 = st.columns(2)
        with col1:
            search_query = st.text_input(
                "🔍 Search by scenario, description, or keywords"
            )
        with col2:
            optimization_type = st.selectbox(
                "Filter by Type",
                options=[None] + [t.value for t in OptimizationType],
                format_func=lambda x: "All Types"
                if x is None
                else x.replace("_", " ").title(),
            )

        # Date range filter
        col3, col4 = st.columns(2)
        with col3:
            start_date = st.date_input(
                "Start Date", value=datetime.now().date() - pd.Timedelta(days=30)
            )
        with col4:
            end_date = st.date_input("End Date", value=datetime.now().date())

        # Search button
        if st.button("🔍 Search", key="search_results"):
            opt_type = (
                OptimizationType(optimization_type) if optimization_type else None
            )
            results = self.search_results(
                query=search_query if search_query else None, optimization_type=opt_type
            )

            # Filter by date range
            if results:
                filtered_results = [
                    r for r in results if start_date <= r.created_at.date() <= end_date
                ]

                if filtered_results:
                    st.success(f"Found {len(filtered_results)} matching results")
                    # Display results similar to recent results view
                    # ... (similar table display code)
                else:
                    st.info("No results match the specified criteria")
            else:
                st.info("No results found")

    def _create_comparison_view(self):
        """Create the comparison view."""
        st.subheader("Compare Optimization Results")

        manager_state = st.session_state[self.session_key]
        selected_runs = manager_state.get("selected_runs", [])

        if len(selected_runs) < 2:
            st.info(
                "Select at least 2 results from the 'Recent Results' tab to compare them."
            )
            return

        # Display comparison
        comparison = self.compare_results(selected_runs)

        # Overview metrics
        st.subheader("Comparison Overview")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Runs Compared", comparison["run_count"])
        with col2:
            best_run = comparison["objective_comparison"]["best_run"]
            st.metric("Best Objective", f"{best_run['objective_value']:.4f}")
        with col3:
            risk_counts = {k: len(v) for k, v in comparison["risk_comparison"].items()}
            most_common_risk = max(risk_counts, key=risk_counts.get)
            st.metric("Most Common Risk", most_common_risk)

        # Parameter comparison chart
        st.subheader("Parameter Comparison")
        if comparison["parameter_comparison"]:
            param_names = list(comparison["parameter_comparison"].keys())
            selected_param = st.selectbox("Select parameter to compare", param_names)

            if selected_param:
                param_data = comparison["parameter_comparison"][selected_param]
                df = pd.DataFrame(param_data["values"])

                import plotly.express as px

                fig = px.bar(
                    df, x="scenario", y="value", title=f"{selected_param} Comparison"
                )
                st.plotly_chart(fig, use_container_width=True)

        # Clear comparison
        if st.button("🗑️ Clear Comparison"):
            manager_state["selected_runs"] = []
            manager_state["comparison_mode"] = False
            st.rerun()

    def _create_export_view(self):
        """Create the export and archive view."""
        st.subheader("Export & Archive Results")

        # Export controls
        export_runs = st.session_state.get("export_selected", [])

        if export_runs:
            st.info(f"Selected {len(export_runs)} runs for export")

            col1, col2 = st.columns(2)
            with col1:
                export_format = st.selectbox(
                    "Export Format",
                    options=[f.value for f in ExportFormat],
                    format_func=lambda x: x.upper(),
                )
            with col2:
                include_simulation_data = st.checkbox(
                    "Include Simulation Data", value=True
                )

            if st.button("📥 Export Selected Runs"):
                export_paths = []
                for run_id in export_runs:
                    try:
                        path = self.export_results(
                            run_id=run_id, format=ExportFormat(export_format)
                        )
                        export_paths.append(path)
                    except Exception as e:
                        st.error(f"Failed to export {run_id}: {e}")

                if export_paths:
                    st.success(f"Exported {len(export_paths)} files")
                    for path in export_paths:
                        st.text(f"📁 {path}")

        # Export history
        st.subheader("Export History")
        recent_runs = self.get_recent_results(10)
        if recent_runs:
            selected_run_id = st.selectbox(
                "View export history for run",
                options=[r.run_id for r in recent_runs],
                format_func=lambda x: f"{x[:8]}... ({next(r.scenario_id for r in recent_runs if r.run_id == x)})",
            )

            if selected_run_id:
                history = self.get_export_history(selected_run_id)
                if history:
                    history_df = pd.DataFrame(history)
                    st.dataframe(history_df, use_container_width=True)
                else:
                    st.info("No export history for this run")

    def _show_run_details(self, run_id: str):
        """Show detailed view of a specific run."""
        run = self.load_results(run_id)
        if not run:
            st.error("Run not found")
            return

        st.subheader(f"Run Details: {run_id[:8]}...")

        # Metadata
        with st.expander("📋 Run Metadata", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Scenario ID", run.metadata.scenario_id)
                st.metric("Optimization Type", run.metadata.optimization_type.value)
                st.metric("Engine", run.metadata.optimization_engine.value)
                st.metric("Status", run.metadata.status.value)
            with col2:
                st.metric(
                    "Created", run.metadata.created_at.strftime("%Y-%m-%d %H:%M:%S")
                )
                st.metric(
                    "Runtime",
                    f"{run.metadata.runtime_seconds:.2f}s"
                    if run.metadata.runtime_seconds
                    else "N/A",
                )
                st.metric(
                    "Function Evaluations", run.metadata.function_evaluations or "N/A"
                )
                st.metric(
                    "Converged",
                    "✅ Yes"
                    if run.metadata.converged
                    else "❌ No"
                    if run.metadata.converged is False
                    else "N/A",
                )

        # Results
        with st.expander("🎯 Optimization Results", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    "Objective Value",
                    f"{run.results.objective_value:.6f}"
                    if run.results.objective_value
                    else "N/A",
                )
                st.metric("Risk Level", run.results.risk_level)
            with col2:
                if run.results.objective_breakdown:
                    st.json(run.results.objective_breakdown)

        # Parameters
        with st.expander("⚙️ Optimal Parameters"):
            if run.results.optimal_parameters:
                params_df = pd.DataFrame(
                    [
                        {"Parameter": k, "Value": v}
                        for k, v in run.results.optimal_parameters.items()
                    ]
                )
                st.dataframe(params_df, use_container_width=True)

        # Actions
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📥 Export This Run"):
                st.session_state["export_selected"] = [run_id]
        with col2:
            if st.button("⚖️ Compare With Others"):
                manager_state = st.session_state[self.session_key]
                if run_id not in manager_state["selected_runs"]:
                    manager_state["selected_runs"].append(run_id)
                manager_state["comparison_mode"] = True
        with col3:
            if st.button("🗑️ Delete This Run", type="secondary"):
                if st.confirm("Are you sure? This action cannot be undone."):
                    if self.delete_results(run_id):
                        st.success("Run deleted successfully")
                        del st.session_state["selected_run_details"]
                        st.rerun()
                    else:
                        st.error("Failed to delete run")


# Singleton instance
_results_manager = None


def get_optimization_results_manager() -> OptimizationResultsManager:
    """Get the singleton optimization results manager."""
    global _results_manager
    if _results_manager is None:
        _results_manager = OptimizationResultsManager()
    return _results_manager


# Convenience functions for integration with existing interfaces
def save_scipy_optimization_results(
    scenario_id: str,
    algorithm: str,
    initial_parameters: Dict[str, float],
    optimal_parameters: Dict[str, float],
    objective_weights: Dict[str, float],
    objective_value: float,
    converged: bool,
    function_evaluations: int,
    runtime_seconds: float,
    **kwargs,
) -> str:
    """Save SciPy optimization results."""
    manager = get_optimization_results_manager()
    return manager.save_advanced_optimization_results(
        scenario_id=scenario_id,
        algorithm=algorithm,
        initial_parameters=initial_parameters,
        optimal_parameters=optimal_parameters,
        objective_weights=objective_weights,
        objective_value=objective_value,
        converged=converged,
        function_evaluations=function_evaluations,
        runtime_seconds=runtime_seconds,
        **kwargs,
    )


def save_tuning_optimization_results(
    scenario_id: str,
    parameters: Dict[str, float],
    simulation_results: Dict[str, Any],
    **kwargs,
) -> str:
    """Save compensation tuning results."""
    manager = get_optimization_results_manager()
    return manager.save_compensation_tuning_results(
        scenario_id=scenario_id,
        parameters=parameters,
        simulation_results=simulation_results,
        **kwargs,
    )


def load_latest_optimization_results() -> Optional[OptimizationRun]:
    """Load the most recent optimization results."""
    manager = get_optimization_results_manager()
    recent = manager.get_recent_results(1)
    if recent:
        return manager.load_results(recent[0].run_id)
    return None


if __name__ == "__main__":
    # Example usage for testing
    manager = OptimizationResultsManager()

    # Test advanced optimization save
    run_id = manager.save_advanced_optimization_results(
        scenario_id="test_scenario_001",
        algorithm="SLSQP",
        initial_parameters={"merit_rate_level_1": 0.045, "cola_rate": 0.025},
        optimal_parameters={"merit_rate_level_1": 0.042, "cola_rate": 0.023},
        objective_weights={"cost": 0.4, "equity": 0.3, "targets": 0.3},
        objective_value=0.234567,
        converged=True,
        function_evaluations=87,
        runtime_seconds=45.2,
    )

    print(f"Saved optimization result: {run_id}")

    # Test loading
    loaded_run = manager.load_results(run_id)
    if loaded_run:
        print(f"Loaded run: {loaded_run.metadata.scenario_id}")
        print(f"Objective value: {loaded_run.results.objective_value}")
