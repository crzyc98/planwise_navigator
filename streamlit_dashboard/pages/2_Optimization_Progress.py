# filename: streamlit_dashboard/pages/4_🔄_Optimization_Progress.py
"""
Dedicated Optimization Progress Monitoring Page
Real-time visualization and tracking of compensation optimization runs.
"""

import datetime
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

# Page configuration
st.set_page_config(
    page_title="Optimization Progress - PlanWise Navigator",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for enhanced visualization
st.markdown(
    """
<style>
    .optimization-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2rem;
        border-radius: 1rem;
        margin-bottom: 2rem;
        text-align: center;
    }

    .progress-card {
        background: #f8f9fa;
        border-left: 4px solid #007bff;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }

    .convergence-indicator {
        font-size: 1.2rem;
        font-weight: bold;
        padding: 0.5rem 1rem;
        border-radius: 2rem;
        display: inline-block;
        margin: 0.5rem;
    }

    .converged {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }

    .optimizing {
        background-color: #fff3cd;
        color: #856404;
        border: 1px solid #ffeaa7;
    }

    .failed {
        background-color: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }

    .metric-highlight {
        font-size: 2rem;
        font-weight: bold;
        color: #007bff;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Header
st.markdown(
    """
<div class="optimization-header">
    <h1>🔄 Optimization Progress Monitor</h1>
    <p>Real-time tracking and visualization of compensation parameter optimization</p>
</div>
""",
    unsafe_allow_html=True,
)


# Function definitions first
def create_demo_progress_interface(tracker, visualizer):
    """Create demonstration progress interface with sample data."""

    history = tracker.get_history()

    if not history:
        st.warning("No demo data available")
        return

    # Performance dashboard
    st.markdown("## 📈 Performance Metrics")

    perf_metrics = visualizer.create_performance_dashboard(history, tracker.start_time)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f'<div class="metric-highlight">{perf_metrics["current_iteration"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("**Current Iteration**")

    with col2:
        st.markdown(
            f'<div class="metric-highlight">{perf_metrics["elapsed_time"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("**Elapsed Time**")

    with col3:
        st.markdown(
            f'<div class="metric-highlight">{perf_metrics["iterations_per_minute"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("**Iterations/Min**")

    with col4:
        st.markdown(
            f'<div class="metric-highlight">{perf_metrics["convergence_rate"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("**Convergence Rate**")

    # Visualization tabs
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "🎯 Convergence Analysis",
            "📊 Parameter Evolution",
            "⚖️ Constraint Monitoring",
            "📋 Event Logs",
        ]
    )

    with tab1:
        st.markdown("### Objective Function Convergence")

        convergence_fig = visualizer.create_convergence_chart(history, target_value=0.1)
        st.plotly_chart(convergence_fig, use_container_width=True)

        # Convergence statistics
        if len(history) > 10:
            recent_values = [p.function_value for p in history[-10:]]
            improvement = recent_values[0] - recent_values[-1]

            col1, col2 = st.columns(2)
            with col1:
                st.markdown('<div class="progress-card">', unsafe_allow_html=True)
                st.markdown("**Convergence Analysis**")
                if improvement > 0.001:
                    st.success(
                        f"✅ Improving: {improvement:.6f} over last 10 iterations"
                    )
                elif abs(improvement) < 0.001:
                    st.info("➡️ Stable: Function converging")
                else:
                    st.warning("⚠️ Degrading: Algorithm may need adjustment")
                st.markdown("</div>", unsafe_allow_html=True)

            with col2:
                st.markdown('<div class="progress-card">', unsafe_allow_html=True)
                st.markdown("**Current Performance**")
                st.metric(
                    "Best Value", f"{min([p.function_value for p in history]):.6f}"
                )
                st.metric("Current Value", f"{history[-1].function_value:.6f}")
                st.metric("Iterations", len(history))
                st.markdown("</div>", unsafe_allow_html=True)

    with tab2:
        st.markdown("### Parameter Evolution")

        # Parameter selection
        all_params = list(history[-1].parameters.keys())
        selected_params = st.multiselect(
            "Select parameters to display:", all_params, default=all_params[:4]
        )

        param_fig = visualizer.create_parameter_evolution_chart(
            history, selected_params
        )
        st.plotly_chart(param_fig, use_container_width=True)

        # Parameter statistics
        if selected_params:
            st.markdown("### Parameter Statistics")

            param_stats = []
            for param in selected_params:
                values = [p.parameters.get(param, 0) for p in history]
                param_stats.append(
                    {
                        "Parameter": param.replace("_", " ").title(),
                        "Current": f"{values[-1]:.4f}",
                        "Min": f"{min(values):.4f}",
                        "Max": f"{max(values):.4f}",
                        "Range": f"{max(values) - min(values):.4f}",
                        "Std Dev": f"{np.std(values):.4f}",
                    }
                )

            st.dataframe(pd.DataFrame(param_stats), use_container_width=True)

    with tab3:
        st.markdown("### Constraint Violations")

        constraint_fig = visualizer.create_constraint_violation_chart(history)
        st.plotly_chart(constraint_fig, use_container_width=True)

        # Current constraint status
        if history[-1].constraint_violations:
            st.markdown("### Current Constraint Status")

            for constraint, violation in history[-1].constraint_violations.items():
                col1, col2 = st.columns([3, 1])

                with col1:
                    constraint_name = constraint.replace("_", " ").title()

                with col2:
                    if abs(violation) < 1e-6:
                        st.success("✅ Satisfied")
                    else:
                        st.error(f"❌ {violation:.6f}")

                st.markdown(f"**{constraint_name}**")

                # Progress bar for violation magnitude
                if violation > 0:
                    progress_val = min(violation / 10, 1.0)  # Normalize to max 10
                    st.progress(progress_val)

    with tab4:
        st.markdown("### Optimization Event Logs")

        # Generate and display demo logs
        demo_logs = generate_demo_logs()

        # Log filtering
        col1, col2, col3 = st.columns(3)

        with col1:
            level_filter = st.multiselect(
                "Log Levels:",
                ["DEBUG", "INFO", "WARNING", "ERROR"],
                default=["INFO", "WARNING", "ERROR"],
            )

        with col2:
            event_filter = st.multiselect(
                "Event Types:",
                [
                    "ITERATION_START",
                    "OBJECTIVE_EVALUATION",
                    "CONSTRAINT_CHECK",
                    "PARAMETER_UPDATE",
                ],
                default=["ITERATION_START", "OBJECTIVE_EVALUATION", "CONSTRAINT_CHECK"],
            )

        with col3:
            search_term = st.text_input("Search:", placeholder="Filter logs...")

        # Filter logs
        filtered_logs = demo_logs
        if level_filter:
            filtered_logs = [
                log for log in filtered_logs if log.get("level") in level_filter
            ]
        if event_filter:
            filtered_logs = [
                log for log in filtered_logs if log.get("event_type") in event_filter
            ]
        if search_term:
            search_lower = search_term.lower()
            filtered_logs = [
                log
                for log in filtered_logs
                if search_lower in log.get("message", "").lower()
            ]

        # Display logs
        st.markdown("### Recent Log Entries")

        for log in filtered_logs[-20:]:  # Show last 20 entries
            timestamp = log.get("timestamp", "")
            level = log.get("level", "INFO")
            event_type = log.get("event_type", "")
            message = log.get("message", "")

            if level == "ERROR":
                st.error(f"🔴 {timestamp} | {event_type} | {message}")
            elif level == "WARNING":
                st.warning(f"🟡 {timestamp} | {event_type} | {message}")
            elif level == "INFO":
                st.info(f"🔵 {timestamp} | {event_type} | {message}")
            else:
                st.text(f"⚪ {timestamp} | {event_type} | {message}")


# Import the optimization progress components
try:
    from optimization_progress import (OptimizationLogFilter,
                                       OptimizationProgress,
                                       OptimizationVisualization,
                                       ProgressTracker,
                                       create_optimization_progress_interface,
                                       generate_demo_logs,
                                       generate_demo_progress_data)

    progress_available = True
except ImportError as e:
    st.error(f"❌ Could not import optimization progress components: {e}")
    st.info(
        "💡 Make sure optimization_progress.py is in the streamlit_dashboard directory"
    )
    progress_available = False

if progress_available:
    # Check for active optimization
    temp_result_path = Path("/tmp/planwise_optimization_result.pkl")
    temp_config_path = Path("/tmp/planwise_optimization_config.yaml")

    optimization_status = "Unknown"
    if temp_result_path.exists():
        try:
            import pickle

            with open(temp_result_path, "rb") as f:
                result_data = pickle.load(f)

            if result_data.get("optimization_failed", False):
                optimization_status = "Failed"
            elif result_data.get("converged", False):
                optimization_status = "Converged"
            else:
                optimization_status = "Running"
        except Exception as e:
            optimization_status = f"Error: {e}"
    else:
        optimization_status = "No Active Run"

    # Status indicator
    st.markdown("## 📊 Current Status")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if optimization_status == "Converged":
            st.markdown(
                '<span class="convergence-indicator converged">✅ Converged</span>',
                unsafe_allow_html=True,
            )
        elif optimization_status == "Running":
            st.markdown(
                '<span class="convergence-indicator optimizing">🔄 Optimizing</span>',
                unsafe_allow_html=True,
            )
        elif optimization_status == "Failed":
            st.markdown(
                '<span class="convergence-indicator failed">❌ Failed</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="convergence-indicator">⚪ Idle</span>',
                unsafe_allow_html=True,
            )

    with col2:
        st.metric("Status", optimization_status)

    with col3:
        if temp_result_path.exists():
            modified_time = temp_result_path.stat().st_mtime
            import datetime

            last_update = datetime.datetime.fromtimestamp(modified_time).strftime(
                "%H:%M:%S"
            )
            st.metric("Last Update", last_update)
        else:
            st.metric("Last Update", "N/A")

    with col4:
        if temp_config_path.exists():
            st.metric("Config Available", "✅ Yes")
        else:
            st.metric("Config Available", "❌ No")

    # Main progress interface
    st.markdown("---")

    # Control buttons
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("🔄 Refresh Data", type="primary"):
            st.rerun()

    with col2:
        if st.button("🧹 Clear Cache"):
            # Clear Streamlit cache
            st.cache_data.clear()
            st.success("Cache cleared!")

    with col3:
        auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)

    with col4:
        show_demo = st.checkbox(
            "Show Demo Data", value=optimization_status == "No Active Run"
        )

    # Create the main progress interface
    if show_demo or optimization_status == "No Active Run":
        st.info(
            "📊 Showing demonstration data. Start an optimization from the Compensation Tuning page to see real progress."
        )

        # Initialize demo components
        if "demo_tracker" not in st.session_state:
            st.session_state.demo_tracker = ProgressTracker()
            st.session_state.demo_viz = OptimizationVisualization()

            # Load demo data
            demo_history = generate_demo_progress_data()
            for progress in demo_history:
                st.session_state.demo_tracker.add_progress(progress)

        # Display demo interface
        create_demo_progress_interface(
            st.session_state.demo_tracker, st.session_state.demo_viz
        )
    else:
        # Show real optimization progress
        create_optimization_progress_interface()

    # Auto-refresh functionality
    if auto_refresh and optimization_status in ["Running", "Optimizing"]:
        import time

        time.sleep(30)
        st.rerun()

else:
    # Fallback interface if progress module not available
    st.warning("⚠️ Advanced progress tracking not available")

    st.markdown("## 📁 Manual Progress Checking")

    # Basic file-based progress checking
    temp_files = [
        "/tmp/planwise_optimization_result.pkl",
        "/tmp/planwise_optimization_config.yaml",
        "/tmp/dagster_optimization_logs.txt",
    ]

    for file_path in temp_files:
        file_exists = Path(file_path).exists()
        if file_exists:
            file_size = Path(file_path).stat().st_size
            modified_time = Path(file_path).stat().st_mtime
            import datetime

            mod_time_str = datetime.datetime.fromtimestamp(modified_time).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            st.success(f"✅ {file_path} - {file_size} bytes - Modified: {mod_time_str}")
        else:
            st.info(f"ℹ️ {file_path} - Not found")

# Footer
st.markdown("---")
st.markdown(
    """
<div style='text-align: center; color: #666; padding: 2rem;'>
    <h4>🔄 Optimization Progress Monitor</h4>
    <p>Real-time tracking for PlanWise Navigator compensation optimization</p>
    <p><small>Last updated: {}</small></p>
</div>
""".format(
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ),
    unsafe_allow_html=True,
)
