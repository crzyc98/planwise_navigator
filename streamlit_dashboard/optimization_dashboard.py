"""
Unified Optimization Dashboard for PlanWise Navigator
Provides a comprehensive interface for managing optimization results from both
advanced_optimization.py and compensation_tuning.py interfaces.

This dashboard integrates:
- Results viewing and management
- Comparison tools
- Export capabilities
- Cache management
- System health monitoring
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import time
from pathlib import Path

from optimization_results_manager import get_optimization_results_manager
from optimization_integration import (
    get_duckdb_integration,
    get_optimization_cache,
    validate_optimization_environment,
    get_cached_simulation_summary,
    get_cached_multi_year_summary
)
from optimization_storage import (
    OptimizationType,
    OptimizationStatus,
    OptimizationEngine,
    ExportFormat
)

# Page configuration
st.set_page_config(
    page_title="Optimization Dashboard - PlanWise Navigator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #2E8B57;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #dee2e6;
        margin-bottom: 1rem;
    }
    .status-good {
        color: #28a745;
        font-weight: bold;
    }
    .status-warning {
        color: #ffc107;
        font-weight: bold;
    }
    .status-error {
        color: #dc3545;
        font-weight: bold;
    }
    .comparison-table {
        border-collapse: collapse;
        width: 100%;
    }
    .comparison-table th, .comparison-table td {
        border: 1px solid #ddd;
        padding: 8px;
        text-align: left;
    }
    .comparison-table th {
        background-color: #f2f2f2;
    }
</style>
""", unsafe_allow_html=True)

# Initialize managers
@st.cache_resource
def get_managers():
    """Initialize and cache manager instances."""
    return {
        'results_manager': get_optimization_results_manager(),
        'db_integration': get_duckdb_integration(),
        'cache': get_optimization_cache()
    }

managers = get_managers()
results_manager = managers['results_manager']
db_integration = managers['db_integration']
cache = managers['cache']

# Page header
st.markdown('<div class="main-header">📊 Optimization Results Dashboard</div>', unsafe_allow_html=True)
st.markdown("**Unified management for Advanced Optimization and Compensation Tuning results**")

# Sidebar
st.sidebar.header("🎛️ Dashboard Controls")

# Environment health check
with st.sidebar.expander("🔧 System Health", expanded=False):
    if st.button("🔍 Check Environment"):
        with st.spinner("Validating environment..."):
            validation = validate_optimization_environment()

            if all([
                validation["database_accessible"],
                validation["tables_exist"],
                validation["cache_operational"],
                validation["storage_initialized"]
            ]):
                st.success("✅ Environment healthy")
            else:
                st.warning("⚠️ Environment issues detected")

            # Show details
            for key, value in validation.items():
                if key in ["warnings", "errors"]:
                    continue
                status = "✅" if value else "❌"
                st.write(f"{status} {key.replace('_', ' ').title()}")

            if validation["warnings"]:
                st.warning("Warnings: " + "; ".join(validation["warnings"]))
            if validation["errors"]:
                st.error("Errors: " + "; ".join(validation["errors"]))

# Cache management
with st.sidebar.expander("💾 Cache Management", expanded=False):
    cache_stats = cache.get_cache_stats()
    st.metric("Session Cache Size", cache_stats["session_cache_size"])
    st.metric("File Cache Count", cache_stats["file_cache_count"])
    st.metric("File Cache Size (MB)", f"{cache_stats['file_cache_size_mb']:.2f}")

    if st.button("🗑️ Clear Cache"):
        cache.clear_cache()
        st.success("Cache cleared")
        st.rerun()

# Quick actions
st.sidebar.header("⚡ Quick Actions")
if st.sidebar.button("🚀 Launch Advanced Optimization"):
    st.switch_page("advanced_optimization.py")

if st.sidebar.button("💰 Launch Compensation Tuning"):
    st.switch_page("compensation_tuning.py")

# Main dashboard tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview",
    "📋 Results Browser",
    "⚖️ Comparison",
    "📥 Export & Archive",
    "📈 Analytics"
])

with tab1:
    st.header("📊 Optimization Overview")

    # Get recent results for overview
    recent_results = results_manager.get_recent_results(20)

    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_runs = len(recent_results)
        st.metric("Total Optimization Runs", total_runs)

    with col2:
        completed_runs = len([r for r in recent_results if r.status == OptimizationStatus.COMPLETED])
        st.metric("Completed Runs", completed_runs)

    with col3:
        advanced_runs = len([r for r in recent_results if r.optimization_type == OptimizationType.ADVANCED_SCIPY])
        st.metric("Advanced Optimizations", advanced_runs)

    with col4:
        tuning_runs = len([r for r in recent_results if r.optimization_type == OptimizationType.COMPENSATION_TUNING])
        st.metric("Compensation Tuning", tuning_runs)

    # Recent activity chart
    if recent_results:
        st.subheader("📈 Recent Activity")

        # Create activity timeline
        activity_data = []
        for run in recent_results:
            activity_data.append({
                "Date": run.created_at.date(),
                "Type": run.optimization_type.value.replace("_", " ").title(),
                "Status": run.status.value.title(),
                "Runtime (s)": run.runtime_seconds or 0,
                "Scenario": run.scenario_id
            })

        activity_df = pd.DataFrame(activity_data)

        # Timeline chart
        fig = px.scatter(
            activity_df,
            x="Date",
            y="Type",
            color="Status",
            size="Runtime (s)",
            hover_data=["Scenario"],
            title="Optimization Activity Timeline"
        )
        st.plotly_chart(fig, use_container_width=True)

        # Type distribution
        col1, col2 = st.columns(2)

        with col1:
            type_counts = activity_df["Type"].value_counts()
            fig_type = px.pie(
                values=type_counts.values,
                names=type_counts.index,
                title="Optimization Types"
            )
            st.plotly_chart(fig_type, use_container_width=True)

        with col2:
            status_counts = activity_df["Status"].value_counts()
            fig_status = px.pie(
                values=status_counts.values,
                names=status_counts.index,
                title="Status Distribution"
            )
            st.plotly_chart(fig_status, use_container_width=True)
    else:
        st.info("No optimization results found. Run some optimizations to see overview data.")

    # System summary
    st.subheader("🏗️ System Summary")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Recent Simulation Data**")
        try:
            sim_summary = get_cached_simulation_summary(2025)
            if "error" not in sim_summary:
                workforce = sim_summary["workforce"]
                st.metric("Total Headcount (2025)", f"{workforce['total_headcount']:,}")
                st.metric("Average Compensation", f"${workforce['avg_compensation']:,.0f}")
                st.metric("Total Compensation", f"${workforce['total_compensation']:,.0f}")
            else:
                st.warning("No recent simulation data available")
        except Exception as e:
            st.error(f"Error loading simulation data: {e}")

    with col2:
        st.markdown("**Database Status**")
        try:
            # Quick database health check
            validation = validate_optimization_environment()

            db_status = "🟢 Healthy" if validation["database_accessible"] else "🔴 Offline"
            st.write(f"Database: {db_status}")

            tables_status = "🟢 All Tables" if validation["tables_exist"] else "🟡 Some Missing"
            st.write(f"Tables: {tables_status}")

            data_status = "🟢 Recent Data" if validation["recent_data_available"] else "🟡 No Recent Data"
            st.write(f"Data: {data_status}")

        except Exception as e:
            st.error(f"Database check failed: {e}")

with tab2:
    st.header("📋 Optimization Results Browser")

    # Search and filter controls
    col1, col2, col3 = st.columns(3)

    with col1:
        search_query = st.text_input("🔍 Search scenarios, descriptions...")

    with col2:
        filter_type = st.selectbox(
            "Filter by Type",
            options=[None] + [t.value for t in OptimizationType],
            format_func=lambda x: "All Types" if x is None else x.replace("_", " ").title()
        )

    with col3:
        filter_status = st.selectbox(
            "Filter by Status",
            options=[None] + [s.value for s in OptimizationStatus],
            format_func=lambda x: "All Status" if x is None else x.title()
        )

    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.now().date() - timedelta(days=30))
    with col2:
        end_date = st.date_input("End Date", value=datetime.now().date())

    # Apply filters
    if search_query or filter_type or filter_status:
        opt_type = OptimizationType(filter_type) if filter_type else None
        opt_status = OptimizationStatus(filter_status) if filter_status else None

        filtered_results = results_manager.search_results(
            query=search_query if search_query else None,
            optimization_type=opt_type,
            status=opt_status
        )

        # Additional date filtering
        filtered_results = [
            r for r in filtered_results
            if start_date <= r.created_at.date() <= end_date
        ]
    else:
        filtered_results = results_manager.get_recent_results(50)
        filtered_results = [
            r for r in filtered_results
            if start_date <= r.created_at.date() <= end_date
        ]

    # Results table
    if filtered_results:
        st.subheader(f"📊 Found {len(filtered_results)} Results")

        # Create results DataFrame
        results_data = []
        for run in filtered_results:
            results_data.append({
                "Run ID": run.run_id[:8] + "...",
                "Scenario": run.scenario_id,
                "Type": run.optimization_type.value.replace("_", " ").title(),
                "Engine": run.optimization_engine.value.replace("_", " ").title(),
                "Status": run.status.value.title(),
                "Created": run.created_at.strftime("%Y-%m-%d %H:%M"),
                "Runtime": f"{run.runtime_seconds:.1f}s" if run.runtime_seconds else "N/A",
                "Converged": "✅" if run.converged else "❌" if run.converged is False else "N/A",
                "Full ID": run.run_id  # Hidden column for actions
            })

        df = pd.DataFrame(results_data)

        # Interactive table
        selected_data = st.dataframe(
            df.drop("Full ID", axis=1),  # Hide the full ID column
            use_container_width=True,
            selection_mode="multi-row",
            on_select="rerun"
        )

        # Action buttons
        if selected_data and hasattr(selected_data, 'selection') and selected_data.selection['rows']:
            selected_indices = selected_data.selection['rows']
            selected_run_ids = [df.iloc[i]["Full ID"] for i in selected_indices]

            st.subheader("🎯 Actions for Selected Results")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("📋 View Details"):
                    st.session_state['selected_run_details'] = selected_run_ids[0]

            with col2:
                if st.button("⚖️ Compare Selected"):
                    st.session_state['comparison_runs'] = selected_run_ids
                    st.success(f"Selected {len(selected_run_ids)} runs for comparison")

            with col3:
                if st.button("📥 Export Selected"):
                    st.session_state['export_runs'] = selected_run_ids
                    st.success(f"Queued {len(selected_run_ids)} runs for export")

            with col4:
                if st.button("🗑️ Delete Selected", type="secondary"):
                    if st.confirm(f"Delete {len(selected_run_ids)} optimization runs? This cannot be undone."):
                        deleted_count = 0
                        for run_id in selected_run_ids:
                            if results_manager.delete_results(run_id):
                                deleted_count += 1
                        st.success(f"Deleted {deleted_count} runs")
                        st.rerun()

        # Show details if requested
        if 'selected_run_details' in st.session_state:
            run_id = st.session_state['selected_run_details']

            with st.expander(f"📋 Run Details: {run_id[:8]}...", expanded=True):
                run = results_manager.load_results(run_id)
                if run:
                    # Metadata
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Metadata**")
                        st.write(f"Scenario: {run.metadata.scenario_id}")
                        st.write(f"Type: {run.metadata.optimization_type.value}")
                        st.write(f"Engine: {run.metadata.optimization_engine.value}")
                        st.write(f"Status: {run.metadata.status.value}")
                        st.write(f"Created: {run.metadata.created_at}")

                    with col2:
                        st.write("**Performance**")
                        st.write(f"Runtime: {run.metadata.runtime_seconds:.2f}s" if run.metadata.runtime_seconds else "N/A")
                        st.write(f"Evaluations: {run.metadata.function_evaluations}" if run.metadata.function_evaluations else "N/A")
                        st.write(f"Converged: {'Yes' if run.metadata.converged else 'No' if run.metadata.converged is False else 'N/A'}")
                        st.write(f"Risk Level: {run.results.risk_level}")

                    # Results
                    st.write("**Results**")
                    st.write(f"Objective Value: {run.results.objective_value:.6f}" if run.results.objective_value else "N/A")

                    # Parameters
                    if run.results.optimal_parameters:
                        st.write("**Optimal Parameters**")
                        params_df = pd.DataFrame([
                            {"Parameter": k, "Value": f"{v:.4f}"}
                            for k, v in run.results.optimal_parameters.items()
                        ])
                        st.dataframe(params_df, use_container_width=True)

                else:
                    st.error("Run details not found")

                if st.button("❌ Close Details"):
                    del st.session_state['selected_run_details']
                    st.rerun()

    else:
        st.info("No results match the current filters")

with tab3:
    st.header("⚖️ Results Comparison")

    # Check if runs are selected for comparison
    comparison_runs = st.session_state.get('comparison_runs', [])

    if len(comparison_runs) < 2:
        st.info("Select at least 2 results from the Results Browser to compare them.")

        # Alternative: manual run selection
        st.subheader("Manual Run Selection")
        recent_runs = results_manager.get_recent_results(20)

        if recent_runs:
            run_options = {
                f"{run.scenario_id} ({run.run_id[:8]}...)": run.run_id
                for run in recent_runs
            }

            selected_for_comparison = st.multiselect(
                "Select runs to compare",
                options=list(run_options.keys()),
                help="Choose 2 or more optimization runs to compare"
            )

            if len(selected_for_comparison) >= 2:
                comparison_runs = [run_options[key] for key in selected_for_comparison]
                st.session_state['comparison_runs'] = comparison_runs

    if len(comparison_runs) >= 2:
        st.subheader(f"🔍 Comparing {len(comparison_runs)} Optimization Runs")

        # Perform comparison
        with st.spinner("Generating comparison..."):
            comparison = results_manager.compare_results(comparison_runs)

        # Overview
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Runs Compared", comparison['run_count'])
        with col2:
            best_run = comparison['objective_comparison']['best_run']
            st.metric("Best Objective", f"{best_run['objective_value']:.4f}")
        with col3:
            st.metric("Best Scenario", best_run['scenario'])

        # Run metadata comparison
        st.subheader("📊 Run Comparison Table")
        metadata_df = pd.DataFrame(comparison['run_metadata'])
        metadata_df['created_at'] = pd.to_datetime(metadata_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        st.dataframe(metadata_df, use_container_width=True)

        # Parameter comparison
        st.subheader("⚙️ Parameter Comparison")
        if comparison['parameter_comparison']:
            param_names = list(comparison['parameter_comparison'].keys())

            # Select parameters to compare
            selected_params = st.multiselect(
                "Select parameters to visualize",
                options=param_names,
                default=param_names[:3] if len(param_names) >= 3 else param_names
            )

            if selected_params:
                for param in selected_params:
                    param_data = comparison['parameter_comparison'][param]

                    # Create comparison chart
                    values_df = pd.DataFrame(param_data['values'])

                    fig = px.bar(
                        values_df,
                        x='scenario',
                        y='value',
                        title=f"{param} Comparison",
                        text='value'
                    )
                    fig.update_traces(texttemplate='%{text:.4f}', textposition='outside')
                    st.plotly_chart(fig, use_container_width=True)

                    # Show statistics
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(f"{param} Min", f"{param_data['min']:.4f}")
                    with col2:
                        st.metric(f"{param} Max", f"{param_data['max']:.4f}")
                    with col3:
                        st.metric(f"{param} Variance", f"{param_data['variance']:.6f}")

        # Objective comparison
        st.subheader("🎯 Objective Comparison")
        objectives_df = pd.DataFrame(comparison['objective_comparison']['objectives'])

        fig_obj = px.bar(
            objectives_df,
            x='scenario',
            y='objective_value',
            title="Objective Values Comparison",
            text='objective_value'
        )
        fig_obj.update_traces(texttemplate='%{text:.4f}', textposition='outside')
        st.plotly_chart(fig_obj, use_container_width=True)

        # Risk comparison
        st.subheader("⚠️ Risk Level Comparison")
        risk_data = []
        for risk_level, runs in comparison['risk_comparison'].items():
            for run in runs:
                risk_data.append({
                    'Scenario': run['scenario'],
                    'Risk Level': risk_level,
                    'Run ID': run['run_id'][:8] + "..."
                })

        if risk_data:
            risk_df = pd.DataFrame(risk_data)
            fig_risk = px.histogram(
                risk_df,
                x='Risk Level',
                color='Risk Level',
                title="Risk Level Distribution"
            )
            st.plotly_chart(fig_risk, use_container_width=True)

        # Clear comparison
        if st.button("🗑️ Clear Comparison"):
            st.session_state['comparison_runs'] = []
            st.rerun()

with tab4:
    st.header("📥 Export & Archive Management")

    # Check for queued exports
    export_runs = st.session_state.get('export_runs', [])

    if export_runs:
        st.subheader(f"📤 Export Queue ({len(export_runs)} runs)")

        # Export configuration
        col1, col2 = st.columns(2)

        with col1:
            export_format = st.selectbox(
                "Export Format",
                options=[f.value for f in ExportFormat],
                format_func=lambda x: x.upper()
            )

        with col2:
            include_simulation_data = st.checkbox("Include Simulation Data", value=True)

        # Custom export path
        custom_path = st.text_input(
            "Custom Export Path (optional)",
            placeholder="/path/to/export/directory/",
            help="Leave empty to use default naming"
        )

        # Bulk export button
        if st.button("📥 Export All Queued Runs"):
            export_results = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, run_id in enumerate(export_runs):
                try:
                    status_text.text(f"Exporting run {i+1}/{len(export_runs)}: {run_id[:8]}...")

                    output_path = None
                    if custom_path:
                        run_filename = f"optimization_{run_id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{export_format}"
                        output_path = str(Path(custom_path) / run_filename)

                    export_path = results_manager.export_results(
                        run_id=run_id,
                        format=ExportFormat(export_format),
                        output_path=output_path
                    )

                    export_results.append({
                        'run_id': run_id,
                        'export_path': export_path,
                        'status': 'success'
                    })

                except Exception as e:
                    export_results.append({
                        'run_id': run_id,
                        'export_path': None,
                        'status': f'error: {str(e)}'
                    })

                progress_bar.progress((i + 1) / len(export_runs))

            # Show results
            status_text.text("Export completed!")

            successful_exports = [r for r in export_results if r['status'] == 'success']
            failed_exports = [r for r in export_results if r['status'] != 'success']

            if successful_exports:
                st.success(f"✅ Successfully exported {len(successful_exports)} runs")
                for result in successful_exports:
                    st.text(f"📁 {result['export_path']}")

            if failed_exports:
                st.error(f"❌ Failed to export {len(failed_exports)} runs")
                for result in failed_exports:
                    st.text(f"❌ {result['run_id'][:8]}...: {result['status']}")

            # Clear export queue
            st.session_state['export_runs'] = []

        # Clear queue button
        if st.button("🗑️ Clear Export Queue"):
            st.session_state['export_runs'] = []
            st.rerun()

    # Export history
    st.subheader("📜 Export History")

    recent_runs = results_manager.get_recent_results(10)
    if recent_runs:
        selected_run_for_history = st.selectbox(
            "View export history for run",
            options=[r.run_id for r in recent_runs],
            format_func=lambda x: f"{x[:8]}... ({next(r.scenario_id for r in recent_runs if r.run_id == x)})"
        )

        if selected_run_for_history:
            history = results_manager.get_export_history(selected_run_for_history)

            if history:
                history_df = pd.DataFrame(history)
                history_df['exported_at'] = pd.to_datetime(history_df['exported_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
                history_df['file_size_mb'] = history_df['file_size_bytes'] / (1024 * 1024)

                st.dataframe(
                    history_df[['format', 'exported_at', 'file_size_mb', 'path']],
                    use_container_width=True
                )
            else:
                st.info("No export history for this run")

    # Bulk operations
    st.subheader("🔧 Bulk Operations")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📥 Export All Recent Results"):
            recent_runs = results_manager.get_recent_results(20)
            if recent_runs:
                st.session_state['export_runs'] = [r.run_id for r in recent_runs]
                st.success(f"Queued {len(recent_runs)} runs for export")
                st.rerun()
            else:
                st.info("No recent results to export")

    with col2:
        if st.button("🗑️ Archive Old Results"):
            # This would implement archiving logic
            st.info("Archive functionality would be implemented here")

with tab5:
    st.header("📈 Optimization Analytics")

    # Get data for analytics
    recent_runs = results_manager.get_recent_results(50)

    if not recent_runs:
        st.info("No optimization results available for analytics. Run some optimizations first.")
    else:
        # Performance analytics
        st.subheader("⚡ Performance Analytics")

        # Create performance DataFrame
        perf_data = []
        for run in recent_runs:
            if run.runtime_seconds and run.function_evaluations:
                perf_data.append({
                    'Type': run.optimization_type.value.replace('_', ' ').title(),
                    'Engine': run.optimization_engine.value.replace('_', ' ').title(),
                    'Runtime (s)': run.runtime_seconds,
                    'Function Evaluations': run.function_evaluations,
                    'Converged': run.converged,
                    'Date': run.created_at.date()
                })

        if perf_data:
            perf_df = pd.DataFrame(perf_data)

            # Runtime distribution
            col1, col2 = st.columns(2)

            with col1:
                fig_runtime = px.box(
                    perf_df,
                    x='Type',
                    y='Runtime (s)',
                    title="Runtime Distribution by Optimization Type"
                )
                st.plotly_chart(fig_runtime, use_container_width=True)

            with col2:
                fig_evals = px.scatter(
                    perf_df,
                    x='Function Evaluations',
                    y='Runtime (s)',
                    color='Type',
                    title="Runtime vs Function Evaluations"
                )
                st.plotly_chart(fig_evals, use_container_width=True)

            # Convergence analysis
            st.subheader("🎯 Convergence Analysis")

            convergence_stats = perf_df.groupby(['Type', 'Converged']).size().reset_index(name='Count')

            fig_conv = px.bar(
                convergence_stats,
                x='Type',
                y='Count',
                color='Converged',
                title="Convergence Rate by Optimization Type"
            )
            st.plotly_chart(fig_conv, use_container_width=True)

        # Objective value trends
        st.subheader("📊 Objective Value Trends")

        objective_data = []
        for run in recent_runs:
            full_run = results_manager.load_results(run.run_id)
            if full_run and full_run.results.objective_value:
                objective_data.append({
                    'Date': run.created_at,
                    'Objective Value': full_run.results.objective_value,
                    'Type': run.optimization_type.value.replace('_', ' ').title(),
                    'Scenario': run.scenario_id,
                    'Risk Level': full_run.results.risk_level
                })

        if objective_data:
            obj_df = pd.DataFrame(objective_data)

            # Time series of objective values
            fig_trend = px.scatter(
                obj_df,
                x='Date',
                y='Objective Value',
                color='Type',
                size_max=10,
                title="Objective Value Trends Over Time"
            )
            st.plotly_chart(fig_trend, use_container_width=True)

            # Risk level distribution
            col1, col2 = st.columns(2)

            with col1:
                risk_counts = obj_df['Risk Level'].value_counts()
                fig_risk = px.pie(
                    values=risk_counts.values,
                    names=risk_counts.index,
                    title="Risk Level Distribution"
                )
                st.plotly_chart(fig_risk, use_container_width=True)

            with col2:
                # Objective value by risk level
                fig_risk_obj = px.box(
                    obj_df,
                    x='Risk Level',
                    y='Objective Value',
                    title="Objective Values by Risk Level"
                )
                st.plotly_chart(fig_risk_obj, use_container_width=True)

        # Simulation data analytics
        st.subheader("🏗️ Simulation Data Analytics")

        try:
            multi_year_summary = get_cached_multi_year_summary(2025, 2029)

            if multi_year_summary['overall']['data_quality'] == 'good':
                year_summaries = multi_year_summary['year_summaries']
                yoy_metrics = multi_year_summary['yoy_metrics']

                # Workforce growth trends
                workforce_data = []
                for year, summary in year_summaries.items():
                    if 'error' not in summary:
                        workforce_data.append({
                            'Year': year,
                            'Headcount': summary['workforce']['total_headcount'],
                            'Total Compensation': summary['workforce']['total_compensation'],
                            'Avg Compensation': summary['workforce']['avg_compensation']
                        })

                if workforce_data:
                    workforce_df = pd.DataFrame(workforce_data)

                    col1, col2 = st.columns(2)

                    with col1:
                        fig_hc = px.line(
                            workforce_df,
                            x='Year',
                            y='Headcount',
                            title="Headcount Trends",
                            markers=True
                        )
                        st.plotly_chart(fig_hc, use_container_width=True)

                    with col2:
                        fig_comp = px.line(
                            workforce_df,
                            x='Year',
                            y='Total Compensation',
                            title="Total Compensation Trends",
                            markers=True
                        )
                        st.plotly_chart(fig_comp, use_container_width=True)

                # Year-over-year growth rates
                if yoy_metrics:
                    growth_data = []
                    for year, metrics in yoy_metrics.items():
                        growth_data.append({
                            'Year': year,
                            'Headcount Growth': metrics['headcount_growth'] * 100,
                            'Compensation Growth': metrics['compensation_growth'] * 100
                        })

                    growth_df = pd.DataFrame(growth_data)

                    fig_growth = px.bar(
                        growth_df,
                        x='Year',
                        y=['Headcount Growth', 'Compensation Growth'],
                        title="Year-over-Year Growth Rates (%)",
                        barmode='group'
                    )
                    st.plotly_chart(fig_growth, use_container_width=True)
            else:
                st.warning("Limited simulation data available for analytics")

        except Exception as e:
            st.error(f"Error loading simulation data analytics: {e}")

# Footer
st.markdown("---")
st.markdown("**PlanWise Navigator Optimization Dashboard** | Built with Streamlit | v1.0.0")

# Auto-refresh option
if st.sidebar.checkbox("🔄 Auto-refresh (30s)", value=False):
    time.sleep(30)
    st.rerun()
