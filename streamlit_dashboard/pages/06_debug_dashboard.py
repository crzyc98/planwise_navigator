"""
Streamlit Debug Dashboard for Fidelity PlanAlign Engine
Story S071-06: Interactive web UI for all debugging utilities
"""

import streamlit as st
from pathlib import Path
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from planalign_orchestrator.debug_utils import (
    DatabaseInspector,
    StateVisualizer,
    DependencyAnalyzer,
)
from planalign_orchestrator.config import get_database_path
import pandas as pd

st.set_page_config(page_title="Debug Dashboard", page_icon="🐛", layout="wide")

st.title("🐛 PlanWise Debug Dashboard")

# Sidebar navigation
debug_mode = st.sidebar.selectbox(
    "Debug Mode",
    [
        "Database Inspector",
        "State Visualizer",
        "Dependency Analyzer",
        "Performance Traces",
    ],
)

# Database Inspector
if debug_mode == "Database Inspector":
    st.header("Database Inspector")

    try:
        with DatabaseInspector() as inspector:
            # Quick stats
            st.subheader("Quick Statistics")
            stats = inspector.quick_stats()

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Events", f"{stats['total_events']:,}")
            col2.metric("Total Years", stats["total_years"])
            col3.metric("Unique Employees", f"{stats['unique_employees']:,}")
            col4.metric("Net Workforce Change", f"{stats['net_workforce_change']:+,}")

            # Event breakdown
            st.subheader("Event Type Breakdown")
            event_df = pd.DataFrame(
                [
                    {"Event Type": k.title(), "Count": v}
                    for k, v in stats["event_counts"].items()
                ]
            )
            st.bar_chart(event_df.set_index("Event Type"))

            # Year-specific inspection
            st.subheader("Year Inspection")

            if stats["year_range"]:
                year = st.slider(
                    "Select Year",
                    min_value=stats["year_range"][0],
                    max_value=stats["year_range"][1],
                    value=stats["year_range"][0],
                )

                snapshot = inspector.get_year_snapshot(year)

                col1, col2, col3 = st.columns(3)
                col1.metric("Workforce Count", f"{snapshot.workforce_count:,}")
                col2.metric("Average Salary", f"${snapshot.avg_salary:,.0f}")
                col3.metric(
                    "Total Compensation", f"${snapshot.total_compensation_cost:,.0f}"
                )

                st.subheader("Events")
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Hires", snapshot.hire_events)
                col2.metric("Terminations", snapshot.termination_events)
                col3.metric("Promotions", snapshot.promotion_events)
                col4.metric("Raises", snapshot.raise_events)
                col5.metric("Enrollments", snapshot.enrollment_events)

                # Data quality issues
                if snapshot.data_quality_issues:
                    st.subheader("⚠️ Data Quality Issues")
                    for issue in snapshot.data_quality_issues:
                        st.warning(issue)
                else:
                    st.success("✓ No data quality issues detected")

            # Employee timeline search
            st.subheader("Employee Timeline Search")
            employee_id = st.text_input("Employee ID")

            if employee_id:
                try:
                    timeline = inspector.event_timeline(employee_id)
                    if not timeline.empty:
                        st.dataframe(timeline, use_container_width=True)
                    else:
                        st.info(f"No events found for employee {employee_id}")
                except Exception as e:
                    st.error(f"Error: {e}")

    except Exception as e:
        st.error(f"Database connection error: {e}")
        st.info(
            "Make sure the simulation database exists and is accessible. "
            "Run a simulation first if needed."
        )

# State Visualizer
elif debug_mode == "State Visualizer":
    st.header("State Visualizer")

    checkpoint_dir = Path("checkpoints")

    if not checkpoint_dir.exists():
        st.warning("No checkpoints directory found")
        st.info(
            "Checkpoints are created during multi-year simulations. "
            "Run a simulation with checkpointing enabled to see data here."
        )
    else:
        visualizer = StateVisualizer(checkpoint_dir)
        checkpoints = visualizer.list_checkpoints()

        if not checkpoints:
            st.info("No checkpoints available")
            st.info("Run a multi-year simulation to generate checkpoints.")
        else:
            # Checkpoint summary table
            st.subheader("Checkpoint Summary")

            checkpoint_data = [
                {
                    "Year": cp.year,
                    "Stage": cp.stage,
                    "Timestamp": cp.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "Duration": f"{cp.duration_seconds:.1f}s",
                    "Status": "✓ Success" if cp.success else f"✗ Failed: {cp.error}",
                }
                for cp in checkpoints
            ]
            st.dataframe(pd.DataFrame(checkpoint_data), use_container_width=True)

            # Registry state comparison
            st.subheader("Registry State Comparison")

            years = sorted(set(cp.year for cp in checkpoints))
            if len(years) >= 2:
                col1, col2 = st.columns(2)
                year1 = col1.selectbox("Year 1", years, index=0)
                year2 = col2.selectbox("Year 2", years, index=min(1, len(years) - 1))

                if st.button("Compare"):
                    try:
                        diff = visualizer.compare_years(year1, year2)

                        for registry_name, changes in diff.items():
                            st.subheader(registry_name.replace("_", " ").title())

                            col1, col2, col3 = st.columns(3)
                            col1.metric(f"Year {year1} Count", changes["year1_count"])
                            col2.metric(f"Year {year2} Count", changes["year2_count"])
                            col3.metric(
                                "Net Change",
                                changes["year2_count"] - changes["year1_count"],
                            )

                            st.write(f"Added: {len(changes['added'])} employees")
                            st.write(f"Removed: {len(changes['removed'])} employees")
                    except Exception as e:
                        st.error(f"Error comparing years: {e}")

# Dependency Analyzer
elif debug_mode == "Dependency Analyzer":
    st.header("Dependency Analyzer")

    dbt_dir = Path("dbt")

    if not dbt_dir.exists():
        st.error("dbt directory not found")
    else:
        analyzer = DependencyAnalyzer(dbt_dir)

        with st.spinner("Building dependency graph..."):
            analyzer.build_dependency_graph()

        st.subheader("Dependency Statistics")
        col1, col2 = st.columns(2)
        col1.metric("Total Models", analyzer.graph.number_of_nodes())
        col2.metric("Total Dependencies", analyzer.graph.number_of_edges())

        # Circular dependencies
        cycles = analyzer.find_circular_dependencies()
        if cycles:
            st.error(f"⚠️ Found {len(cycles)} circular dependencies")
            for i, cycle in enumerate(cycles, 1):
                st.write(f"{i}. {' → '.join(cycle + [cycle[0]])}")
        else:
            st.success("✓ No circular dependencies detected")

        # Critical path
        critical_path = analyzer.get_critical_path()
        if critical_path:
            st.subheader(f"Critical Path ({len(critical_path)} models)")
            st.write(" → ".join(critical_path))

        # Most depended-upon models
        st.subheader("Most Depended-Upon Models")
        in_degrees = [
            (node, analyzer.graph.in_degree(node)) for node in analyzer.graph.nodes()
        ]
        top_dependencies = sorted(in_degrees, key=lambda x: x[1], reverse=True)[:10]

        dep_df = pd.DataFrame(
            [
                {"Model": model, "Downstream Dependencies": degree}
                for model, degree in top_dependencies
            ]
        )
        st.dataframe(dep_df, use_container_width=True)

        # Generate graph
        if st.button("Generate Dependency Graph"):
            output_file = Path("dependency_graph.png")
            with st.spinner("Generating graph..."):
                analyzer.visualize_graph(output_file)
            st.success(f"Graph saved to {output_file}")
            st.image(str(output_file))

# Performance Traces
elif debug_mode == "Performance Traces":
    st.header("Performance Traces")

    # Look for recent trace files
    trace_files = list(Path(".").glob("performance_trace_*.json"))

    if not trace_files:
        st.info(
            "No performance trace files found. Run a simulation to generate traces."
        )
        st.info(
            "Performance traces are automatically generated when you run simulations "
            "with the ExecutionTracer enabled."
        )
    else:
        trace_file = st.selectbox("Select Trace File", trace_files)

        # Load trace data
        with open(trace_file) as f:
            traces = json.load(f)

        df = pd.DataFrame(traces)

        st.subheader("Execution Summary")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Models", len(df))
        col2.metric("Total Time", f"{df['duration_seconds'].sum():.1f}s")
        col3.metric(
            "Success Rate", f"{(df['success'].sum() / len(df) * 100):.1f}%"
        )

        # Slowest models
        st.subheader("Slowest Models")
        slowest = df.nlargest(10, "duration_seconds")[
            ["model_name", "simulation_year", "duration_seconds", "memory_delta_mb"]
        ]
        st.dataframe(slowest, use_container_width=True)

        # Timeline visualization
        st.subheader("Execution Timeline")
        timeline_df = df.sort_values("start_time")[
            ["model_name", "duration_seconds", "simulation_year"]
        ]
        st.bar_chart(timeline_df.set_index("model_name")["duration_seconds"])

        # Memory usage
        st.subheader("Memory Usage")
        memory_df = df.nlargest(10, "memory_delta_mb")[
            ["model_name", "memory_delta_mb", "simulation_year"]
        ]
        st.bar_chart(memory_df.set_index("model_name")["memory_delta_mb"])

        # Download option
        st.subheader("Export Data")
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download Performance Data as CSV",
            data=csv,
            file_name=f"{trace_file.stem}.csv",
            mime="text/csv",
        )

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.info(
    """
    **PlanWise Debug Dashboard**

    Epic E071: Debug Utilities & Observability

    Features:
    - Database inspection and health checks
    - State visualization across simulation years
    - Dependency graph analysis
    - Performance profiling

    **Usage:**
    Select a debug mode from the dropdown to explore
    simulation data, dependencies, and performance metrics.
"""
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Quick Actions")

if st.sidebar.button("📊 Generate Full Report"):
    st.info("Full report generation not yet implemented")

if st.sidebar.button("🔄 Refresh Data"):
    st.rerun()

if st.sidebar.button("📁 Open Database"):
    db_path = get_database_path()
    st.code(f"Database location: {db_path}")
    st.info(
        f"Use DuckDB CLI to query: `duckdb {db_path}`"
    )
