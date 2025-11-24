# filename: streamlit_dashboard/optimization_progress.py
"""
Enhanced Progress Tracking and Real-time Visualization for Compensation Optimization
Provides comprehensive monitoring, convergence tracking, and parameter evolution displays.
"""

import json
import pickle
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


@dataclass
class OptimizationProgress:
    """Data structure for tracking optimization progress."""

    iteration: int
    timestamp: datetime
    function_value: float
    constraint_violations: Dict[str, float]
    parameters: Dict[str, float]
    gradient_norm: Optional[float] = None
    step_size: Optional[float] = None
    convergence_criteria: Dict[str, bool] = field(default_factory=dict)
    performance_metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class ProgressTracker:
    """Thread-safe progress tracking for optimization."""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.progress_queue = queue.Queue()
        self.history: deque = deque(maxlen=max_history)
        self.start_time = datetime.now()
        self.current_iteration = 0
        self.is_running = False
        self.lock = threading.Lock()

    def add_progress(self, progress: OptimizationProgress):
        """Thread-safe method to add progress data."""
        with self.lock:
            self.history.append(progress)
            self.current_iteration = progress.iteration
            self.progress_queue.put(progress)

    def get_latest_progress(self) -> List[OptimizationProgress]:
        """Get all progress updates since last call."""
        updates = []
        while not self.progress_queue.empty():
            try:
                updates.append(self.progress_queue.get_nowait())
            except queue.Empty:
                break
        return updates

    def get_history(self) -> List[OptimizationProgress]:
        """Get complete optimization history."""
        with self.lock:
            return list(self.history)


class OptimizationVisualization:
    """Real-time visualization components for optimization progress."""

    def __init__(self):
        self.color_palette = {
            "primary": "#1f77b4",
            "secondary": "#ff7f0e",
            "success": "#2ca02c",
            "warning": "#d62728",
            "info": "#9467bd",
            "background": "#f8f9fa",
        }

    def create_convergence_chart(
        self, history: List[OptimizationProgress], target_value: Optional[float] = None
    ) -> go.Figure:
        """Create real-time convergence tracking chart."""

        if not history:
            # Empty state
            fig = go.Figure()
            fig.add_annotation(
                text="Waiting for optimization to start...",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=16, color="gray"),
            )
            fig.update_layout(
                title="Objective Function Convergence",
                height=400,
                template="plotly_white",
            )
            return fig

        # Extract data
        iterations = [p.iteration for p in history]
        objective_values = [p.function_value for p in history]
        timestamps = [p.timestamp for p in history]

        # Create convergence plot
        fig = go.Figure()

        # Main convergence line
        fig.add_trace(
            go.Scatter(
                x=iterations,
                y=objective_values,
                mode="lines+markers",
                name="Objective Function",
                line=dict(color=self.color_palette["primary"], width=3),
                marker=dict(size=6),
                hovertemplate="<b>Iteration %{x}</b><br>"
                + "Objective: %{y:.6f}<br>"
                + "<extra></extra>",
            )
        )

        # Add target line if provided
        if target_value is not None:
            fig.add_hline(
                y=target_value,
                line_dash="dash",
                line_color=self.color_palette["success"],
                annotation_text=f"Target: {target_value:.4f}",
                annotation_position="top left",
            )

        # Add convergence bands (if we can detect patterns)
        if len(history) > 5:
            recent_values = objective_values[-5:]
            std_dev = np.std(recent_values)
            mean_value = np.mean(recent_values)

            if std_dev < 0.001:  # Converging
                fig.add_hrect(
                    y0=mean_value - std_dev,
                    y1=mean_value + std_dev,
                    fillcolor=self.color_palette["success"],
                    opacity=0.1,
                    annotation_text="Convergence Zone",
                )

        # Update layout
        fig.update_layout(
            title={
                "text": "🎯 Objective Function Convergence",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 18},
            },
            xaxis_title="Iteration",
            yaxis_title="Objective Function Value",
            height=400,
            template="plotly_white",
            showlegend=True,
            hovermode="x unified",
        )

        return fig

    def create_parameter_evolution_chart(
        self,
        history: List[OptimizationProgress],
        selected_params: Optional[List[str]] = None,
    ) -> go.Figure:
        """Create parameter evolution visualization."""

        if not history:
            fig = go.Figure()
            fig.add_annotation(
                text="No parameter data available",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
            )
            return fig

        # Get all parameter names
        all_params = set()
        for p in history:
            all_params.update(p.parameters.keys())

        # Select parameters to display
        if selected_params:
            params_to_show = [p for p in selected_params if p in all_params]
        else:
            # Show top 8 most variable parameters
            param_variances = {}
            for param in all_params:
                values = [p.parameters.get(param, 0) for p in history]
                param_variances[param] = np.var(values) if values else 0

            params_to_show = sorted(
                param_variances.keys(), key=lambda x: param_variances[x], reverse=True
            )[:8]

        if not params_to_show:
            fig = go.Figure()
            fig.add_annotation(text="No parameters to display")
            return fig

        # Create subplots for parameters
        rows = min(4, len(params_to_show))
        cols = 2

        subplot_titles = [
            f"{param.replace('_', ' ').title()}"
            for param in params_to_show[: rows * cols]
        ]

        fig = make_subplots(
            rows=rows,
            cols=cols,
            subplot_titles=subplot_titles,
            vertical_spacing=0.12,
            horizontal_spacing=0.10,
        )

        colors = px.colors.qualitative.Set1

        for i, param in enumerate(params_to_show[: rows * cols]):
            row = (i // cols) + 1
            col = (i % cols) + 1

            # Extract parameter values
            iterations = [p.iteration for p in history]
            values = [p.parameters.get(param, 0) for p in history]

            fig.add_trace(
                go.Scatter(
                    x=iterations,
                    y=values,
                    mode="lines+markers",
                    name=param,
                    line=dict(color=colors[i % len(colors)], width=2),
                    marker=dict(size=4),
                    showlegend=False,
                ),
                row=row,
                col=col,
            )

        fig.update_layout(
            title={
                "text": "📊 Parameter Evolution Over Iterations",
                "x": 0.5,
                "xanchor": "center",
            },
            height=600,
            template="plotly_white",
        )

        return fig

    def create_multi_objective_chart(
        self, history: List[OptimizationProgress], objectives: Dict[str, str]
    ) -> go.Figure:
        """Create multi-objective optimization progress chart."""

        if not history or len(objectives) < 2:
            fig = go.Figure()
            fig.add_annotation(text="Multi-objective data not available")
            return fig

        # Create 3D scatter if we have 3 objectives, otherwise 2D
        obj_keys = list(objectives.keys())[:3]  # Max 3 for visualization

        if len(obj_keys) == 3:
            # 3D scatter plot
            x_vals = [p.performance_metrics.get(obj_keys[0], 0) for p in history]
            y_vals = [p.performance_metrics.get(obj_keys[1], 0) for p in history]
            z_vals = [p.performance_metrics.get(obj_keys[2], 0) for p in history]

            fig = go.Figure(
                data=[
                    go.Scatter3d(
                        x=x_vals,
                        y=y_vals,
                        z=z_vals,
                        mode="markers+lines",
                        marker=dict(
                            size=6,
                            color=[p.iteration for p in history],
                            colorscale="Viridis",
                            showscale=True,
                            colorbar=dict(title="Iteration"),
                        ),
                        line=dict(color="gray", width=2),
                        hovertemplate=f"<b>Iteration %{{text}}</b><br>"
                        + f"{objectives[obj_keys[0]]}: %{{x:.4f}}<br>"
                        + f"{objectives[obj_keys[1]]}: %{{y:.4f}}<br>"
                        + f"{objectives[obj_keys[2]]}: %{{z:.4f}}<br>"
                        + "<extra></extra>",
                        text=[p.iteration for p in history],
                    )
                ]
            )

            fig.update_layout(
                title="🎯 Multi-Objective Optimization Progress (3D)",
                scene=dict(
                    xaxis_title=objectives[obj_keys[0]],
                    yaxis_title=objectives[obj_keys[1]],
                    zaxis_title=objectives[obj_keys[2]],
                ),
                height=500,
            )

        else:
            # 2D scatter plot
            x_vals = [p.performance_metrics.get(obj_keys[0], 0) for p in history]
            y_vals = [p.performance_metrics.get(obj_keys[1], 0) for p in history]

            fig = go.Figure(
                data=[
                    go.Scatter(
                        x=x_vals,
                        y=y_vals,
                        mode="markers+lines",
                        marker=dict(
                            size=8,
                            color=[p.iteration for p in history],
                            colorscale="Viridis",
                            showscale=True,
                            colorbar=dict(title="Iteration"),
                        ),
                        line=dict(color="gray", width=2),
                        hovertemplate=f"<b>Iteration %{{text}}</b><br>"
                        + f"{objectives[obj_keys[0]]}: %{{x:.4f}}<br>"
                        + f"{objectives[obj_keys[1]]}: %{{y:.4f}}<br>"
                        + "<extra></extra>",
                        text=[p.iteration for p in history],
                    )
                ]
            )

            fig.update_layout(
                title="🎯 Multi-Objective Optimization Progress",
                xaxis_title=objectives[obj_keys[0]],
                yaxis_title=objectives[obj_keys[1]],
                height=400,
            )

        fig.update_layout(template="plotly_white")
        return fig

    def create_constraint_violation_chart(
        self, history: List[OptimizationProgress]
    ) -> go.Figure:
        """Create constraint violation tracking chart."""

        if not history:
            fig = go.Figure()
            fig.add_annotation(text="No constraint data available")
            return fig

        # Get all constraint names
        all_constraints = set()
        for p in history:
            all_constraints.update(p.constraint_violations.keys())

        if not all_constraints:
            fig = go.Figure()
            fig.add_annotation(text="No constraint violations tracked")
            return fig

        fig = go.Figure()

        colors = px.colors.qualitative.Set1

        for i, constraint in enumerate(all_constraints):
            iterations = [p.iteration for p in history]
            violations = [p.constraint_violations.get(constraint, 0) for p in history]

            fig.add_trace(
                go.Scatter(
                    x=iterations,
                    y=violations,
                    mode="lines+markers",
                    name=constraint.replace("_", " ").title(),
                    line=dict(color=colors[i % len(colors)], width=2),
                    marker=dict(size=4),
                )
            )

        # Add feasibility line
        fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="green",
            annotation_text="Feasible Region",
            annotation_position="top left",
        )

        fig.update_layout(
            title="⚖️ Constraint Violations Over Iterations",
            xaxis_title="Iteration",
            yaxis_title="Constraint Violation",
            height=400,
            template="plotly_white",
            showlegend=True,
        )

        return fig

    def create_performance_dashboard(
        self, history: List[OptimizationProgress], start_time: datetime
    ) -> Dict[str, Any]:
        """Create performance metrics dashboard."""

        if not history:
            return {
                "current_iteration": 0,
                "elapsed_time": "00:00:00",
                "iterations_per_minute": 0,
                "estimated_completion": "Unknown",
                "convergence_rate": "Unknown",
            }

        current_time = datetime.now()
        elapsed = current_time - start_time

        # Calculate metrics
        current_iteration = history[-1].iteration
        elapsed_seconds = elapsed.total_seconds()
        iterations_per_minute = (
            (current_iteration / elapsed_seconds * 60) if elapsed_seconds > 0 else 0
        )

        # Estimate completion time
        if len(history) > 5:
            recent_rate = len(history[-5:]) / 5  # Recent iteration rate
            estimated_total_iterations = current_iteration * 1.5  # Rough estimate
            remaining_iterations = max(
                0, estimated_total_iterations - current_iteration
            )
            estimated_seconds = (
                remaining_iterations / recent_rate if recent_rate > 0 else 0
            )
            estimated_completion = current_time + timedelta(seconds=estimated_seconds)
            est_completion_str = estimated_completion.strftime("%H:%M:%S")
        else:
            est_completion_str = "Calculating..."

        # Calculate convergence rate
        if len(history) > 10:
            recent_values = [p.function_value for p in history[-10:]]
            convergence_rate = abs(recent_values[-1] - recent_values[0]) / len(
                recent_values
            )
            conv_rate_str = f"{convergence_rate:.2e}"
        else:
            conv_rate_str = "Calculating..."

        return {
            "current_iteration": current_iteration,
            "elapsed_time": str(elapsed).split(".")[0],  # Remove microseconds
            "iterations_per_minute": f"{iterations_per_minute:.1f}",
            "estimated_completion": est_completion_str,
            "convergence_rate": conv_rate_str,
        }


class OptimizationLogFilter:
    """Filter and display optimization log events."""

    def __init__(self):
        self.log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        self.event_types = [
            "ITERATION_START",
            "OBJECTIVE_EVALUATION",
            "CONSTRAINT_CHECK",
            "PARAMETER_UPDATE",
            "CONVERGENCE_CHECK",
            "ALGORITHM_STATUS",
        ]

    def filter_logs(
        self,
        logs: List[Dict],
        level_filter: List[str] = None,
        event_filter: List[str] = None,
        search_term: str = None,
    ) -> List[Dict]:
        """Filter optimization logs based on criteria."""

        filtered = logs

        if level_filter:
            filtered = [log for log in filtered if log.get("level") in level_filter]

        if event_filter:
            filtered = [
                log for log in filtered if log.get("event_type") in event_filter
            ]

        if search_term:
            search_lower = search_term.lower()
            filtered = [
                log
                for log in filtered
                if search_lower in log.get("message", "").lower()
            ]

        return filtered

    def display_logs(self, logs: List[Dict], max_entries: int = 100):
        """Display filtered logs in Streamlit."""

        if not logs:
            st.info("No log entries match the current filters.")
            return

        # Limit number of displayed logs
        display_logs = logs[-max_entries:] if len(logs) > max_entries else logs

        log_container = st.container()

        with log_container:
            for log_entry in reversed(display_logs):  # Most recent first
                timestamp = log_entry.get("timestamp", "")
                level = log_entry.get("level", "INFO")
                message = log_entry.get("message", "")
                event_type = log_entry.get("event_type", "")

                # Style based on log level
                if level == "ERROR":
                    st.error(f"🔴 {timestamp} | {event_type} | {message}")
                elif level == "WARNING":
                    st.warning(f"🟡 {timestamp} | {event_type} | {message}")
                elif level == "INFO":
                    st.info(f"🔵 {timestamp} | {event_type} | {message}")
                else:
                    st.text(f"⚪ {timestamp} | {event_type} | {message}")


def create_optimization_progress_interface():
    """Create the complete optimization progress tracking interface."""

    st.markdown("## 🔄 Real-time Optimization Progress")

    # Initialize components
    if "progress_tracker" not in st.session_state:
        st.session_state.progress_tracker = ProgressTracker()

    if "optimization_viz" not in st.session_state:
        st.session_state.optimization_viz = OptimizationVisualization()

    if "log_filter" not in st.session_state:
        st.session_state.log_filter = OptimizationLogFilter()

    # Check for optimization results from temporary file (Dagster integration)
    temp_result_path = "/tmp/planalign_optimization_result.pkl"
    optimization_running = Path(temp_result_path).exists()

    # Progress indicators
    col1, col2, col3, col4 = st.columns(4)

    # Load or simulate progress data
    if optimization_running:
        try:
            with open(temp_result_path, "rb") as f:
                result_data = pickle.load(f)

            # Convert result data to progress history if available
            if "optimization_history" in result_data:
                history = []
                for i, entry in enumerate(result_data["optimization_history"]):
                    progress = OptimizationProgress(
                        iteration=i,
                        timestamp=datetime.now()
                        - timedelta(
                            seconds=(len(result_data["optimization_history"]) - i) * 30
                        ),
                        function_value=entry.get("objective_value", 0),
                        constraint_violations=entry.get("constraints", {}),
                        parameters=entry.get("parameters", {}),
                        performance_metrics=entry.get("metrics", {}),
                    )
                    history.append(progress)
            else:
                history = []

        except Exception as e:
            st.error(f"Error loading optimization progress: {e}")
            history = []
    else:
        # Demo data for development
        history = generate_demo_progress_data()

    # Performance dashboard
    if history:
        perf_metrics = st.session_state.optimization_viz.create_performance_dashboard(
            history, datetime.now() - timedelta(minutes=5)
        )

        with col1:
            st.metric("Current Iteration", perf_metrics["current_iteration"])
        with col2:
            st.metric("Elapsed Time", perf_metrics["elapsed_time"])
        with col3:
            st.metric("Iterations/Min", perf_metrics["iterations_per_minute"])
        with col4:
            st.metric("Est. Completion", perf_metrics["estimated_completion"])

    # Main visualization tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "🎯 Convergence",
            "📊 Parameters",
            "⚖️ Constraints",
            "🎭 Multi-Objective",
            "📋 Logs",
        ]
    )

    with tab1:
        st.markdown("### Objective Function Convergence")
        convergence_fig = st.session_state.optimization_viz.create_convergence_chart(
            history, target_value=None
        )
        st.plotly_chart(convergence_fig, use_container_width=True)

        if history:
            # Convergence analysis
            recent_values = [p.function_value for p in history[-10:]]
            if len(recent_values) > 5:
                improvement = recent_values[0] - recent_values[-1]
                if improvement > 0.001:
                    st.success(
                        f"✅ Function improving: {improvement:.6f} over last 10 iterations"
                    )
                elif abs(improvement) < 0.001:
                    st.info("➡️ Function stable: converging")
                else:
                    st.warning("⚠️ Function degrading: may need algorithm adjustment")

    with tab2:
        st.markdown("### Parameter Evolution")

        # Parameter selection
        if history and history[-1].parameters:
            all_params = list(history[-1].parameters.keys())
            selected_params = st.multiselect(
                "Select parameters to display:",
                all_params,
                default=all_params[:6],  # Show first 6 by default
            )
        else:
            selected_params = []

        param_fig = st.session_state.optimization_viz.create_parameter_evolution_chart(
            history, selected_params
        )
        st.plotly_chart(param_fig, use_container_width=True)

        # Parameter statistics
        if history and selected_params:
            st.markdown("#### Parameter Statistics")
            param_stats = []

            for param in selected_params:
                values = [p.parameters.get(param, 0) for p in history]
                param_stats.append(
                    {
                        "Parameter": param.replace("_", " ").title(),
                        "Current": f"{values[-1]:.4f}" if values else "N/A",
                        "Min": f"{min(values):.4f}" if values else "N/A",
                        "Max": f"{max(values):.4f}" if values else "N/A",
                        "Std Dev": f"{np.std(values):.4f}" if values else "N/A",
                    }
                )

            st.dataframe(pd.DataFrame(param_stats), use_container_width=True)

    with tab3:
        st.markdown("### Constraint Violations")
        constraint_fig = (
            st.session_state.optimization_viz.create_constraint_violation_chart(history)
        )
        st.plotly_chart(constraint_fig, use_container_width=True)

        # Constraint status
        if history and history[-1].constraint_violations:
            st.markdown("#### Current Constraint Status")
            constraints = history[-1].constraint_violations

            for constraint, violation in constraints.items():
                if abs(violation) < 1e-6:
                    st.success(f"✅ {constraint.replace('_', ' ').title()}: Satisfied")
                else:
                    st.error(
                        f"❌ {constraint.replace('_', ' ').title()}: Violation = {violation:.6f}"
                    )

    with tab4:
        st.markdown("### Multi-Objective Progress")

        # Define objectives for demo
        objectives = {
            "cost_efficiency": "Cost Efficiency",
            "equity_score": "Equity Score",
            "target_achievement": "Target Achievement",
        }

        multi_obj_fig = st.session_state.optimization_viz.create_multi_objective_chart(
            history, objectives
        )
        st.plotly_chart(multi_obj_fig, use_container_width=True)

        # Pareto frontier analysis
        if len(history) > 10:
            st.markdown("#### Pareto Frontier Analysis")
            st.info("🔍 Analyzing trade-offs between competing objectives...")

            # Simple Pareto analysis placeholder
            pareto_data = []
            for p in history[-20:]:  # Last 20 iterations
                if p.performance_metrics:
                    pareto_data.append(
                        {
                            "Iteration": p.iteration,
                            "Cost": p.performance_metrics.get("cost_efficiency", 0),
                            "Equity": p.performance_metrics.get("equity_score", 0),
                            "Targets": p.performance_metrics.get(
                                "target_achievement", 0
                            ),
                        }
                    )

            if pareto_data:
                st.dataframe(pd.DataFrame(pareto_data), use_container_width=True)

    with tab5:
        st.markdown("### Optimization Logs")

        # Log filtering controls
        col1, col2, col3 = st.columns(3)

        with col1:
            level_filter = st.multiselect(
                "Log Levels:",
                st.session_state.log_filter.log_levels,
                default=["INFO", "WARNING", "ERROR"],
            )

        with col2:
            event_filter = st.multiselect(
                "Event Types:",
                st.session_state.log_filter.event_types,
                default=st.session_state.log_filter.event_types,
            )

        with col3:
            search_term = st.text_input(
                "Search logs:", placeholder="Enter search term..."
            )

        # Generate demo logs
        demo_logs = generate_demo_logs()

        # Filter and display logs
        filtered_logs = st.session_state.log_filter.filter_logs(
            demo_logs, level_filter, event_filter, search_term
        )

        st.session_state.log_filter.display_logs(filtered_logs)

    # Auto-refresh control
    if optimization_running:
        auto_refresh = st.checkbox("Auto-refresh (10 seconds)", value=True)
        if auto_refresh:
            time.sleep(10)
            st.rerun()


def generate_demo_progress_data() -> List[OptimizationProgress]:
    """Generate demo progress data for testing visualization."""

    history = []
    np.random.seed(42)

    # Simulate optimization progress
    for i in range(50):
        # Decreasing objective function with noise
        base_value = 100 * np.exp(-i / 20) + np.random.normal(0, 1)

        # Random parameters with trends
        parameters = {
            "merit_rate_level_1": 0.045
            + 0.01 * np.sin(i / 10)
            + np.random.normal(0, 0.001),
            "cola_rate": 0.025 + 0.005 * np.cos(i / 8) + np.random.normal(0, 0.0005),
            "new_hire_salary_adjustment": 1.15
            + 0.05 * np.sin(i / 15)
            + np.random.normal(0, 0.01),
            "promotion_probability_level_1": 0.12
            + 0.02 * np.cos(i / 12)
            + np.random.normal(0, 0.005),
        }

        # Constraint violations (decreasing over time)
        constraints = {
            "budget_constraint": max(0, 10 - i / 5 + np.random.normal(0, 1)),
            "equity_constraint": max(0, 5 - i / 10 + np.random.normal(0, 0.5)),
        }

        # Performance metrics
        metrics = {
            "cost_efficiency": np.random.uniform(0.6, 0.9),
            "equity_score": np.random.uniform(0.5, 0.85),
            "target_achievement": np.random.uniform(0.7, 0.95),
        }

        progress = OptimizationProgress(
            iteration=i,
            timestamp=datetime.now() - timedelta(seconds=(50 - i) * 30),
            function_value=base_value,
            constraint_violations=constraints,
            parameters=parameters,
            gradient_norm=np.random.uniform(0.1, 2.0),
            step_size=np.random.uniform(0.001, 0.1),
            performance_metrics=metrics,
        )

        history.append(progress)

    return history


def generate_demo_logs() -> List[Dict]:
    """Generate demo log entries for testing."""

    logs = []
    event_types = [
        "ITERATION_START",
        "OBJECTIVE_EVALUATION",
        "CONSTRAINT_CHECK",
        "PARAMETER_UPDATE",
        "CONVERGENCE_CHECK",
        "ALGORITHM_STATUS",
    ]

    levels = ["INFO", "WARNING", "ERROR", "DEBUG"]

    for i in range(100):
        log_entry = {
            "timestamp": (datetime.now() - timedelta(seconds=i * 30)).strftime(
                "%H:%M:%S"
            ),
            "level": np.random.choice(levels, p=[0.6, 0.2, 0.1, 0.1]),
            "event_type": np.random.choice(event_types),
            "message": f"Optimization step {100-i}: Processing parameter adjustments and constraint validation",
        }
        logs.append(log_entry)

    # Add some specific meaningful logs
    logs.extend(
        [
            {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "level": "INFO",
                "event_type": "CONVERGENCE_CHECK",
                "message": "Convergence criteria met: gradient norm < 1e-6",
            },
            {
                "timestamp": (datetime.now() - timedelta(seconds=60)).strftime(
                    "%H:%M:%S"
                ),
                "level": "WARNING",
                "event_type": "CONSTRAINT_CHECK",
                "message": "Budget constraint approaching violation: 95% of limit reached",
            },
        ]
    )

    return logs


if __name__ == "__main__":
    # For testing the visualization components
    st.set_page_config(page_title="Optimization Progress", layout="wide")
    create_optimization_progress_interface()
